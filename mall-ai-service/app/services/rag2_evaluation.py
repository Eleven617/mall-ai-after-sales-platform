"""Versioned, measurement-oriented RAG 2.0 evaluation helpers.

Retrieval metrics are fully local and repeatable.  Generated-answer grounding
is intentionally a separate explicit profile because the existing evidence
verifier and answer generation call the configured LLM provider.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from math import ceil, log2
from pathlib import Path
from typing import Any

from app.schemas.rag import RetrievedChunk
from app.services.llm_observability import (
    TokenPricing,
    capture_llm_metrics,
    summarize_llm_metrics,
)
from app.services.policy_retrieval import (
    PolicyRetrievalResult,
    PolicyRetrievalUnavailable,
    is_evidence_candidate,
    retrieve_policy_candidates,
)
from app.services.rag_service import RagAnswer, answer_after_sales_question


class Rag2EvaluationError(ValueError):
    """The committed synthetic suite does not satisfy its stable contract."""


def load_rag2_golden_suite(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise Rag2EvaluationError("RAG2 suite must be a JSON object")
    _validate_suite(raw)
    return raw


def evaluate_retrieval_suite(
    suite: Mapping[str, Any],
    *,
    mode: str,
    top_k: int = 3,
    retrieve: Callable[..., PolicyRetrievalResult] = retrieve_policy_candidates,
) -> dict[str, Any]:
    """Measure candidate recall/ranking without invoking an LLM provider."""
    _validate_suite(suite)
    if top_k < 1:
        raise Rag2EvaluationError("top_k must be positive")

    cases = suite["cases"]
    results: list[dict[str, Any]] = []
    blocked_cases = 0
    supported_ranks: list[int] = []
    supported_ndcg: list[float] = []
    supported_total = 0
    supported_hits = 0
    abstention_total = 0
    abstention_no_candidate = 0
    reranker_unavailable_cases = 0
    latencies: list[float] = []

    for case in cases:
        expected = case["expected"]
        started_at = time.perf_counter()
        try:
            outcome = retrieve(case["query"], top_k=top_k, mode=mode)
        except PolicyRetrievalUnavailable:
            elapsed_ms = _elapsed_ms(started_at)
            blocked_cases += 1
            results.append(
                {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "status": "environment_blocked",
                    "elapsed_ms": elapsed_ms,
                    "retrieved_sections": [],
                }
            )
            continue
        except Exception as exc:
            raise Rag2EvaluationError("RAG2 retriever raised an unexpected error") from exc

        elapsed_ms = _elapsed_ms(started_at)
        latencies.append(elapsed_ms)
        chunks = outcome.chunks
        allowed_sections = expected["allowed_evidence_sections"]
        relevant_ranks = _relevant_ranks(chunks, allowed_sections)
        is_supported = expected["outcome"] == "answered"
        if is_supported:
            supported_total += 1
            if relevant_ranks:
                supported_hits += 1
                supported_ranks.append(relevant_ranks[0])
                supported_ndcg.append(_ndcg_at_k(relevant_ranks, top_k))
            else:
                supported_ndcg.append(0.0)
        else:
            abstention_total += 1
            candidate_chunks = [chunk for chunk in chunks if is_evidence_candidate(chunk)]
            if not candidate_chunks:
                abstention_no_candidate += 1

        if outcome.reranker_unavailable:
            reranker_unavailable_cases += 1
        retrieval_pass = bool(relevant_ranks) if is_supported else True
        results.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "status": "passed" if retrieval_pass else "quality_failed",
                "elapsed_ms": elapsed_ms,
                "retrieved_sections": [chunk.section_path for chunk in chunks],
                "relevant_ranks": relevant_ranks,
                "effective_mode": outcome.effective_mode,
                "reranker_unavailable": outcome.reranker_unavailable,
                # Candidate retrieval alone cannot establish no-evidence.  The
                # existing semantic verifier owns that final abstention choice.
                "requires_semantic_abstention_check": not is_supported,
            }
        )

    quality_failed = any(result["status"] == "quality_failed" for result in results)
    reranker_measurement_blocked = mode == "hybrid_rerank" and reranker_unavailable_cases > 0
    status = (
        "environment_blocked"
        if blocked_cases or reranker_measurement_blocked
        else "quality_failed"
        if quality_failed
        else "passed"
    )
    return {
        "suite_version": suite["suite_version"],
        "mode": mode,
        "status": status,
        "total_cases": len(cases),
        "environment_blocked_cases": blocked_cases,
        "supported_cases": supported_total,
        "recall_at_k": _ratio(supported_hits, supported_total),
        "mrr": round(
            sum(1 / rank for rank in supported_ranks) / supported_total
            if supported_total
            else 0.0,
            6,
        ),
        "ndcg_at_k": round(
            sum(supported_ndcg) / supported_total if supported_total else 0.0,
            6,
        ),
        "abstention_cases": abstention_total,
        "abstention_no_candidate_rate": _ratio(
            abstention_no_candidate, abstention_total
        ),
        "reranker_unavailable_cases": reranker_unavailable_cases,
        "reranker_measurement_blocked": reranker_measurement_blocked,
        "latency": _latency_summary(latencies),
        "cost": {
            "external_model_calls": 0,
            "estimated_external_cost": 0.0,
            "currency": "CNY",
            "note": "Dense/BM25/RRF/Cross-Encoder retrieval is local; local CPU/disk cost is not converted to a currency estimate.",
        },
        "results": results,
    }


def evaluate_grounded_answer_suite(
    suite: Mapping[str, Any],
    *,
    mode: str,
    answer_question: Callable[[str], RagAnswer] | None = None,
    pricing: TokenPricing | None = None,
    timeout_seconds: float | None = None,
    max_attempts: int | None = None,
    max_cases: int | None = None,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Explicit live-safe grounding/abstention evaluator for a chosen mode.

    It does not persist prompts, answers, customer IDs, or policy texts.  The
    suite queries are synthetic and the response report contains only reviewed
    contract summaries and numerical provider metrics.
    """
    _validate_suite(suite)
    selected_cases = list(suite["cases"])
    if case_ids is not None:
        selected_cases = [case for case in selected_cases if case["case_id"] in case_ids]
        missing_case_ids = case_ids - {case["case_id"] for case in selected_cases}
        if missing_case_ids:
            raise Rag2EvaluationError("Unknown RAG2 grounding case ID")
    elif max_cases:
        selected_cases = selected_cases[:max_cases]
    answer_question = answer_question or (
        lambda query: answer_after_sales_question(query, retrieval_mode=mode)
    )
    results: list[dict[str, Any]] = []
    elapsed_values: list[float] = []
    environment_blocked = 0

    with capture_llm_metrics(
        timeout_seconds=timeout_seconds, max_attempts=max_attempts
    ) as metric_sink:
        for case in selected_cases:
            started_at = time.perf_counter()
            answer = answer_question(case["query"])
            elapsed_ms = _elapsed_ms(started_at)
            elapsed_values.append(elapsed_ms)
            expected = case["expected"]
            observed_outcome = _answer_outcome(answer)
            if observed_outcome == "environment_blocked":
                environment_blocked += 1
                results.append(
                    {
                        "case_id": case["case_id"],
                        "category": case["category"],
                        "status": "environment_blocked",
                        "elapsed_ms": elapsed_ms,
                        "observed_outcome": observed_outcome,
                        "violations": [],
                    }
                )
                continue

            violations = _answer_contract_violations(expected, answer, observed_outcome)
            results.append(
                {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "status": "passed" if not violations else "quality_failed",
                    "elapsed_ms": elapsed_ms,
                    "observed_outcome": observed_outcome,
                    "source_sections": [source.section_path for source in answer.sources],
                    "violations": violations,
                }
            )

    quality_failed = any(result["status"] == "quality_failed" for result in results)
    status = (
        "environment_blocked"
        if environment_blocked
        else "quality_failed"
        if quality_failed
        else "passed"
    )
    passed_cases = sum(result["status"] == "passed" for result in results)
    return {
        "suite_version": suite["suite_version"],
        "mode": mode,
        "status": status,
        "total_cases": len(selected_cases),
        "passed_cases": passed_cases,
        "quality_failed_cases": sum(
            result["status"] == "quality_failed" for result in results
        ),
        "environment_blocked_cases": environment_blocked,
        "grounded_answer_or_abstention_pass_rate": _ratio(
            passed_cases, len(selected_cases) - environment_blocked
        ),
        "latency": _latency_summary(elapsed_values),
        "provider_metrics": summarize_llm_metrics(metric_sink.events, pricing),
        "results": results,
    }


