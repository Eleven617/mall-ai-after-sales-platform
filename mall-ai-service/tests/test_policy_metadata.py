import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.schemas.rag import PolicyMetadataFilter
from app.services.chunking_service import Chunk
from app.services.policy_metadata import (
    build_chroma_where,
    chunk_matches_filter,
    resolve_published_policy_filter,
)
from app.services.policy_retrieval import retrieve_policy_candidates


_SETTINGS = SimpleNamespace(
    rag_active_policy_version="V1.1",
    rag_policy_language="zh-CN",
    rag_policy_document_type="policy",
)


class PolicyMetadataTests(unittest.TestCase):
    def test_published_scope_keeps_default_hard_filters_when_category_is_added(self) -> None:
        with patch("app.services.policy_metadata.settings", _SETTINGS):
            selected = resolve_published_policy_filter(
                {"category": "electronics"},
                today=date(2026, 8, 28),
            )

        self.assertEqual("V1.1", selected.policy_version)
        self.assertEqual("electronics", selected.category)
        self.assertEqual("zh-CN", selected.language)
        self.assertEqual("policy", selected.document_type)
        self.assertEqual(date(2026, 8, 28), selected.effective_on_or_before)

    def test_future_requested_date_cannot_widen_published_effective_date(self) -> None:
        with patch("app.services.policy_metadata.settings", _SETTINGS):
            selected = resolve_published_policy_filter(
                {"effective_on_or_before": "2026-12-31"},
                today=date(2026, 8, 28),
            )

        self.assertEqual(date(2026, 8, 28), selected.effective_on_or_before)

    def test_filter_schema_rejects_unknown_model_controlled_fields(self) -> None:
        with self.assertRaises(ValidationError):
            PolicyMetadataFilter.model_validate(
                {"category": "electronics", "ignore_policy_version": True}
            )

    def test_metadata_matching_filters_version_date_category_language_and_type(self) -> None:
        chunk = Chunk(
            text="policy",
            policy_version="V2.0",
            effective_from="2026-08-20",
            effective_from_ts=1787184000,
            category="electronics",
            language="zh-CN",
            document_type="policy",
        )
        matching = PolicyMetadataFilter(
            policy_version="V2.0",
            effective_on_or_before=date(2026, 8, 28),
            category="electronics",
            language="zh-CN",
            document_type="policy",
        )

        self.assertTrue(chunk_matches_filter(chunk, matching))
        self.assertFalse(
            chunk_matches_filter(
                chunk,
                matching.model_copy(update={"policy_version": "V1.0"}),
            )
        )
        where = build_chroma_where(matching)
        self.assertIn("$and", where or {})
        self.assertIn({"category": {"$eq": "electronics"}}, (where or {})["$and"])

    def test_real_dense_path_receives_server_resolved_filter(self) -> None:
        captured: list[PolicyMetadataFilter] = []

        with patch("app.services.policy_metadata.settings", _SETTINGS), patch(
            "app.services.policy_retrieval.search_similar",
            side_effect=lambda _query, _top_k, *, metadata_filter: captured.append(metadata_filter) or [],
        ):
            result = retrieve_policy_candidates(
                "质量问题退货运费",
                mode="dense",
                metadata_filter={"category": "electronics"},
            )

        self.assertEqual([], result.chunks)
        self.assertEqual(1, len(captured))
        self.assertEqual("V1.1", captured[0].policy_version)
        self.assertEqual("electronics", captured[0].category)


if __name__ == "__main__":
    unittest.main()
