import unittest

from app.schemas.rag import RetrievedChunk
from app.services.rag_evidence_verifier import EvidenceVerificationError
from app.services.rag_verifier_evaluation import evaluate_rag_verifier_cases


SHIPPING_CHUNK = RetrievedChunk(
    chunk_id="shipping",
    document_name="policy",
    section_path="policy > shipping-fee",
    text="Quality return shipping is merchant paid.",
    distance=0.2,
)


class RagVerifierEvaluationTests(unittest.TestCase):
    def test_reports_supported_and_no_evidence_results_separately(self) -> None:
        cases = [
            {"id": "supported", "question": "quality shipping", "expected_section": "shipping-fee"},
            {"id": "unknown", "question": "unknown benefit", "expected_section": None},
        ]

        def batch_search(_questions: list[str], _top_k: int):
            return [[SHIPPING_CHUNK], [SHIPPING_CHUNK]]

        def verifier(question: str, _chunks: list[RetrievedChunk]):
            return [SHIPPING_CHUNK] if question == "quality shipping" else []

        report = evaluate_rag_verifier_cases(
            cases,
            batch_search=batch_search,
            verifier=verifier,
        )

        self.assertEqual("completed", report["status"])
        self.assertEqual(1.0, report["supported_pass_rate"])
        self.assertEqual(1.0, report["no_evidence_pass_rate"])

    def test_marks_verifier_outage_as_environment_blocked(self) -> None:
        cases = [{"id": "supported", "question": "quality shipping", "expected_section": "shipping-fee"}]

        def batch_search(_questions: list[str], _top_k: int):
            return [[SHIPPING_CHUNK]]

        def verifier(_question: str, _chunks: list[RetrievedChunk]):
            raise EvidenceVerificationError("synthetic outage")

        report = evaluate_rag_verifier_cases(
            cases,
            batch_search=batch_search,
            verifier=verifier,
        )

        self.assertEqual("environment_blocked", report["status"])
        self.assertEqual(1, report["environment_blocked_cases"])
