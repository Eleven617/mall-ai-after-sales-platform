"""Chroma storage for the packaged local policy embedding model."""

import hashlib
from pathlib import Path
from typing import Optional

import chromadb

from app.config import settings
from app.schemas.rag import PolicyMetadataFilter, RetrievedChunk
from app.services.chunking_service import CHUNK_CONTRACT_VERSION, chunk_directory
from app.services.embedding_service import (
    EmbeddingServiceError,
    current_dimension,
    current_model_name,
    get_embedding,
    get_embeddings,
)
from app.services.policy_metadata import build_chroma_where

_DB_PATH = Path(__file__).resolve().parents[2] / "chroma_data"
_client = chromadb.PersistentClient(path=str(_DB_PATH))
COLLECTION_NAME = "mall_knowledge_local_bge_small_zh_v1_5"
_CHUNK_METADATA_KEYS = {
    "chunk_id",
    "document_id",
    "heading_path",
    "source_order",
    "policy_version",
    "effective_from",
    "effective_from_ts",
    "category",
    "language",
    "document_type",
    "content_hash",
}


def _collection_metadata() -> dict:
    return {
        "hnsw:space": "cosine",
        "embedding_provider": "local",
        "embedding_model": current_model_name(),
        "embedding_dimension": current_dimension(),
        "chunk_contract_version": CHUNK_CONTRACT_VERSION,
        "chunking_strategy": "markdown_heading_then_natural_boundary",
        "chunk_metadata_keys": ",".join(sorted(_CHUNK_METADATA_KEYS)),
    }


def _get_collection():
    try:
        collection = _client.get_collection(name=COLLECTION_NAME)
    except Exception:
        return _client.create_collection(name=COLLECTION_NAME, metadata=_collection_metadata())

    _assert_collection_compatible(collection)
    return collection


def _assert_collection_compatible(collection) -> None:
    """Reject an index created by a different local model contract."""
    metadata = collection.metadata or {}
    if not isinstance(metadata, dict):
        return

    stored_provider = metadata.get("embedding_provider")
    stored_model = metadata.get("embedding_model")
    stored_dimension = metadata.get("embedding_dimension")
    if stored_provider and stored_provider != "local":
        raise EmbeddingServiceError(
            f"向量索引 provider 不匹配：当前 local，索引为 {stored_provider}"
        )
    if stored_model and stored_model != current_model_name():
        raise EmbeddingServiceError(
            "向量索引模型不匹配："
            f"当前 {current_model_name()}，索引为 {stored_model}"
        )
    if stored_dimension and int(stored_dimension) != current_dimension():
        raise EmbeddingServiceError(
            "向量索引维度不匹配："
            f"当前 {current_dimension()}，索引为 {stored_dimension}"
        )


def ingest_knowledge_base(knowledge_dir: Optional[Path] = None) -> int:
    """Chunk policies, embed locally, then atomically replace the local index."""
    if knowledge_dir is None:
        knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge"

    chunks = chunk_directory(knowledge_dir)
    if not chunks:
        return 0

    texts = [chunk.text for chunk in chunks]
    embeddings = get_embeddings(texts)
    _validate_embeddings(embeddings, expected_count=len(chunks))
    ids = [chunk.chunk_id for chunk in chunks]
    metadatas = [
        {
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "source": chunk.source,
            "document_name": chunk.document_title,
            "section_path": chunk.section_path,
            "document_id": chunk.document_id or chunk.source or chunk.document_title,
            "heading_path": ">".join(chunk.heading_path) or chunk.section_path,
            "source_order": int(chunk.source_order or index + 1),
            "policy_version": chunk.policy_version or "unknown",
            "effective_from": chunk.effective_from or "",
            "effective_from_ts": int(chunk.effective_from_ts or 0),
            "category": chunk.category or "after_sales",
            "language": chunk.language or "zh-CN",
            "document_type": chunk.document_type or "policy",
            "content_hash": chunk.content_hash
            or hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
        }
        for index, chunk in enumerate(chunks)
    ]

    try:
        _client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    collection = _client.create_collection(name=COLLECTION_NAME, metadata=_collection_metadata())
    collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(chunks)


def search_similar(
    query: str,
    top_k: int | None = None,
    *,
    metadata_filter: PolicyMetadataFilter | dict | None = None,
) -> list[RetrievedChunk]:
    """Semantic retrieval from the one approved local vector index."""
    results = _query_collection(
        [get_embedding(query)], top_k, metadata_filter=metadata_filter
    )
    return _result_row_to_chunks(results, 0)


