"""Shared, server-owned policy metadata filtering helpers.

Metadata filters are deliberately separate from model prompts.  They are
constructed by trusted application code (for example a Java-verified product
category or an explicit policy version), validated here, and then applied
before dense retrieval.  An LLM never gets to widen or invent this scope.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from app.schemas.rag import PolicyMetadataFilter
from app.services.chunking_service import Chunk
from app.config import settings


def coerce_policy_metadata_filter(
    value: PolicyMetadataFilter | dict[str, Any] | None,
) -> PolicyMetadataFilter | None:
    if value is None:
        return None
    if isinstance(value, PolicyMetadataFilter):
        return value
    return PolicyMetadataFilter.model_validate(value)


def default_published_policy_filter(
    *,
    today: date | None = None,
) -> PolicyMetadataFilter:
    """Return the trusted default scope for customer policy retrieval.

    The active version comes from deployment configuration, not a request or
    model.  Category intentionally remains unset: the current Java order
    snapshot has no canonical product-category field, so applying one would
    fabricate a hard filter.  Once Java supplies it, a trusted caller can pass
    ``PolicyMetadataFilter(category=...)`` explicitly.
    """

    return PolicyMetadataFilter(
        policy_version=getattr(settings, "rag_active_policy_version", None),
        effective_on_or_before=today or date.today(),
        language=str(getattr(settings, "rag_policy_language", "zh-CN")),
        document_type=str(getattr(settings, "rag_policy_document_type", "policy")),
    )


def resolve_published_policy_filter(
    value: PolicyMetadataFilter | dict[str, Any] | None,
    *,
    today: date | None = None,
) -> PolicyMetadataFilter:
    """Merge a trusted narrowing request with the published default scope.

    Omitting a field never drops the version/language/type/effective-date
    gate.  A caller may add a Java-derived category, choose another explicitly
    authorized version, or tighten the date; a future date cannot widen the
    default effective-date ceiling.
    """

    base = default_published_policy_filter(today=today)
    requested = coerce_policy_metadata_filter(value)
    if requested is None:
        return base
    base_date = base.effective_on_or_before
    requested_date = requested.effective_on_or_before
    effective_date = (
        min(base_date, requested_date)
        if base_date is not None and requested_date is not None
        else requested_date or base_date
    )
    return PolicyMetadataFilter(
        policy_version=requested.policy_version or base.policy_version,
        effective_on_or_before=effective_date,
        category=requested.category,
        language=requested.language or base.language,
        document_type=requested.document_type or base.document_type,
    )


def build_chroma_where(
    value: PolicyMetadataFilter | dict[str, Any] | None,
) -> dict[str, Any] | None:
    selected = coerce_policy_metadata_filter(value)
    if selected is None:
        return None

    clauses: list[dict[str, Any]] = []
    for key in ("policy_version", "category", "language", "document_type"):
        field_value = getattr(selected, key)
        if field_value is not None:
            clauses.append({key: {"$eq": field_value}})
    if selected.effective_on_or_before is not None:
        clauses.append(
            {
                "effective_from_ts": {
                    "$lte": _date_to_timestamp(selected.effective_on_or_before)
                }
            }
        )
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def chunk_matches_filter(
    chunk: Chunk,
    value: PolicyMetadataFilter | dict[str, Any] | None,
) -> bool:
    selected = coerce_policy_metadata_filter(value)
    if selected is None:
        return True
    if selected.policy_version is not None and chunk.policy_version != selected.policy_version:
        return False
    if selected.category is not None and chunk.category != selected.category:
        return False
    if selected.language is not None and chunk.language != selected.language:
        return False
    if selected.document_type is not None and chunk.document_type != selected.document_type:
        return False
    if selected.effective_on_or_before is not None:
        effective_ts = int(chunk.effective_from_ts or 0)
        if effective_ts <= 0 or effective_ts > _date_to_timestamp(selected.effective_on_or_before):
            return False
    return True


def _date_to_timestamp(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())
