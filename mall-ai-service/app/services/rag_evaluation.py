"""Deterministic retrieval evaluation helpers for the after-sales knowledge base."""
import json
from collections.abc import Callable
from pathlib import Path

from app.config import settings
from app.schemas.rag import RetrievedChunk
from app.services.vector_store import search_similar


def load_rag_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_rag_cases(
    cases: list[dict],
    search: Callable[[str, int], list[RetrievedChunk]] = search_similar,
    top_k: int = 3,
    max_distance: float | None = None,
    batch_search: Callable[[list[str], int], list[list[RetrievedChunk]]] | None = None,
) -> dict:
    """Measure raw retrieval and the evidence gate used by the RAG service.

    A correct section in Top-K is useful, but it is not enough for this
    application: the answer service will refuse chunks beyond its configured
    distance threshold.  Report both values so a raw Recall@K score cannot
    overstate user-visible coverage.
    """
    results: list[dict] = []
    supported_cases = [case for case in cases if case.get("expected_section")]
    no_evidence_cases = [case for case in cases if not case.get("expected_section")]
    evidence_max_distance = (
        settings.rag_max_distance if max_distance is None else max_distance
    )

    chunk_groups = (
        batch_search([case["question"] for case in cases], top_k)
        if batch_search is not None
        else [search(case["question"], top_k) for case in cases]
    )
    if len(chunk_groups) != len(cases):
        raise ValueError("Batch retrieval result count does not match evaluation cases")

    for case, chunks in zip(cases, chunk_groups):
        expected_section = case.get("expected_section")
        hit = bool(
            expected_section
            and any(expected_section in chunk.section_path for chunk in chunks)
        )
        evidence_chunks = [
            chunk for chunk in chunks if chunk.distance <= evidence_max_distance
        ]
        evidence_hit = bool(
            expected_section
            and any(
                expected_section in chunk.section_path for chunk in evidence_chunks
            )
        )
        no_evidence_pass = bool(
            not expected_section and not evidence_chunks
        )
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "expected_section": expected_section,
                "hit": hit,
                "evidence_hit": evidence_hit,
                "no_evidence_pass": no_evidence_pass,
                "retrieved_sections": [chunk.section_path for chunk in chunks],
                "retrieved_distances": [chunk.distance for chunk in chunks],
                "evidence_sections": [
                    chunk.section_path for chunk in evidence_chunks
                ],
            }
        )

    hit_count = sum(1 for result in results if result["hit"])
    evidence_hit_count = sum(1 for result in results if result["evidence_hit"])
    no_evidence_pass_count = sum(
        1 for result in results if result["no_evidence_pass"]
    )
    return {
        "total_cases": len(cases),
        "supported_cases": len(supported_cases),
        "retrieval_hits": hit_count,
        "recall_at_k": (hit_count / len(supported_cases)) if supported_cases else 0.0,
        "evidence_max_distance": evidence_max_distance,
        "evidence_retrieval_hits": evidence_hit_count,
        "evidence_recall_at_k": (
            evidence_hit_count / len(supported_cases)
            if supported_cases
            else 0.0
        ),
        "no_evidence_cases": len(no_evidence_cases),
        "no_evidence_passes": no_evidence_pass_count,
        "no_evidence_pass_rate": (
            no_evidence_pass_count / len(no_evidence_cases)
            if no_evidence_cases
            else 0.0
        ),
        "results": results,
    }
