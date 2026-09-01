"""Structural contracts for the reviewed demo policy corpus and its evaluations.

This module deliberately validates data shape and references only.  It does
not pretend that a structurally valid policy or evaluation proves RAG quality;
the live retrieval and grounding evaluators provide that separate evidence.
"""
import json
from pathlib import Path
from typing import Any

from app.services.chunking_service import CHUNK_CONTRACT_VERSION, Chunk, chunk_directory


class KnowledgeContractError(ValueError):
    """Raised when the reviewed local corpus has an invalid contract."""


_ALLOWED_OUTCOMES = {
    "answered",
    "no_evidence",
    "retrieval_unavailable",
    "answer_generation_unavailable",
}


def validate_policy_corpus(
    knowledge_dir: Path,
    rag_cases_path: Path,
    grounding_cases_path: Path,
) -> dict[str, Any]:
    """Validate that committed evaluation references match real policy headings."""
    chunks = chunk_directory(knowledge_dir)
    section_titles = [chunk.title for chunk in chunks]
    rag_cases = _load_case_list(rag_cases_path)
    grounding_cases = _load_case_list(grounding_cases_path)
    report = validate_policy_corpus_data(section_titles, rag_cases, grounding_cases)
    chunk_errors = validate_chunk_contract(chunks)
    report["errors"].extend(chunk_errors)
    report["valid"] = not report["errors"]
    report["chunk_contract_version"] = CHUNK_CONTRACT_VERSION
    report["chunk_count"] = len(chunks)
    return report


def validate_chunk_contract(chunks: list[Chunk]) -> list[str]:
    """Validate the explicit v2 metadata that is persisted beside vectors."""

    errors: list[str] = []
    seen_chunk_ids: set[str] = set()
    source_orders: dict[str, list[int]] = {}
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"chunk #{index}"
        if not isinstance(chunk.chunk_id, str) or not chunk.chunk_id:
            errors.append(f"{prefix} has no chunk_id")
        elif chunk.chunk_id in seen_chunk_ids:
            errors.append(f"duplicate chunk_id: {chunk.chunk_id}")
        else:
            seen_chunk_ids.add(chunk.chunk_id)
        if not isinstance(chunk.text, str) or not chunk.text.strip():
            errors.append(f"{prefix} has no text")
        if not isinstance(chunk.document_id, str) or not chunk.document_id:
            errors.append(f"{prefix} has no document_id")
        if not chunk.heading_path or not all(isinstance(item, str) and item for item in chunk.heading_path):
            errors.append(f"{prefix} has no heading_path")
        if not isinstance(chunk.source_order, int) or chunk.source_order < 1:
            errors.append(f"{prefix} has invalid source_order")
        else:
            source_orders.setdefault(chunk.document_id or chunk.source, []).append(chunk.source_order)
        if not isinstance(chunk.policy_version, str) or not chunk.policy_version or chunk.policy_version == "unknown":
            errors.append(f"{prefix} has no explicit policy_version")
        if not isinstance(chunk.effective_from, str) or not chunk.effective_from or chunk.effective_from_ts <= 0:
            errors.append(f"{prefix} has no valid effective_from")
        if not isinstance(chunk.category, str) or not chunk.category:
            errors.append(f"{prefix} has no category")
        if chunk.language not in {"zh-CN", "en"}:
            errors.append(f"{prefix} has unsupported language")
        if chunk.document_type != "policy":
            errors.append(f"{prefix} has unsupported document_type")
        if not isinstance(chunk.content_hash, str) or len(chunk.content_hash) != 64:
            errors.append(f"{prefix} has invalid content_hash")
    for document_id, orders in source_orders.items():
        if sorted(orders) != list(range(1, len(orders) + 1)):
            errors.append(f"document {document_id} source_order is not contiguous")
    return errors


