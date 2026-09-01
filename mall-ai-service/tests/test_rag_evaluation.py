import unittest

from app.schemas.rag import RetrievedChunk
from app.services.rag_evaluation import evaluate_rag_cases


class RagEvaluationTests(unittest.TestCase):
    def test_reports_recall_for_supported_cases_only(self) -> None:
        cases = [
            {
                "id": "case-1",
                "category": "shipping_fee",
                "question": "质量问题退货运费谁承担？",
                "expected_section": "退货运费",
            },
            {
                "id": "case-2",
                "category": "no_evidence",
                "question": "送多少积分？",
                "expected_section": None,
            },
        ]

        def fake_search(query: str, top_k: int):
            if "运费" in query:
                return [
                    RetrievedChunk(
                        chunk_id="chunk-1",
                        document_name="售后政策知识库",
                        section_path="售后政策知识库 > 退货运费",
                        text="质量问题退货运费由商家承担。",
                        distance=0.2,
                    )
                ]
            return []

        report = evaluate_rag_cases(cases, search=fake_search, top_k=3)

        self.assertEqual(2, report["total_cases"])
        self.assertEqual(1, report["supported_cases"])
        self.assertEqual(1, report["retrieval_hits"])
        self.assertEqual(1.0, report["recall_at_k"])
        self.assertEqual(1, report["evidence_retrieval_hits"])
        self.assertEqual(1.0, report["evidence_recall_at_k"])
        self.assertEqual(1, report["no_evidence_cases"])
        self.assertEqual(1, report["no_evidence_passes"])
        self.assertEqual(1.0, report["no_evidence_pass_rate"])

    def test_distinguishes_raw_recall_from_the_rag_evidence_gate(self) -> None:
        cases = [
            {
                "id": "case-1",
                "category": "shipping_fee",
                "question": "质量问题退货运费谁承担？",
                "expected_section": "退货运费",
            },
            {
                "id": "case-2",
                "category": "no_evidence",
                "question": "赠送多少积分？",
                "expected_section": None,
            },
        ]

        def fake_search(query: str, _top_k: int):
            if "积分" in query:
                return [
                    RetrievedChunk(
                        chunk_id="chunk-irrelevant-but-close",
                        document_name="售后政策知识库",
                        section_path="售后政策知识库 > 退货运费",
                        text="质量问题退货运费由商家承担。",
                        distance=0.2,
                    )
                ]
            return [
                RetrievedChunk(
                    chunk_id="chunk-too-far",
                    document_name="售后政策知识库",
                    section_path="售后政策知识库 > 退货运费",
                    text="质量问题退货运费由商家承担。",
                    distance=0.9,
                )
            ]

        report = evaluate_rag_cases(
            cases,
            search=fake_search,
            top_k=3,
            max_distance=0.75,
        )

        self.assertEqual(1.0, report["recall_at_k"])
        self.assertEqual(0.0, report["evidence_recall_at_k"])
        self.assertEqual(0.0, report["no_evidence_pass_rate"])

    def test_calibrated_threshold_keeps_supported_and_refuses_unsupported(self) -> None:
        cases = [
            {
                "id": "supported",
                "category": "shipping_fee",
                "question": "known policy question",
                "expected_section": "shipping_fee",
            },
            {
                "id": "unsupported",
                "category": "no_evidence",
                "question": "unknown benefit question",
                "expected_section": None,
            },
        ]

        def fake_search(query: str, _top_k: int):
            if query == "known policy question":
                return [
                    RetrievedChunk(
                        chunk_id="supported-chunk",
                        document_name="policy",
                        section_path="policy > shipping_fee",
                        text="Known shipping-fee policy.",
                        distance=0.4243,
                    )
                ]
            return [
                RetrievedChunk(
                    chunk_id="unsupported-nearest-chunk",
                    document_name="policy",
                    section_path="policy > shipping_fee",
                    text="Irrelevant but semantically close policy.",
                    distance=0.5267,
                )
            ]

        report = evaluate_rag_cases(
            cases,
            search=fake_search,
            top_k=3,
            max_distance=0.48,
        )

        self.assertEqual(1.0, report["evidence_recall_at_k"])
        self.assertEqual(1.0, report["no_evidence_pass_rate"])

    def test_uses_batch_retrieval_when_the_evaluation_runner_provides_it(self) -> None:
        cases = [
            {
                "id": "case-1",
                "category": "shipping_fee",
                "question": "quality return shipping",
                "expected_section": "shipping-fee",
            },
            {
                "id": "case-2",
                "category": "no_evidence",
                "question": "unknown benefit",
                "expected_section": None,
            },
        ]

        def unexpected_single_search(_query: str, _top_k: int):
            raise AssertionError("single-query search should not run")

        def batch_search(queries: list[str], top_k: int):
            self.assertEqual(["quality return shipping", "unknown benefit"], queries)
            self.assertEqual(3, top_k)
            return [
                [
                    RetrievedChunk(
                        chunk_id="shipping",
                        document_name="policy",
                        section_path="policy > shipping-fee",
                        text="quality issue shipping is covered",
                        distance=0.2,
                    )
                ],
                [],
            ]

        report = evaluate_rag_cases(
            cases,
            search=unexpected_single_search,
            batch_search=batch_search,
        )

        self.assertEqual(1.0, report["evidence_recall_at_k"])
        self.assertEqual(1.0, report["no_evidence_pass_rate"])


if __name__ == "__main__":
    unittest.main()
