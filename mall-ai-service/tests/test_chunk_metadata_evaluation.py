import unittest
from pathlib import Path

from app.services.chunk_metadata_evaluation import (
    ChunkMetadataEvaluationError,
    evaluate_chunk_metadata_suite,
    load_chunk_metadata_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ChunkMetadataEvaluationTests(unittest.TestCase):
    def test_committed_synthetic_chunk_metadata_suite_passes(self) -> None:
        suite = load_chunk_metadata_suite(
            PROJECT_ROOT / "evals" / "rag_chunk_metadata_cases.v1.json"
        )

        report = evaluate_chunk_metadata_suite(suite)

        self.assertEqual("rag-chunk-metadata.v1", report["suite_version"])
        self.assertEqual("passed", report["status"])
        self.assertGreaterEqual(report["total_cases"], 8)
        self.assertEqual(0, report["failed_cases"])
        self.assertEqual(0, report["cost"]["external_model_calls"])

    def test_bad_filter_contract_becomes_deterministic_failure(self) -> None:
        suite = {
            "suite_version": "test.v1",
            "schema_version": "1",
            "documents": [
                {
                    "file_name": "policy.md",
                    "content": "# 政策\n\n> 规则 V1.0，更新于 2026-08-20。\n\n## 规则\n\n正文。\n",
                }
            ],
            "cases": [
                {
                    "case_id": "bad-filter",
                    "metadata_filter": {"category": "after_sales", "model_can_pick_version": True},
                    "expected_document_ids": ["policy"],
                }
            ],
        }

        report = evaluate_chunk_metadata_suite(suite)

        self.assertEqual("quality_failed", report["status"])
        self.assertIn("invalid_metadata_filter", report["results"][0]["violations"])

    def test_loader_rejects_duplicate_case_ids(self) -> None:
        path = PROJECT_ROOT / "evals" / "rag_chunk_metadata_cases.v1.json"
        # The committed fixture is the source of truth; this test only proves
        # that the loader itself rejects duplicate case IDs when supplied a
        # malformed in-memory-style JSON file through the public boundary.
        self.assertTrue(path.is_file())
        with self.assertRaises(ChunkMetadataEvaluationError):
            from unittest.mock import patch

            with patch(
                "pathlib.Path.read_text",
                return_value=(
                    '{"suite_version":"x","schema_version":"1",'
                    '"documents":[{"file_name":"x.md","content":"# x"}],'
                    '"cases":[{"case_id":"same"},{"case_id":"same"}]}'
                ),
            ):
                load_chunk_metadata_suite(path)


if __name__ == "__main__":
    unittest.main()