def validate_policy_corpus_data(
    section_titles: list[str] | set[str],
    rag_cases: list[Any],
    grounding_cases: list[Any],
) -> dict[str, Any]:
    """Validate data supplied by tests or by the committed corpus loader."""
    titles = [title.strip() for title in section_titles if isinstance(title, str) and title.strip()]
    title_set = set(titles)
    errors: list[str] = []

    if not title_set:
        errors.append("policy corpus has no non-empty sections")
    duplicate_titles = sorted({title for title in titles if titles.count(title) > 1})
    if duplicate_titles:
        errors.append(f"duplicate policy section titles: {', '.join(duplicate_titles)}")

    rag_summary = _validate_retrieval_cases(rag_cases, title_set, errors)
    grounding_summary = _validate_grounding_cases(grounding_cases, title_set, errors)
    return {
        "valid": not errors,
        "policy_section_count": len(title_set),
        "policy_sections": sorted(title_set),
        "retrieval_case_count": rag_summary["total"],
        "retrieval_supported_case_count": rag_summary["supported"],
        "retrieval_no_evidence_case_count": rag_summary["no_evidence"],
        "grounding_case_count": grounding_summary["total"],
        "grounding_answered_case_count": grounding_summary["answered"],
        "grounding_no_evidence_case_count": grounding_summary["no_evidence"],
        "errors": errors,
    }


def assert_policy_corpus_valid(
    knowledge_dir: Path,
    rag_cases_path: Path,
    grounding_cases_path: Path,
) -> dict[str, Any]:
    """Return the report or stop a build before invalid data reaches RAG."""
    report = validate_policy_corpus(
        knowledge_dir,
        rag_cases_path,
        grounding_cases_path,
    )
    if not report["valid"]:
        raise KnowledgeContractError("; ".join(report["errors"]))
    return report


def _load_case_list(path: Path) -> list[Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeContractError(
            f"unable to read {path.name}: {type(exc).__name__}"
        ) from exc
    if not isinstance(data, list):
        raise KnowledgeContractError(f"{path.name} must contain a JSON array")
    return data


def _validate_retrieval_cases(
    cases: list[Any],
    section_titles: set[str],
    errors: list[str],
) -> dict[str, int]:
    ids: set[str] = set()
    supported = 0
    no_evidence = 0
    for index, case in enumerate(cases, start=1):
        prefix = f"rag case #{index}"
        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _validate_case_identity(case, prefix, ids, errors)
        _require_text(case, "category", prefix, errors)
        _require_text(case, "question", prefix, errors)
        expected_section = case.get("expected_section")
        if expected_section is None:
            no_evidence += 1
            continue
        if not isinstance(expected_section, str) or not expected_section.strip():
            errors.append(f"{prefix}.expected_section must be a section title or null")
            continue
        supported += 1
        if expected_section not in section_titles:
            errors.append(
                f"{prefix} references missing policy section: {expected_section}"
            )
    return {"total": len(cases), "supported": supported, "no_evidence": no_evidence}


def _validate_grounding_cases(
    cases: list[Any],
    section_titles: set[str],
    errors: list[str],
) -> dict[str, int]:
    ids: set[str] = set()
    answered = 0
    no_evidence = 0
    for index, case in enumerate(cases, start=1):
        prefix = f"grounding case #{index}"
        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _validate_case_identity(case, prefix, ids, errors)
        _require_text(case, "question", prefix, errors)
        expected = case.get("expected")
        if not isinstance(expected, dict):
            errors.append(f"{prefix}.expected must be an object")
            continue
        outcome = expected.get("outcome")
        if outcome not in _ALLOWED_OUTCOMES:
            errors.append(f"{prefix}.expected.outcome is invalid")
            continue
        if outcome == "answered":
            answered += 1
            expected_sections = expected.get("source_sections_include")
            if not isinstance(expected_sections, list) or not expected_sections:
                errors.append(
                    f"{prefix} with answered outcome needs source_sections_include"
                )
            else:
                for section in expected_sections:
                    if not isinstance(section, str) or section not in section_titles:
                        errors.append(
                            f"{prefix} references missing policy section: {section}"
                        )
        if outcome == "no_evidence":
            no_evidence += 1
            if expected.get("sources_empty") is not True:
                errors.append(
                    f"{prefix} with no_evidence outcome must expect empty sources"
                )
    return {"total": len(cases), "answered": answered, "no_evidence": no_evidence}


def _validate_case_identity(
    case: dict[str, Any],
    prefix: str,
    ids: set[str],
    errors: list[str],
) -> None:
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        errors.append(f"{prefix}.id must be non-empty text")
        return
    if case_id in ids:
        errors.append(f"duplicate case id: {case_id}")
        return
    ids.add(case_id)


def _require_text(
    case: dict[str, Any],
    field: str,
    prefix: str,
    errors: list[str],
) -> None:
    value = case.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}.{field} must be non-empty text")
