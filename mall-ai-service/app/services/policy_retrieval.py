"""Selectable Dense / Hybrid / Hybrid+Rerank policy retrieval pipeline."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Literal

from app.config import settings
from app.schemas.rag import PolicyMetadataFilter, RetrievedChunk
from app.services.bm25_retriever import search_bm25
from app.services.cross_encoder_reranker import (
    RerankerUnavailable,
    rerank_policy_candidates,
)
from app.services.policy_query import project_policy_query
from app.services.policy_metadata import (
    resolve_published_policy_filter,
)
from app.services.vector_store import search_similar


RetrievalMode = Literal["dense", "hybrid", "hybrid_rerank"]


class PolicyRetrievalUnavailable(RuntimeError):
    """The requested safe retrieval pipeline could not establish candidates."""


@dataclass(frozen=True)
class PolicyRetrievalResult:
    """Internal-only retrieval result; it is never serialized to customers."""

    chunks: list[RetrievedChunk]
    requested_mode: RetrievalMode
    effective_mode: Literal["dense", "hybrid", "hybrid_rerank"]
    reranker_unavailable: bool = False


def retrieve_policy_candidates(
    question: str,
    top_k: int | None = None,
    *,
    mode: str | None = None,
    metadata_filter: PolicyMetadataFilter | dict | None = None,
    dense_search: Callable[[str, int | None], list[RetrievedChunk]] | None = None,
    bm25_search: Callable[[str, int], list[RetrievedChunk]] | None = None,
    rerank: Callable[[str, list[RetrievedChunk]], list[RetrievedChunk]] | None = None,
) -> PolicyRetrievalResult:
    """Retrieve only policy candidates for the requested experiment mode.

    Hybrid intentionally requires both dense and BM25 to be healthy.  A BM25
    result is not an embedding outage fallback: if either primary candidate
    stage cannot run, the customer RAG path fails closed as unavailable.
    """
    requested_mode = _validated_mode(mode or settings.rag_retrieval_mode)
    safe_query = project_policy_query(question)
    if not safe_query:
        return PolicyRetrievalResult([], requested_mode, "dense")

    output_k = max(1, int(top_k or settings.rag_top_k))
    # Every production retrieval starts with a trusted metadata scope.  A
    # caller may narrow it with a Java-derived category or an explicitly
    # configured policy version, but the model never chooses it.
    resolved_filter = resolve_published_policy_filter(metadata_filter)

    if dense_search is None:
        # Keep custom test/evaluation callbacks on the legacy two-argument
        # contract while the real store receives the server-owned filter.
        dense_search = lambda query, limit: search_similar(
            query, limit, metadata_filter=resolved_filter
        )

    if requested_mode == "dense":
        try:
            chunks = _with_dense_ranks(dense_search(safe_query, output_k))
        except Exception as exc:
            raise PolicyRetrievalUnavailable("政策向量检索暂时不可用") from exc
        return PolicyRetrievalResult(chunks[:output_k], "dense", "dense")

    if bm25_search is None:
        bm25_search = lambda query, limit: search_bm25(
            query, limit, metadata_filter=resolved_filter
        )
    candidate_k = max(output_k, int(settings.rag_hybrid_candidate_k))
    try:
        # The two independent local candidate stages run in parallel.  They
        # converge only through deterministic rank fusion below.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="policy-retrieval") as executor:
            dense_future = executor.submit(dense_search, safe_query, candidate_k)
            bm25_future = executor.submit(bm25_search, safe_query, candidate_k)
            dense_chunks = _with_dense_ranks(dense_future.result())
            bm25_chunks = _with_bm25_ranks(bm25_future.result())
    except Exception as exc:
        raise PolicyRetrievalUnavailable("混合政策检索暂时不可用") from exc

    hybrid_candidates = fuse_rrf(
        dense_chunks,
        bm25_chunks,
        rrf_k=int(settings.rag_rrf_k),
        limit=candidate_k,
    )
    if requested_mode == "hybrid":
        return PolicyRetrievalResult(
            hybrid_candidates[:output_k], "hybrid", "hybrid"
        )

    try:
        reranked = (
            rerank(safe_query, hybrid_candidates)
            if rerank is not None
            else rerank_policy_candidates(safe_query, hybrid_candidates)
        )
    except RerankerUnavailable:
        # The model is an optional experiment layer.  Falling back to the
        # already computed Hybrid candidates is safe because the existing
        # evidence verifier still owns the answer/no-answer decision.
        return PolicyRetrievalResult(
            hybrid_candidates[:output_k],
            "hybrid_rerank",
            "hybrid",
            reranker_unavailable=True,
        )
    except Exception as exc:
        raise PolicyRetrievalUnavailable("政策重排暂时不可用") from exc
    return PolicyRetrievalResult(
        reranked[:output_k], "hybrid_rerank", "hybrid_rerank"
    )


def fuse_rrf(
    dense_chunks: list[RetrievedChunk],
    bm25_chunks: list[RetrievedChunk],
    *,
    rrf_k: int,
    limit: int,
) -> list[RetrievedChunk]:
    """Fuse candidate ranks with Reciprocal Rank Fusion deterministically."""
    if rrf_k < 1:
        raise ValueError("RRF k must be at least 1")
    if limit <= 0:
        return []

    candidates: dict[str, dict[str, object]] = {}
    for rank, chunk in enumerate(dense_chunks, start=1):
        entry = candidates.setdefault(
            chunk.chunk_id,
            {"chunk": chunk, "dense_rank": None, "bm25_rank": None, "bm25_score": None, "score": 0.0},
        )
        entry["chunk"] = chunk
        entry["dense_rank"] = chunk.dense_rank or rank
        entry["score"] = float(entry["score"]) + 1 / (rrf_k + (chunk.dense_rank or rank))

    for rank, chunk in enumerate(bm25_chunks, start=1):
        entry = candidates.setdefault(
            chunk.chunk_id,
            {"chunk": chunk, "dense_rank": None, "bm25_rank": None, "bm25_score": None, "score": 0.0},
        )
        entry["bm25_rank"] = chunk.bm25_rank or rank
        entry["bm25_score"] = chunk.bm25_score
        entry["score"] = float(entry["score"]) + 1 / (rrf_k + (chunk.bm25_rank or rank))

    fused: list[RetrievedChunk] = []
    for entry in candidates.values():
        original = entry["chunk"]
        if not isinstance(original, RetrievedChunk):  # defensive narrowing
            continue
        fused.append(
            original.model_copy(
                update={
                    "retrieval_method": "hybrid",
                    "dense_rank": entry["dense_rank"],
                    "bm25_rank": entry["bm25_rank"],
                    "bm25_score": entry["bm25_score"],
                    "rrf_score": round(float(entry["score"]), 10),
                }
            )
        )
    fused.sort(
        key=lambda chunk: (
            -(chunk.rrf_score or 0.0),
            min(
                value
                for value in (chunk.dense_rank, chunk.bm25_rank)
                if value is not None
            ),
            chunk.chunk_id,
        )
    )
    return fused[:limit]


def is_evidence_candidate(
    chunk: RetrievedChunk,
    *,
    max_dense_distance: float | None = None,
    min_bm25_score: float | None = None,
) -> bool:
    """Apply the candidate gate before semantic evidence verification.

    Dense candidates retain the calibrated cosine-distance gate.  Hybrid may
    additionally admit a non-zero, calibrated BM25 exact-term hit so that a
    relevant terminology match is not discarded solely because it fell outside
    dense Top-K.  This is still only candidate admission: the existing LLM
    evidence verifier must independently select explicit supporting chunks.
    """
    dense_limit = (
        settings.rag_max_distance
        if max_dense_distance is None
        else max_dense_distance
    )
    bm25_limit = (
        settings.rag_bm25_min_score if min_bm25_score is None else min_bm25_score
    )
    dense_eligible = chunk.dense_rank is not None and chunk.distance <= dense_limit
    # Legacy unit fixtures and direct dense retrieval calls do not always carry
    # a dense rank.  Their distance still has the historical meaning.
    if chunk.retrieval_method == "dense" and chunk.distance <= dense_limit:
        dense_eligible = True
    lexical_eligible = (
        chunk.bm25_rank is not None
        and chunk.bm25_score is not None
        and chunk.bm25_score >= bm25_limit
    )
    return dense_eligible or lexical_eligible


def _validated_mode(value: str) -> RetrievalMode:
    if value in {"dense", "hybrid", "hybrid_rerank"}:
        return value
    raise PolicyRetrievalUnavailable("未配置受支持的政策检索模式")


def _with_dense_ranks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return [
        chunk.model_copy(
            update={
                "retrieval_method": "dense",
                "dense_rank": chunk.dense_rank or rank,
            }
        )
        for rank, chunk in enumerate(chunks, start=1)
    ]


def _with_bm25_ranks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return [
        chunk.model_copy(
            update={
                "retrieval_method": "bm25",
                "bm25_rank": chunk.bm25_rank or rank,
            }
        )
        for rank, chunk in enumerate(chunks, start=1)
    ]
