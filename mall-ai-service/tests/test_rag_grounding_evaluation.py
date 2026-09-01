import unittest

from app.schemas.rag import RagSource
from app.services.rag_grounding_evaluation import evaluate_rag_grounding_cases
from app.services.rag_service import RagAnswer


SHIPPING_SOURCE = RagSource(
    chunk_id="shipping-001",
    document_name="policy",
    section_path="policy > shipping-fee",
    distance=0.2,
)


class RagGroundingEvaluationTests(unittest.TestCase):
    def test_reports_supported_no_evidence_and_retrieval_unavailable_outcomes(self) -> None:
        cases = [
            {
                "id": "supported",
                "question": "supported question",
                "expected": {
                    "outcome": "answered",
                    "source_sections_include": ["shipping-fee"],
                    "sources_empty": False,
                    "answer_fact_marker_groups": [["merchant pays", "merchant covers"]],
                    "answer_not_contains": ["coupon"],
                },
            },
            {
                "id": "no-evidence",
                "question": "unknown benefit",
                "expected": {
                    "outcome": "no_evidence",
                    "sources_empty": True,
                    "answer_fact_marker_groups": [["not enough evidence"]],
                },
            },
            {
                "id": "provider-down",
                "question": "provider down",
                "expected": {
                    "outcome": "retrieval_unavailable",
                    "sources_empty": True,
                    "answer_fact_marker_groups": [["temporarily unavailable"]],
                },
            },
        ]

        def fake_answer(question: str) -> RagAnswer:
            if question == "supported question":
                return RagAnswer(
                    answer="The merchant pays the return shipping fee.",
                    retrieved_context=["policy text"],
                    sources=[SHIPPING_SOURCE],
                )
            if question == "unknown benefit":
                return RagAnswer(
                    answer="There is not enough evidence in the policy.",
                    retrieved_context=[],
                    sources=[],
                    no_evidence=True,
                )
            return RagAnswer(
                answer="Policy retrieval is temporarily unavailable.",
                retrieved_context=[],
                sources=[],
                retrieval_unavailable=True,
            )

        report = evaluate_rag_grounding_cases(cases, answer_question=fake_answer)

        self.assertEqual(3, report["total_cases"])
        self.assertEqual(3, report["passed_cases"])
        self.assertEqual(1.0, report["pass_rate"])

    def test_reports_a_forbidden_claim_even_when_the_source_is_correct(self) -> None:
        cases = [
            {
                "id": "hallucinated-benefit",
                "question": "shipping question",
                "expected": {
                    "outcome": "answered",
                    "source_sections_include": ["shipping-fee"],
                    "answer_not_contains": ["coupon"],
                },
            }
        ]

        def fake_answer(_question: str) -> RagAnswer:
            return RagAnswer(
                answer="The merchant pays shipping and sends a coupon.",
                retrieved_context=["policy text"],
                sources=[SHIPPING_SOURCE],
            )

        report = evaluate_rag_grounding_cases(cases, answer_question=fake_answer)

        self.assertEqual(0, report["passed_cases"])
        self.assertFalse(report["cases"][0]["checks"]["answer_not_contains"])
        self.assertEqual(["policy > shipping-fee"], report["cases"][0]["observed"]["source_sections"])

    def test_ignores_whitespace_in_a_reviewed_fact_marker(self) -> None:
        cases = [
            {
                "id": "refund-spacing",
                "question": "refund question",
                "expected": {
                    "outcome": "answered",
                    "answer_fact_marker_groups": [["1 到 3 个工作日"]],
                },
            }
        ]

        def fake_answer(_question: str) -> RagAnswer:
            return RagAnswer(
                answer="退款通常会在1到3个工作日内原路退回。",
                retrieved_context=["policy text"],
                sources=[SHIPPING_SOURCE],
            )

        report = evaluate_rag_grounding_cases(cases, answer_question=fake_answer)

        self.assertEqual(1, report["passed_cases"])
        self.assertTrue(
            report["cases"][0]["review_checks"]["answer_fact_marker_groups"]
        )

    def test_separates_provider_outage_from_grounding_quality_failure(self) -> None:
        cases = [
            {
                "id": "provider-outage",
                "question": "supported question",
                "expected": {"outcome": "answered"},
            }
        ]

        def fake_answer(_question: str) -> RagAnswer:
            return RagAnswer(
                answer="Policy retrieval is temporarily unavailable.",
                retrieved_context=[],
                sources=[],
                retrieval_unavailable=True,
            )

        report = evaluate_rag_grounding_cases(cases, answer_question=fake_answer)

        self.assertEqual("environment_blocked", report["status"])
        self.assertEqual(1, report["environment_blocked_cases"])
        self.assertEqual(0, report["quality_evaluated_cases"])

    def test_does_not_flag_a_forbidden_phrase_when_the_answer_explicitly_denies_it(self) -> None:
        cases = [
            {
                "id": "negated-claim",
                "question": "doorstep collection",
                "expected": {
                    "outcome": "answered",
                    "answer_not_contains": ["自动安排免费上门取件"],
                },
            }
        ]

        def fake_answer(_question: str) -> RagAnswer:
            return RagAnswer(
                answer="当前规则不自动安排免费上门取件。",
                retrieved_context=["policy text"],
                sources=[SHIPPING_SOURCE],
            )

        report = evaluate_rag_grounding_cases(cases, answer_question=fake_answer)

        self.assertEqual(1, report["passed_cases"])

    def test_keeps_an_affirmative_claim_after_an_unrelated_denial_as_a_failure(self) -> None:
        cases = [
            {
                "id": "affirmative-after-denial",
                "question": "points",
                "expected": {
                    "outcome": "answered",
                    "answer_not_contains": ["自动赠送积分"],
                },
            }
        ]

        def fake_answer(_question: str) -> RagAnswer:
            return RagAnswer(
                answer="本规则不支持退货，但会自动赠送积分。",
                retrieved_context=["policy text"],
                sources=[SHIPPING_SOURCE],
            )

        report = evaluate_rag_grounding_cases(cases, answer_question=fake_answer)

        self.assertEqual(0, report["passed_cases"])


if __name__ == "__main__":
    unittest.main()
