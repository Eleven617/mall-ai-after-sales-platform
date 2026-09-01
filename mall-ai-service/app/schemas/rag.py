from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PolicyMetadataFilter(BaseModel):
    """Server-owned hard filters for policy retrieval.

    This is an internal retrieval contract, not an LLM output.  Callers may
    supply a policy version, effective-date ceiling, business category,
    language, or document type; unknown fields and blank values are rejected
    before they can reach Chroma.
    """

    model_config = ConfigDict(extra="forbid")

    policy_version: str | None = Field(default=None, min_length=1, max_length=32)
    effective_on_or_before: date | None = None
    category: str | None = Field(default=None, min_length=1, max_length=64)
    language: Literal["zh-CN", "zh", "en"] | None = None
    document_type: Literal["policy"] | None = None


class RetrievedChunk(BaseModel):
    """A retrieval result with metadata from the vector store."""

    chunk_id: str
    document_name: str
    section_path: str
    text: str
    distance: float = Field(ge=0)
    # These fields stay inside the AI service.  Customer DTO projection uses
    # RagSource and does not expose retrieval strategy or ranking telemetry.
    retrieval_method: str = "dense"
    dense_rank: int | None = Field(default=None, ge=1)
    bm25_rank: int | None = Field(default=None, ge=1)
    bm25_score: float | None = Field(default=None, ge=0)
    rrf_score: float | None = Field(default=None, ge=0)
    rerank_score: float | None = None
    # Internal-only chunk contract metadata.  Customer/public DTOs continue
    # to project through RagSource and never serialize these fields.
    document_id: str | None = None
    heading_path: str | None = None
    source_order: int | None = Field(default=None, ge=1)
    policy_version: str | None = None
    effective_from: str | None = None
    category: str | None = None
    language: str | None = None
    document_type: str | None = None
    content_hash: str | None = None


class RagSource(BaseModel):
    """Evidence returned to the API/UI. It is created from retrieval metadata."""

    chunk_id: str
    document_name: str
    section_path: str
    distance: float = Field(ge=0)
