"""Local ONNX Cross-Encoder reranking for approved policy candidates only."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from math import isfinite
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings
from app.schemas.rag import RetrievedChunk


class RerankerUnavailable(RuntimeError):
    """Raised when the local reranker cannot be safely used."""


_model_lock = Lock()
_model: Any | None = None
_model_signature: tuple[str, str, int] | None = None


def rerank_policy_candidates(
    query: str,
    candidates: list[RetrievedChunk],
    *,
    top_n: int | None = None,
    model_factory: Callable[..., Any] | None = None,
) -> list[RetrievedChunk]:
    """Rerank only a bounded list of already-approved policy candidates.

    The caller supplies a sanitized policy-query projection and chunks already
    obtained from the reviewed policy corpus.  This function never queries
    Java/Redis/Chroma or receives an authentication token / customer context.
    """
    if not candidates:
        return []

    limit = top_n if top_n is not None else int(settings.rag_reranker_top_n)
    if limit <= 0:
        return candidates
    reranked_input = candidates[:limit]
    model = _get_model(model_factory=model_factory)
    try:
        scores = list(model.rerank(query, [candidate.text for candidate in reranked_input]))
    except Exception as exc:  # pragma: no cover - native ONNX errors differ by host
        raise RerankerUnavailable("本地政策重排模型执行失败") from exc
    if len(scores) != len(reranked_input):
        raise RerankerUnavailable("本地政策重排模型返回数量不完整")

    ranked: list[RetrievedChunk] = []
    for candidate, raw_score in zip(reranked_input, scores):
        try:
            score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise RerankerUnavailable("本地政策重排模型返回了无效分数") from exc
        if not isfinite(score):
            raise RerankerUnavailable("本地政策重排模型返回了无效分数")
        ranked.append(
            candidate.model_copy(
                update={
                    "retrieval_method": "hybrid_rerank",
                    "rerank_score": round(score, 8),
                }
            )
        )

    ranked.sort(
        key=lambda candidate: (
            -(candidate.rerank_score or float("-inf")),
            -(candidate.rrf_score or 0.0),
            candidate.chunk_id,
        )
    )
    return [*ranked, *candidates[limit:]]


def clear_reranker_cache() -> None:
    """Test/support hook; customer requests never force a network download."""
    global _model, _model_signature
    with _model_lock:
        _model = None
        _model_signature = None


def _get_model(*, model_factory: Callable[..., Any] | None) -> Any:
    global _model, _model_signature
    model_name = str(settings.rag_reranker_model)
    model_path = _resolve_model_path()
    threads = int(settings.rag_reranker_threads)
    signature = (model_name, str(model_path), threads)

    with _model_lock:
        if model_factory is None and _model is not None and _model_signature == signature:
            return _model
        _assert_local_model_files(model_path)
        if model_factory is None:
            try:
                from fastembed.rerank.cross_encoder.text_cross_encoder import TextCrossEncoder

                model_factory = TextCrossEncoder
            except Exception as exc:  # pragma: no cover - import varies by package build
                raise RerankerUnavailable("本地政策重排依赖不可用") from exc
        try:
            model = model_factory(
                model_name,
                cache_dir=str(model_path.parent),
                specific_model_path=str(model_path),
                local_files_only=True,
                providers=["CPUExecutionProvider"],
                threads=threads,
            )
        except Exception as exc:  # pragma: no cover - model load varies by host
            raise RerankerUnavailable("本地政策重排模型不可用") from exc
        if model_factory.__module__.startswith("fastembed"):
            _model = model
            _model_signature = signature
        return model


def _resolve_model_path() -> Path:
    configured = Path(str(settings.rag_reranker_model_path))
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[2] / configured


def _assert_local_model_files(model_path: Path) -> None:
    # FastEmbed's BGE ONNX package uses this layout.  Check first so a normal
    # customer request cannot cause an implicit model download or surprise disk
    # use when an image/model mount is incomplete.
    required_files = (
        model_path / "onnx" / "model.onnx",
        model_path / "tokenizer.json",
        model_path / "config.json",
    )
    missing = [str(path.name if path.parent == model_path else path.parent.name + "/" + path.name) for path in required_files if not path.is_file()]
    if missing:
        raise RerankerUnavailable("本地政策重排模型文件不完整")
