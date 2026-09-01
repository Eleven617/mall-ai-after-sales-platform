import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.schemas.rag import PolicyMetadataFilter, RetrievedChunk
from app.services.chunking_service import Chunk
from app.services.embedding_service import EmbeddingServiceError, get_embedding, get_embeddings
from app.services.vector_store import COLLECTION_NAME, ingest_knowledge_base, search_similar_batch


class _FakeLocalModel:
    embedding_size = 512

    def embed(self, texts: list[str]):
        return [[float(index + 1)] * 512 for index, _text in enumerate(texts)]


class EmbeddingAndVectorStoreTests(unittest.TestCase):
    def test_single_query_uses_the_same_local_batch_path(self) -> None:
        with patch(
            "app.services.embedding_service.get_embeddings",
            return_value=[[0.1] * 512],
        ) as get_embeddings_mock:
            embedding = get_embedding("one query")

        self.assertEqual([0.1] * 512, embedding)
        get_embeddings_mock.assert_called_once_with(["one query"])

    def test_local_provider_embeds_without_any_http_dependency(self) -> None:
        test_settings = SimpleNamespace(
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_model_path="models/embedding/bge-small-zh-v1.5",
            local_embedding_dimension=512,
            local_embedding_threads=1,
        )
        with patch("app.services.embedding_service.settings", test_settings), patch(
            "app.services.embedding_service._get_local_model",
            return_value=_FakeLocalModel(),
        ):
            embeddings = get_embeddings(["本地向量", "第二条"])

        self.assertEqual(2, len(embeddings))
        self.assertEqual(512, len(embeddings[0]))

    def test_local_model_missing_files_fails_closed(self) -> None:
        test_settings = SimpleNamespace(
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_model_path="models/embedding/missing-model",
            local_embedding_dimension=512,
            local_embedding_threads=1,
        )
        with patch("app.services.embedding_service.settings", test_settings):
            with self.assertRaisesRegex(EmbeddingServiceError, "模型文件不完整"):
                get_embeddings(["本地向量"])

    def test_local_collection_metadata_records_its_vector_contract(self) -> None:
        with patch(
            "app.services.vector_store.current_model_name",
            return_value="BAAI/bge-small-zh-v1.5",
        ), patch("app.services.vector_store.current_dimension", return_value=512):
            from app.services.vector_store import _collection_metadata

            metadata = _collection_metadata()

        self.assertEqual("local", metadata["embedding_provider"])
        self.assertEqual("BAAI/bge-small-zh-v1.5", metadata["embedding_model"])
        self.assertEqual(512, metadata["embedding_dimension"])

    def test_embedding_failure_keeps_the_previous_collection_untouched(self) -> None:
        chunk = Chunk(
            text="policy > section\ncontent",
            title="section",
            source="policy.md",
            document_title="policy",
            section_path="policy > section",
            chunk_id="chunk-1",
        )
        client = Mock()
        with patch("app.services.vector_store.chunk_directory", return_value=[chunk]), patch(
            "app.services.vector_store.get_embeddings",
            side_effect=EmbeddingServiceError("local model unavailable"),
        ), patch("app.services.vector_store._client", client):
            with self.assertRaises(EmbeddingServiceError):
                ingest_knowledge_base()

        client.delete_collection.assert_not_called()
        client.create_collection.assert_not_called()

    def test_batch_search_keeps_each_query_row_separate(self) -> None:
        collection = Mock()
        collection.count.return_value = 2
        collection.query.return_value = {
            "documents": [["first policy"], ["second policy"]],
            "metadatas": [
                [{"chunk_id": "one", "document_name": "policy", "section_path": "policy > one"}],
                [{"chunk_id": "two", "document_name": "policy", "section_path": "policy > two"}],
            ],
            "distances": [[0.1], [0.2]],
        }
        client = Mock()
        client.get_collection.return_value = collection
        with patch("app.services.vector_store._client", client), patch(
            "app.services.vector_store.get_embeddings",
            return_value=[[0.1] * 512, [0.2] * 512],
        ), patch("app.services.vector_store.current_dimension", return_value=512):
            results = search_similar_batch(["question one", "question two"], top_k=3)

        self.assertEqual(2, len(results))
        self.assertEqual("policy > one", results[0][0].section_path)
        self.assertEqual("policy > two", results[1][0].section_path)
        self.assertIsInstance(results[0][0], RetrievedChunk)
        self.assertEqual("mall_knowledge_local_bge_small_zh_v1_5", COLLECTION_NAME)

    def test_dense_search_applies_structured_metadata_before_vector_query(self) -> None:
        collection = Mock()
        collection.metadata = {
            "embedding_provider": "local",
            "embedding_model": "BAAI/bge-small-zh-v1.5",
            "embedding_dimension": 512,
            "chunk_contract_version": "chunk-v2",
            "chunk_metadata_keys": (
                "category,chunk_id,content_hash,document_id,document_type,effective_from,"
                "effective_from_ts,heading_path,language,policy_version,source_order"
            ),
        }
        collection.count.return_value = 1
        collection.query.return_value = {
            "documents": [["政策 > 退货运费\n质量问题退货运费由商家承担。"]],
            "metadatas": [[{
                "chunk_id": "shipping-v2",
                "document_id": "shipping_v2",
                "document_name": "政策",
                "section_path": "政策 > 退货运费",
                "heading_path": "退货运费",
                "source_order": 1,
                "policy_version": "V2.0",
                "effective_from": "2026-08-20",
                "effective_from_ts": 1787184000,
                "category": "electronics",
                "language": "zh-CN",
                "document_type": "policy",
                "content_hash": "a" * 64,
            }]],
            "distances": [[0.1]],
        }
        client = Mock()
        client.get_collection.return_value = collection
        selected = PolicyMetadataFilter(
            policy_version="V2.0",
            effective_on_or_before=date(2026, 8, 28),
            category="electronics",
            language="zh-CN",
            document_type="policy",
        )

        with patch("app.services.vector_store._client", client), patch(
            "app.services.vector_store.get_embedding", return_value=[0.1] * 512
        ), patch("app.services.vector_store.current_dimension", return_value=512):
            from app.services.vector_store import search_similar

            hits = search_similar("质量问题退货运费", metadata_filter=selected)

        where = collection.query.call_args.kwargs["where"]
        self.assertIn("$and", where)
        self.assertIn({"policy_version": {"$eq": "V2.0"}}, where["$and"])
        self.assertIn({"category": {"$eq": "electronics"}}, where["$and"])
        self.assertEqual("shipping_v2", hits[0].document_id)
        self.assertEqual("V2.0", hits[0].policy_version)
        self.assertEqual("electronics", hits[0].category)

    def test_legacy_chunk_index_fails_closed_without_customer_request_reingestion(self) -> None:
        """A query must not delete/rebuild a persistent index with an old contract."""
        collection = Mock()
        collection.metadata = {
            "embedding_provider": "local",
            "embedding_model": "BAAI/bge-small-zh-v1.5",
            "embedding_dimension": 512,
            # Deliberately no ``chunk_contract_version``: this is a legacy index.
        }
        collection.count.return_value = 1
        client = Mock()
        client.get_collection.return_value = collection

        with patch("app.services.vector_store._client", client), patch(
            "app.services.vector_store.get_embedding", return_value=[0.1] * 512
        ), patch(
            "app.services.vector_store.current_dimension", return_value=512
        ), patch(
            "app.services.vector_store.current_model_name",
            return_value="BAAI/bge-small-zh-v1.5",
        ), patch(
            "app.services.vector_store.ingest_knowledge_base"
        ) as ingest_mock:
            from app.services.vector_store import search_similar

            with self.assertRaisesRegex(EmbeddingServiceError, "显式重新入库"):
                search_similar("质量问题退货运费")

        ingest_mock.assert_not_called()
        client.delete_collection.assert_not_called()
        collection.query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