def _validate_suite(suite: Mapping[str, Any]) -> None:
    if suite.get("schema_version") != "1":
        raise Rag2EvaluationError("Unsupported RAG2 suite schema version")
    if not isinstance(suite.get("suite_version"), str) or not suite["suite_version"]:
        raise Rag2EvaluationError("RAG2 suite must have a version")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise Rag2EvaluationError("RAG2 suite must contain cases")
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise Rag2EvaluationError("RAG2 case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise Rag2EvaluationError("RAG2 case IDs must be unique non-empty strings")
        case_ids.add(case_id)
        if not isinstance(case.get("category"), str) or not isinstance(case.get("query"), str):
            raise Rag2EvaluationError("RAG2 cases require category and synthetic query")
        expected = case.get("expected")
        if not isinstance(expected, Mapping):
            raise Rag2EvaluationError("RAG2 case requires expected contract")
        outcome = expected.get("outcome")
        allowed = expected.get("allowed_evidence_sections")
        if outcome not in {"answered", "abstain"} or not isinstance(allowed, list):
            raise Rag2EvaluationError("RAG2 expected outcome/sections are invalid")
        if outcome == "answered" and not allowed:
            raise Rag2EvaluationError("Answered RAG2 case needs allowed evidence")
        if outcome == "abstain" and allowed:
            raise Rag2EvaluationError("Abstention RAG2 case cannot allow evidence")
        if not all(isinstance(section, str) and section for section in allowed):
            raise Rag2EvaluationError("Allowed evidence sections must be non-empty strings")
    fixtures = suite.get("injection_fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise Rag2EvaluationError("RAG2 suite must contain injection fixtures")
    fixture_ids = set()
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise Rag2EvaluationError("RAG2 injection fixture must be an object")
        fixture_id = fixture.get("case_id")
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in fixture_ids:
            raise Rag2EvaluationError("RAG2 injection fixture IDs must be unique")
        fixture_ids.add(fixture_id)
        if not isinstance(fixture.get("untrusted_candidate_text"), str):
            raise Rag2EvaluationError("RAG2 injection fixture needs untrusted text")


def _relevant_ranks(
    chunks: list[RetrievedChunk], allowed_sections: list[str]
) -> list[int]:
    if not allowed_sections:
        return []
    return [
        rank
        for rank, chunk in enumerate(chunks, start=1)
        if any(section in chunk.section_path for section in allowed_sections)
    ]


def _ndcg_at_k(relevant_ranks: list[int], top_k: int) -> float:
    if not relevant_ranks:
        return 0.0
    dcg = sum(1 / log2(rank + 1) for rank in relevant_ranks if rank <= top_k)
    ideal_count = min(len(relevant_ranks), top_k)
    ideal_dcg = sum(1 / log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _answer_outcome(answer: RagAnswer) -> str:
    if (
        answer.retrieval_unavailable
        or answer.evidence_verification_unavailable
        or answer.answer_generation_unavailable
    ):
        return "environment_blocked"
    return "abstain" if answer.no_evidence else "answered"


def _answer_contract_violations(
    expected: Mapping[str, Any], answer: RagAnswer, observed_outcome: str
) -> list[str]:
    violations: list[str] = []
    wanted_outcome = expected["outcome"]
    if observed_outcome != wanted_outcome:
        violations.append("OUTCOME_MISMATCH")
        return violations
    if wanted_outcome == "abstain":
        if answer.sources:
            violations.append("ABSTENTION_HAS_SOURCES")
        return violations

    allowed_sections = expected["allowed_evidence_sections"]
    source_sections = [source.section_path for source in answer.sources]
    if not source_sections or not all(
        any(allowed in section for allowed in allowed_sections)
        for section in source_sections
    ):
        violations.append("UNAPPROVED_EVIDENCE_SOURCE")
    for group in expected.get("answer_fact_marker_groups", []):
        if not any(_contains_marker(answer.answer, marker) for marker in group):
            violations.append("MISSING_REQUIRED_FACT_MARKER")
            break
    for claim in expected.get("answer_not_contains", []):
        if _contains_unnegated_claim(answer.answer, claim):
            violations.append("FORBIDDEN_POLICY_CLAIM")
            break
    return violations


def _contains_marker(answer: str, marker: str) -> bool:
    return "".join(answer.lower().split()).find("".join(marker.lower().split())) >= 0


def _contains_unnegated_claim(answer: str, claim: str) -> bool:
    normalized_answer = "".join(answer.lower().split())
    normalized_claim = "".join(claim.lower().split())
    start = normalized_answer.find(normalized_claim)
    while start >= 0:
        clause_start = max(
            normalized_answer.rfind(punctuation, 0, start)
            for punctuation in "，。；：！？!?"
        ) + 1
        prefix = normalized_answer[clause_start:start]
        if not any(negation in prefix for negation in ("不", "无", "不能", "无法", "未")):
            return True
        start = normalized_answer.find(normalized_claim, start + 1)
    return False


def _latency_summary(values: list[float]) -> dict[str, float]:
    sorted_values = sorted(values)
    return {
        "average_ms": round(sum(sorted_values) / len(sorted_values), 2)
        if sorted_values
        else 0.0,
        "p95_ms": sorted_values[max(0, ceil(len(sorted_values) * 0.95) - 1)]
        if sorted_values
        else 0.0,
        "max_ms": sorted_values[-1] if sorted_values else 0.0,
    }


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
