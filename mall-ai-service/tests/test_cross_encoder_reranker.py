import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.rag import RetrievedChunk
from app.services.cross_encoder_reranker import (
    RerankerUnavailable,
    clear_reranker_cache,
    rerank_policy_candidates,
)


def _candidate(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_name="policy",
        section_path=f"policy > {chunk_id}",
        text=f"policy text {chunk_id}",
        distance=0.2,
        retrieval_method="hybrid",
        rrf_score=0.03,
    )


class CrossEncoderRerankerTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_reranker_cache()

    def test_reranker_receives_only_query_and_candidate_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model"
            (model_path / "onnx").mkdir(parents=True)
            for relative in ("onnx/model.onnx", "tokenizer.json", "config.json"):
                (model_path / relative).write_text("fixture", encoding="utf-8")
            received: dict[str, object] = {}

            class FakeModel:
                def rerank(self, query, documents):
                    received["query"] = query
                    received["documents"] = list(documents)
                    return [0.1, 0.9]

            def factory(*args, **kwargs):
                received["factory_args"] = args
                received["factory_kwargs"] = kwargs
                return FakeModel()

            fake_settings = SimpleNamespace(
                rag_reranker_top_n=2,
                rag_reranker_model="BAAI/bge-reranker-base",
                rag_reranker_model_path=str(model_path),
                rag_reranker_threads=1,
            )
            with patch("app.services.cross_encoder_reranker.settings", fake_settings):
                result = rerank_policy_candidates(
                    "质量问题退货运费", [_candidate("one"), _candidate("two")], model_factory=factory
                )

        self.assertEqual(["two", "one"], [candidate.chunk_id for candidate in result])
        self.assertEqual("质量问题退货运费", received["query"])
        self.assertEqual(["policy text one", "policy text two"], received["documents"])
        self.assertTrue(received["factory_kwargs"]["local_files_only"])
        self.assertEqual(["CPUExecutionProvider"], received["factory_kwargs"]["providers"])

    def test_missing_model_cannot_trigger_an_implicit_download(self) -> None:
        fake_settings = SimpleNamespace(
            rag_reranker_top_n=2,
            rag_reranker_model="BAAI/bge-reranker-base",
            rag_reranker_model_path="C:/missing-reranker-model",
            rag_reranker_threads=1,
        )
        with patch("app.services.cross_encoder_reranker.settings", fake_settings):
            with self.assertRaises(RerankerUnavailable):
                rerank_policy_candidates("退货", [_candidate("one")], model_factory=lambda *_a, **_k: None)


if __name__ == "__main__":
    unittest.main()