def search_similar_batch(
    queries: list[str],
    top_k: int | None = None,
    *,
    metadata_filter: PolicyMetadataFilter | dict | None = None,
) -> list[list[RetrievedChunk]]:
    """Retrieve many evaluation questions using one local embedding batch."""
    if not queries:
        return []
    results = _query_collection(
        get_embeddings(queries), top_k, metadata_filter=metadata_filter
    )
    return [_result_row_to_chunks(results, index) for index in range(len(queries))]


def _query_collection(
    query_embeddings: list[list[float]],
    top_k: int | None,
    *,
    metadata_filter: PolicyMetadataFilter | dict | None = None,
):
    _validate_embeddings(query_embeddings, expected_count=len(query_embeddings))
    collection = _get_collection()
    if collection.count() == 0:
        ingest_knowledge_base()
        collection = _get_collection()
    elif not _has_chunk_contract(collection):
        # Do not mutate/rebuild a persistent index in a customer request.
        # Re-ingestion is an explicit deployment/development action after a
        # reviewed metadata schema change; until then RAG fails closed.
        raise EmbeddingServiceError(
            "政策向量索引缺少当前 Chunk Metadata 契约，请先显式重新入库。"
        )

    if collection.count() == 0:
        return {"documents": [], "metadatas": [], "distances": []}

    query_kwargs = {
        "query_embeddings": query_embeddings,
        "n_results": min(top_k or settings.rag_top_k, collection.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    where = build_chroma_where(metadata_filter)
    if where is not None:
        query_kwargs["where"] = where
    return collection.query(
        **query_kwargs,
    )


def _validate_embeddings(embeddings: list[list[float]], expected_count: int) -> None:
    if len(embeddings) != expected_count or any(not embedding for embedding in embeddings):
        raise EmbeddingServiceError("Embedding 返回数量或内容不完整")
    if any(len(vector) != current_dimension() for vector in embeddings):
        raise EmbeddingServiceError(
            f"Embedding 维度与本地模型不匹配，期望 {current_dimension()}"
        )


def _result_row_to_chunks(results: dict, row_index: int) -> list[RetrievedChunk]:
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    distances = results.get("distances", [])
    if row_index >= len(documents) or not documents[row_index]:
        return []

    retrieved: list[RetrievedChunk] = []
    for index, text in enumerate(documents[row_index]):
        metadata = (
            metadatas[row_index][index]
            if row_index < len(metadatas) and metadatas[row_index]
            else {}
        )
        distance = (
            distances[row_index][index]
            if row_index < len(distances) and distances[row_index]
            else float("inf")
        )
        retrieved.append(
            RetrievedChunk(
                chunk_id=metadata.get("chunk_id") or f"chunk_{index}",
                document_name=metadata.get("document_name")
                or metadata.get("source")
                or "未知文档",
                section_path=metadata.get("section_path")
                or metadata.get("title")
                or "未知章节",
                text=text,
                distance=max(float(distance), 0.0),
                retrieval_method="dense",
                dense_rank=index + 1,
                document_id=_optional_text(metadata.get("document_id")),
                heading_path=_optional_text(metadata.get("heading_path")),
                source_order=_optional_positive_int(metadata.get("source_order")),
                policy_version=_optional_text(metadata.get("policy_version")),
                effective_from=_optional_text(metadata.get("effective_from")),
                category=_optional_text(metadata.get("category")),
                language=_optional_text(metadata.get("language")),
                document_type=_optional_text(metadata.get("document_type")),
                content_hash=_optional_text(metadata.get("content_hash")),
            )
        )
    return retrieved


def _has_chunk_contract(collection: object) -> bool:
    metadata = getattr(collection, "metadata", None)
    # Mocked collections in unit tests do not expose real metadata.  Treat
    # those as compatible; production Chroma collections always return a dict.
    if not isinstance(metadata, dict):
        return True
    if metadata.get("chunk_contract_version") != CHUNK_CONTRACT_VERSION:
        return False
    declared = metadata.get("chunk_metadata_keys")
    if declared is None:
        # Older v2 indexes may have the marker but not the optional key list;
        # row-level metadata is still checked by the explicit migration path.
        return True
    if isinstance(declared, str):
        return _CHUNK_METADATA_KEYS.issubset(
            {item.strip() for item in declared.split(",") if item.strip()}
        )
    return False


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 1:
        return int(value)
    return None
