"""Local embedding service for the reviewed after-sales policy index.

The demo intentionally has one embedding implementation. Different embedding
models place the same text in incompatible vector spaces, so treating a cloud
provider as a hidden fallback would make distances and thresholds meaningless.
"""

import threading
from pathlib import Path
from typing import Any

from app.config import settings


class EmbeddingServiceError(RuntimeError):
    """Raised when the packaged local embedding model cannot run."""


_local_model: Any | None = None
_local_model_signature: tuple[str, str, int] | None = None
_local_model_lock = threading.Lock()


def get_embedding(text: str) -> list[float]:
    """Embed one query with the packaged local model."""
    return get_embeddings([text])[0]


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a batch locally without any external embedding request."""
    if not texts:
        return []

    model = _get_local_model()
    try:
        raw_embeddings = list(model.embed(texts))
    except Exception as exc:  # pragma: no cover - host ONNX errors vary
        raise EmbeddingServiceError(f"本地 Embedding 模型执行失败：{exc}") from exc

    embeddings = [_to_float_list(vector) for vector in raw_embeddings]
    if len(embeddings) != len(texts) or any(not vector for vector in embeddings):
        raise EmbeddingServiceError("本地 Embedding 返回数量或内容不完整")

    expected_dimension = current_dimension()
    if any(len(vector) != expected_dimension for vector in embeddings):
        raise EmbeddingServiceError(
            "本地 Embedding 维度不匹配："
            f"期望 {expected_dimension}，实际 {[len(vector) for vector in embeddings]}"
        )
    return embeddings


def current_model_name() -> str:
    """Return the fixed model identity recorded beside the vector index."""
    return str(getattr(settings, "local_embedding_model", "BAAI/bge-small-zh-v1.5"))


def current_dimension() -> int:
    """Return the fixed local vector dimension before an index is queried."""
    return int(getattr(settings, "local_embedding_dimension", 512))


def _get_local_model() -> Any:
    global _local_model, _local_model_signature

    model_name = current_model_name()
    model_path = _resolve_local_model_path()
    threads = int(getattr(settings, "local_embedding_threads", 1))
    signature = (model_name, str(model_path), threads)

    with _local_model_lock:
        if _local_model is not None and _local_model_signature == signature:
            return _local_model

        required_files = ("model_optimized.onnx", "tokenizer.json", "config.json")
        missing = [name for name in required_files if not (model_path / name).is_file()]
        if missing:
            raise EmbeddingServiceError(
                "本地 Embedding 模型文件不完整，缺少：" + ", ".join(missing)
            )

        try:
            from fastembed import TextEmbedding

            _local_model = TextEmbedding(
                model_name=model_name,
                specific_model_path=str(model_path),
                local_files_only=True,
                providers=["CPUExecutionProvider"],
                threads=threads,
            )
        except Exception as exc:  # pragma: no cover - platform ONNX errors vary
            raise EmbeddingServiceError(f"本地 Embedding 模型加载失败：{exc}") from exc

        actual_dimension = int(getattr(_local_model, "embedding_size", 0) or 0)
        expected_dimension = current_dimension()
        if actual_dimension and actual_dimension != expected_dimension:
            raise EmbeddingServiceError(
                "本地 Embedding 模型维度不匹配："
                f"期望 {expected_dimension}，实际 {actual_dimension}"
            )

        _local_model_signature = signature
        return _local_model


def _resolve_local_model_path() -> Path:
    configured = Path(
        str(
            getattr(
                settings,
                "local_embedding_model_path",
                "models/embedding/bge-small-zh-v1.5",
            )
        )
    )
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[2] / configured


def _to_float_list(vector: Any) -> list[float]:
    values = vector.tolist() if hasattr(vector, "tolist") else list(vector)
    return [float(value) for value in values]
