"""Offline and live-safe checks for RAG answer grounding.

This evaluator does not claim that string checks prove semantic correctness.
It verifies a reviewed minimum contract: expected source attribution, expected
outcome, required fact markers, and forbidden high-risk claims. Human review
remains required for paraphrases and new failure patterns.
"""
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from app.services.rag_service import RagAnswer, answer_after_sales_question


_NEGATION_PREFIXES = (
    "不",
    "未",
    "无",
    "非",
    "不能",
    "不可",
    "不会",
    "没有",
    "并非",
    "并不",
    "不予",
    "not",
    "cannot",
    "doesnot",
)


class RagGroundingEvaluationError(ValueError):
    """Raised when a reviewed grounding case has an invalid contract."""


def load_rag_grounding_cases(path: Path) -> list[dict[str, Any]]:
    """Load reviewed, non-personal RAG grounding cases."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RagGroundingEvaluationError(
            f"Unable to read RAG grounding cases: {type(exc).__name__}"
        ) from exc
    if not isinstance(data, list):
        raise RagGroundingEvaluationError("RAG grounding cases must be a JSON array")
    return data


def evaluate_rag_grounding_cases(
    cases: Iterable[dict[str, Any]],
    answer_question: Callable[[str], RagAnswer] = answer_after_sales_question,
) -> dict[str, Any]:
    """Evaluate reviewed RAG answer contracts without exposing raw answers."""
    reports: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        case_id = _safe_case_id(case, index)
        try:
            reports.append(evaluate_rag_grounding_case(case, answer_question))
        except RagGroundingEvaluationError as exc:
            reports.append(
                {
                    "id": case_id,
                    "passed": False,
                    "checks": {"case_is_valid": False},
                    "observed": {"error_type": type(exc).__name__},
                }
            )
        except Exception as exc:  # Keep unexpected provider details out of reports.
            reports.append(
                {
                    "id": case_id,
                    "passed": False,
                    "checks": {"answer_function_completed": False},
                    "observed": {"error_type": type(exc).__name__},
                }
            )

    passed_cases = sum(1 for report in reports if report["passed"])
    checks = [check for report in reports for check in report["checks"].values()]
    passed_checks = sum(1 for check in checks if check)
    review_checks = [
        check for report in reports for check in report.get("review_checks", {}).values()
    ]
    passed_review_checks = sum(1 for check in review_checks if check)
    environment_blocked = [
        report
        for report in reports
        if _is_environment_blocked(report)
    ]
    quality_reports = [report for report in reports if report not in environment_blocked]
    quality_passed_cases = sum(1 for report in quality_reports if report["passed"])
    quality_failed_cases = len(quality_reports) - quality_passed_cases
    status = (
        "environment_blocked"
        if environment_blocked
        else "passed" if quality_failed_cases == 0 else "failed"
    )
    return {
        "mode": "grounding_contract",
        "status": status,
        "total_cases": len(reports),
        "passed_cases": passed_cases,
        "failed_cases": len(reports) - passed_cases,
        "pass_rate": _ratio(passed_cases, len(reports)),
        "quality_evaluated_cases": len(quality_reports),
        "quality_passed_cases": quality_passed_cases,
        "quality_failed_cases": quality_failed_cases,
        "quality_pass_rate": _ratio(quality_passed_cases, len(quality_reports)),
        "environment_blocked_cases": len(environment_blocked),
        "environment_blocked_case_ids": [report["id"] for report in environment_blocked],
        "check_summary": {
            "total": len(checks),
            "passed": passed_checks,
            "pass_rate": _ratio(passed_checks, len(checks)),
        },
        "review_check_summary": {
            "total": len(review_checks),
            "passed": passed_review_checks,
            "pass_rate": _ratio(passed_review_checks, len(review_checks)),
        },
        "manual_review_case_ids": [
            report["id"]
            for report in quality_reports
            if report.get("review_checks") and not all(report["review_checks"].values())
        ],
        "cases": reports,
    }


def evaluate_rag_grounding_case(
    case: dict[str, Any],
    answer_question: Callable[[str], RagAnswer] = answer_after_sales_question,
) -> dict[str, Any]:
    """Run one synthetic question through the real RAG answer boundary."""
    if not isinstance(case, dict):
        raise RagGroundingEvaluationError("Each grounding case must be an object")
    case_id = _required_text(case, "id")
    question = _required_text(case, "question")
    expected = case.get("expected")
    if not isinstance(expected, dict):
        raise RagGroundingEvaluationError(f"Case {case_id} requires expected")

    result = answer_question(question)
    observed = {
        "outcome": _outcome(result),
        "source_sections": [source.section_path for source in result.sources],
        "source_count": len(result.sources),
    }
    checks, review_checks = _evaluate_contract(expected, result, observed)
    return {
        "id": case_id,
        "passed": bool(checks) and all(checks.values()),
        "expected_outcome": expected.get("outcome"),
        "checks": checks,
        "review_checks": review_checks,
        "observed": observed,
    }


def _is_environment_blocked(report: dict[str, Any]) -> bool:
    """Do not label a provider outage as an answer-grounding failure."""
    observed = report.get("observed")
    if not isinstance(observed, dict):
        return False
    outcome = observed.get("outcome")
    expected_outcome = report.get("expected_outcome")
    return (
        outcome in {
            "retrieval_unavailable",
            "evidence_verification_unavailable",
            "answer_generation_unavailable",
        }
        and outcome != expected_outcome
    )


def _outcome(result: RagAnswer) -> str:
    if result.retrieval_unavailable:
        return "retrieval_unavailable"
    if result.evidence_verification_unavailable:
        return "evidence_verification_unavailable"
    if result.answer_generation_unavailable:
        return "answer_generation_unavailable"
    if result.no_evidence:
        return "no_evidence"
    return "answered"


def _evaluate_contract(
    expected: dict[str, Any],
    result: RagAnswer,
    observed: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, bool]]:
    checks: dict[str, bool] = {}
    review_checks: dict[str, bool] = {}
    if "outcome" in expected:
        expected_outcome = _required_text(expected, "outcome")
        checks["outcome"] = observed["outcome"] == expected_outcome
    if "source_sections_include" in expected:
        expected_sections = _string_list(
            expected["source_sections_include"],
            "expected.source_sections_include",
        )
        checks["source_sections_include"] = all(
            any(section in observed_section for observed_section in observed["source_sections"])
            for section in expected_sections
        )
    if "sources_empty" in expected:
        if not isinstance(expected["sources_empty"], bool):
            raise RagGroundingEvaluationError("expected.sources_empty must be boolean")
        checks["sources_empty"] = (
            observed["source_count"] == 0
        ) == expected["sources_empty"]
    if "answer_fact_marker_groups" in expected:
        groups = _string_groups(
            expected["answer_fact_marker_groups"],
            "expected.answer_fact_marker_groups",
        )
        # A natural-language paraphrase can express the same fact without an
        # exact marker. Record this as a human-review signal, not a false
        # production-quality failure.
        review_checks["answer_fact_marker_groups"] = all(
            any(_contains_fact_marker(result.answer, term) for term in group)
            for group in groups
        )
    if "answer_not_contains" in expected:
        forbidden = _string_list(
            expected["answer_not_contains"],
            "expected.answer_not_contains",
        )
        checks["answer_not_contains"] = not any(
            _contains_unnegated_claim(result.answer, term) for term in forbidden
        )
    if not checks and not review_checks:
        raise RagGroundingEvaluationError("expected must contain at least one check")
    return checks, review_checks


def _safe_case_id(case: Any, index: int) -> str:
    if isinstance(case, dict) and isinstance(case.get("id"), str) and case["id"].strip():
        return case["id"].strip()
    return f"invalid-case-{index}"


def _required_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RagGroundingEvaluationError(f"Missing non-empty {key}")
    return value.strip()


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise RagGroundingEvaluationError(f"{field_name} must be a non-empty string list")
    return value


def _string_groups(value: Any, field_name: str) -> list[list[str]]:
    if not isinstance(value, list) or not value:
        raise RagGroundingEvaluationError(f"{field_name} must be a non-empty list")
    groups: list[list[str]] = []
    for group in value:
        groups.append(_string_list(group, field_name))
    return groups


def _contains_fact_marker(answer: str, marker: str) -> bool:
    """Ignore harmless whitespace/case differences, not semantic differences."""
    normalized_answer = "".join(answer.lower().split())
    normalized_marker = "".join(marker.lower().split())
    return normalized_marker in normalized_answer


def _contains_unnegated_claim(answer: str, claim: str) -> bool:
    """Detect an affirmative forbidden phrase without flagging a clear denial.

    This remains a deterministic release signal rather than semantic proof.
    A response such as "不自动安排上门取件" must not fail merely because it
    includes the substring "自动安排上门取件". Human review remains the final
    check for nuanced phrasing.
    """
    normalized_answer = "".join(answer.lower().split())
    normalized_claim = "".join(claim.lower().split())
    start = normalized_answer.find(normalized_claim)
    while start >= 0:
        # A clear Chinese denial often appears before, rather than immediately
        # adjacent to, the risky phrase: “不提供售后自动赠送积分”. Restrict
        # the search to the current clause so “不支持 A，但是会自动赠送 B”
        # still flags the affirmative claim about B.
        clause_start = max(
            normalized_answer.rfind(punctuation, 0, start)
            for punctuation in "，。；：！？!?"
        ) + 1
        clause_prefix = normalized_answer[clause_start:start]
        if not any(negation in clause_prefix for negation in _NEGATION_PREFIXES):
            return True
        start = normalized_answer.find(normalized_claim, start + 1)
    return False


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
