import tempfile
import unittest
from pathlib import Path

from app.services.bm25_retriever import BM25PolicyIndex, search_bm25, tokenize_policy_text
from app.services.chunking_service import Chunk


class BM25RetrieverTests(unittest.TestCase):
    def test_chinese_tokenizer_keeps_exact_term_signal(self) -> None:
        tokens = tokenize_policy_text("七天无理由退货，运费由商家承担")

        self.assertIn("七天", tokens)
        self.assertIn("无理由", tokens)
        self.assertIn("退货", tokens)

    def test_bm25_ranks_exact_shipping_policy_above_unrelated_chunk(self) -> None:
        index = BM25PolicyIndex(
            [
                Chunk(
                    chunk_id="shipping",
                    document_title="政策",
                    section_path="政策 > 退货运费",
                    text="政策 > 退货运费\n质量问题退货运费由商家承担。",
                ),
                Chunk(
                    chunk_id="invoice",
                    document_title="政策",
                    section_path="政策 > 发票",
                    text="政策 > 发票\n符合条件的订单可以申请电子发票。",
                ),
            ]
        )

        hits = index.search("质量问题寄回邮费谁承担", top_k=2)

        self.assertEqual("shipping", hits[0].chunk_id)
        self.assertEqual("bm25", hits[0].retrieval_method)
        self.assertEqual(1, hits[0].bm25_rank)
        self.assertGreater(hits[0].bm25_score or 0, 0)

    def test_reads_markdown_corpus_without_a_remote_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = Path(temp_dir) / "policy.md"
            policy.write_text(
                "# 政策\n\n## 价保\n\n价保要看活动时间。\n",
                encoding="utf-8",
            )

            hits = search_bm25("价保活动结束还能补吗", 3, knowledge_dir=Path(temp_dir))

        self.assertEqual(1, len(hits))
        self.assertIn("价保", hits[0].section_path)


if __name__ == "__main__":
    unittest.main()
