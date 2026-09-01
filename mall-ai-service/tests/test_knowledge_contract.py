import unittest
from pathlib import Path

from app.services.knowledge_contract import (
    assert_policy_corpus_valid,
    validate_chunk_contract,
    validate_policy_corpus_data,
)
from app.services.chunking_service import Chunk


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class KnowledgeContractTests(unittest.TestCase):
    def test_committed_demo_corpus_has_a_valid_retrieval_and_grounding_contract(self) -> None:
        report = assert_policy_corpus_valid(
            PROJECT_ROOT / "app" / "knowledge",
            PROJECT_ROOT / "evals" / "rag_cases.json",
            PROJECT_ROOT / "evals" / "rag_grounding_cases.json",
        )

        self.assertTrue(report["valid"])
        self.assertGreaterEqual(report["policy_section_count"], 12)
        self.assertGreaterEqual(report["retrieval_case_count"], 30)
        self.assertGreaterEqual(report["grounding_case_count"], 12)
        self.assertGreater(report["retrieval_no_evidence_case_count"], 0)
        self.assertGreater(report["grounding_no_evidence_case_count"], 0)
        self.assertEqual("chunk-v2", report["chunk_contract_version"])
        self.assertGreaterEqual(report["chunk_count"], 12)

    def test_reports_a_retrieval_case_that_points_to_a_missing_section(self) -> None:
        report = validate_policy_corpus_data(
            {"Known policy"},
            [
                {
                    "id": "bad-reference",
                    "category": "demo",
                    "question": "demo question",
                    "expected_section": "Missing policy",
                }
            ],
            [],
        )

        self.assertFalse(report["valid"])
        self.assertIn("missing policy section", report["errors"][0])

    def test_requires_empty_sources_for_no_evidence_grounding_cases(self) -> None:
        report = validate_policy_corpus_data(
            {"Known policy"},
            [],
            [
                {
                    "id": "bad-no-evidence",
                    "question": "unknown question",
                    "expected": {"outcome": "no_evidence", "sources_empty": False},
                }
            ],
        )

        self.assertFalse(report["valid"])
        self.assertIn("must expect empty sources", report["errors"][0])

    def test_chunk_contract_rejects_missing_version_and_effective_date(self) -> None:
        errors = validate_chunk_contract(
            [
                Chunk(
                    chunk_id="chunk",
                    text="policy",
                    document_id="policy",
                    heading_path=("section",),
                    source_order=1,
                    policy_version="unknown",
                    category="after_sales",
                    language="zh-CN",
                    document_type="policy",
                    content_hash="a" * 64,
                )
            ]
        )

        self.assertTrue(any("policy_version" in error for error in errors))
        self.assertTrue(any("effective_from" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
