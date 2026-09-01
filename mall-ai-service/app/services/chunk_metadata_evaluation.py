"""Deterministic RAG chunk-structure and metadata-pre-filter evaluation.

This suite is intentionally separate from Build 20's 52-case Dense ranking
suite.  It replays only versioned synthetic Markdown documents and proves that
the chunk contract and hard metadata filtering behave as designed.  It never
loads customer data, Chroma, Java, Redis, or an LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas.rag import PolicyMetadataFilter
from app.services.bm25_retriever import BM25PolicyIndex
from app.services.chunking_service import Chunk, chunk_markdown_text
from app.services.policy_metadata import chunk_matches_filter


DEFAULT_SUITE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "rag_chunk_metadata_cases.v1.json"
)


class ChunkMetadataEvaluationError(ValueError):
    """The committed synthetic suite is malformed."""


def load_chunk_metadata_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    try:
        suite = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChunkMetadataEvaluationError("无法读取 Chunk Metadata 评测集。") from exc
    if not isinstance(suite, dict):
        raise ChunkMetadataEvaluationError("Chunk Metadata 评测集必须是对象。")
    if suite.get("schema_version") != "1" or not isinstance(suite.get("suite_version"), str):
        raise ChunkMetadataEvaluationError("Chunk Metadata 评测集版本不正确。")
    documents = suite.get("documents")
    cases = suite.get("cases")
    if not isinstance(documents, list) or not documents:
        raise ChunkMetadataEvaluationError("Chunk Metadata 评测集缺少合成文档。")
    if not isinstance(cases, list) or not cases:
        raise ChunkMetadataEvaluationError("Chunk Metadata 评测集缺少案例。")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("file_name"), str)
        or not isinstance(item.get("content"), str)
        for item in documents
    ):
        raise ChunkMetadataEvaluationError("合成文档字段不正确。")
    case_ids = [item.get("case_id") for item in cases if isinstance(item, dict)]
    if len(case_ids) != len(cases) or any(not isinstance(item, str) or not item for item in case_ids):
        raise ChunkMetadataEvaluationError("评测案例编号不正确。")
    if len(set(case_ids)) != len(case_ids):
        raise ChunkMetadataEvaluationError("评测案例编号重复。")
    return suite


def evaluate_chunk_metadata_suite(suite: dict[str, Any]) -> dict[str, Any]:
    """Evaluate structural grouping plus trusted pre-filter semantics."""

    documents = suite["documents"]
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(
            chunk_markdown_text(document["content"], source=document["file_name"])
        )
    bm25 = BM25PolicyIndex(chunks)
    results: list[dict[str, Any]] = []

    for case in suite["cases"]:
        results.append(_evaluate_case(case, chunks, bm25))

    failed = sum(result["status"] == "FAILED" for result in results)
    return {
        "suite_version": suite["suite_version"],
        "status": "passed" if not failed else "quality_failed",
        "total_cases": len(results),
        "passed_cases": len(results) - failed,
        "failed_cases": failed,
        "synthetic_chunk_count": len(chunks),
        "results": results,
        "cost": {
            "external_model_calls": 0,
            "estimated_external_cost": 0.0,
            "currency": "CNY",
            "note": "Chunking, Metadata filter and BM25 synthetic contract are local and deterministic.",
        },
    }


def _evaluate_case(
    case: dict[str, Any],
    chunks: list[Chunk],
    bm25: BM25PolicyIndex,
) -> dict[str, Any]:
    errors: list[str] = []
    case_id = case["case_id"]
    try:
        metadata_filter = PolicyMetadataFilter.model_validate(
            # JSON dates are ISO strings; schema validation normalizes them
            # into ``date`` before the deterministic comparison below.
            case.get("metadata_filter", {})
        )
    except Exception:
        return {"case_id": case_id, "status": "FAILED", "violations": ["invalid_metadata_filter"]}

    selected = [
        chunk for chunk in chunks if chunk_matches_filter(chunk, metadata_filter)
    ]
    actual_document_ids = sorted({chunk.document_id for chunk in selected})
    expected_document_ids = case.get("expected_document_ids")
    if not isinstance(expected_document_ids, list) or not all(
        isinstance(item, str) for item in expected_document_ids
    ):
        errors.append("invalid_expected_document_ids")
    elif actual_document_ids != sorted(expected_document_ids):
        errors.append("metadata_scope_mismatch")

    expected_titles = case.get("expected_section_titles", [])
    if not isinstance(expected_titles, list) or not all(isinstance(item, str) for item in expected_titles):
        errors.append("invalid_expected_section_titles")
    else:
        actual_titles = {chunk.title for chunk in selected}
        if not set(expected_titles).issubset(actual_titles):
            errors.append("expected_section_missing")

    keep_together = case.get("must_keep_together", [])
    if not isinstance(keep_together, list) or not all(isinstance(item, str) for item in keep_together):
        errors.append("invalid_keep_together_contract")
    elif keep_together and not any(
        all(marker in chunk.text for marker in keep_together) for chunk in selected
    ):
        errors.append("rule_structure_split")

    query = case.get("query")
    expected_top = case.get("expected_top_document_id")
    if query is not None and not isinstance(query, str):
        errors.append("invalid_query")
    elif expected_top is not None and not isinstance(expected_top, str):
        errors.append("invalid_expected_top_document_id")
    elif isinstance(query, str):
        hits = bm25.search(query, top_k=3, metadata_filter=metadata_filter)
        top_document_id = hits[0].document_id if hits else None
        if expected_top is not None and top_document_id != expected_top:
            errors.append("filtered_colloquial_query_miss")
        if not actual_document_ids and hits:
            errors.append("empty_filter_returned_candidate")

    return {
        "case_id": case_id,
        "status": "PASSED" if not errors else "FAILED",
        "violations": errors,
        "selected_document_ids": actual_document_ids,
        "selected_chunk_count": len(selected),
    }
