"""A/B evaluation for the semantic policy-evidence verifier."""
from collections.abc import Callable, Iterable
from typing import Any

from app.config import settings
from app.schemas.rag import RetrievedChunk
from app.services.rag_evidence_verifier import (
    EvidenceVerificationError,
    verify_policy_evidence,
)
from app.services.vector_store import search_similar_batch


def evaluate_rag_verifier_cases(
    cases: Iterable[dict[str, Any]],
    batch_search: Callable[[list[str], int], list[list[RetrievedChunk]]] = search_similar_batch,
    verifier: Callable[[str, list[RetrievedChunk]], list[RetrievedChunk]] = verify_policy_evidence,
    top_k: int = 3,
    max_distance: float | None = None,
) -> dict[str, Any]:
    """Measure whether semantic verification improves the existing evidence gate.

    This report intentionally stores case IDs and section paths only. It does
    not emit arbitrary user questions, model responses, or policy prose.
    """
    case_list = list(cases)
    candidate_groups = batch_search([case["question"] for case in case_list], top_k)
    if len(candidate_groups) != len(case_list):
        raise ValueError("Batch retrieval result count does not match verifier cases")

    threshold = settings.rag_max_distance if max_distance is None else max_distance
    reports: list[dict[str, Any]] = []
    for case, chunks in zip(case_list, candidate_groups):
        expected_section = case.get("expected_section")
        candidates = [chunk for chunk in chunks if chunk.distance <= threshold]
        try:
            approved = verifier(case["question"], candidates)
        except EvidenceVerificationError:
            reports.append(
                {
                    "id": case["id"],
                    "status": "environment_blocked",
                    "expected_kind": "supported" if expected_section else "no_evidence",
                }
            )
            continue

        if expected_section:
            passed = any(expected_section in chunk.section_path for chunk in approved)
        else:
            passed = not approved
        reports.append(
            {
                "id": case["id"],
                "status": "evaluated",
                "expected_kind": "supported" if expected_section else "no_evidence",
                "passed": passed,
                "approved_sections": [chunk.section_path for chunk in approved],
            }
        )

    evaluated = [report for report in reports if report["status"] == "evaluated"]
    supported = [
        report for report in evaluated if report["expected_kind"] == "supported"
    ]
    no_evidence = [
        report for report in evaluated if report["expected_kind"] == "no_evidence"
    ]
    supported_passes = sum(1 for report in supported if report["passed"])
    no_evidence_passes = sum(1 for report in no_evidence if report["passed"])
    return {
        "mode": "semantic_evidence_verifier",
        "status": "environment_blocked" if len(evaluated) != len(reports) else "completed",
        "evidence_max_distance": threshold,
        "total_cases": len(reports),
        "evaluated_cases": len(evaluated),
        "environment_blocked_cases": len(reports) - len(evaluated),
        "supported_cases": len(supported),
        "supported_passes": supported_passes,
        "supported_pass_rate": _ratio(supported_passes, len(supported)),
        "no_evidence_cases": len(no_evidence),
        "no_evidence_passes": no_evidence_passes,
        "no_evidence_pass_rate": _ratio(no_evidence_passes, len(no_evidence)),
        "cases": reports,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
