import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.rag import RetrievedChunk
from app.services.cross_encoder_reranker import RerankerUnavailable
from app.services.policy_retrieval import (
    PolicyRetrievalUnavailable,
    fuse_rrf,
    is_evidence_candidate,
    retrieve_policy_candidates,
)


def _chunk(
    chunk_id: str,
    *,
    distance: float = 0.2,
    dense_rank: int | None = None,
    bm25_rank: int | None = None,
    bm25_score: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_name="policy",
        section_path=f"policy > {chunk_id}",
        text=f"policy {chunk_id}",
        distance=distance,
        dense_rank=dense_rank,
        bm25_rank=bm25_rank,
        bm25_score=bm25_score,
    )


_SETTINGS = SimpleNamespace(
    rag_retrieval_mode="dense",
    rag_top_k=3,
    rag_hybrid_candidate_k=4,
    rag_rrf_k=60,
    rag_max_distance=0.48,
    rag_bm25_min_score=0.1,
)


class PolicyRetrievalTests(unittest.TestCase):
    def test_rrf_rewards_a_chunk_found_by_both_retrievers(self) -> None:
        fused = fuse_rrf(
            [_chunk("dense-only", dense_rank=1), _chunk("shared", dense_rank=2)],
            [_chunk("shared", bm25_rank=1, bm25_score=3.0), _chunk("bm25-only", bm25_rank=2, bm25_score=2.0)],
            rrf_k=60,
            limit=3,
        )

        self.assertEqual("shared", fused[0].chunk_id)
        self.assertEqual("hybrid", fused[0].retrieval_method)
        self.assertEqual(2, fused[0].dense_rank)
        self.assertEqual(1, fused[0].bm25_rank)

    def test_hybrid_uses_both_sources_and_passes_sanitized_query(self) -> None:
        received: list[str] = []

        def dense(query, top_k):
            received.append(query)
            return [_chunk("shipping", distance=0.3)]

        def bm25(query, top_k):
            received.append(query)
            return [_chunk("shipping", bm25_score=2.0)]

        with patch("app.services.policy_retrieval.settings", _SETTINGS):
            result = retrieve_policy_candidates(
                "订单 202608210001 质量问题退货运费谁承担？",
                mode="hybrid",
                dense_search=dense,
                bm25_search=bm25,
            )

        self.assertEqual("hybrid", result.effective_mode)
        self.assertEqual(["shipping"], [chunk.chunk_id for chunk in result.chunks])
        self.assertEqual(2, len(received))
        self.assertTrue(all("202608210001" not in query for query in received))

    def test_hybrid_is_not_a_bm25_fallback_when_dense_fails(self) -> None:
        with patch("app.services.policy_retrieval.settings", _SETTINGS):
            with self.assertRaises(PolicyRetrievalUnavailable):
                retrieve_policy_candidates(
                    "退货运费",
                    mode="hybrid",
                    dense_search=lambda *_args: (_ for _ in ()).throw(RuntimeError("down")),
                    bm25_search=lambda *_args: [_chunk("shipping", bm25_score=2.0)],
                )

    def test_reranker_failure_keeps_safe_hybrid_candidates(self) -> None:
        with patch("app.services.policy_retrieval.settings", _SETTINGS):
            result = retrieve_policy_candidates(
                "退货运费",
                mode="hybrid_rerank",
                dense_search=lambda *_args: [_chunk("shipping", distance=0.2)],
                bm25_search=lambda *_args: [_chunk("shipping", bm25_score=2.0)],
                rerank=lambda *_args: (_ for _ in ()).throw(RerankerUnavailable("missing")),
            )

        self.assertTrue(result.reranker_unavailable)
        self.assertEqual("hybrid", result.effective_mode)
        self.assertEqual(["shipping"], [chunk.chunk_id for chunk in result.chunks])

    def test_candidate_gate_keeps_calibrated_dense_or_positive_bm25_only(self) -> None:
        with patch("app.services.policy_retrieval.settings", _SETTINGS):
            self.assertTrue(is_evidence_candidate(_chunk("dense", distance=0.2, dense_rank=1)))
            self.assertFalse(is_evidence_candidate(_chunk("far", distance=0.9, dense_rank=1)))
            self.assertTrue(
                is_evidence_candidate(_chunk("lexical", distance=1.0, bm25_rank=1, bm25_score=0.2))
            )
            self.assertFalse(
                is_evidence_candidate(_chunk("weak", distance=1.0, bm25_rank=1, bm25_score=0.01))
            )


if __name__ == "__main__":
    unittest.main()
