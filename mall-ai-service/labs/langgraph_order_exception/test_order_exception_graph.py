"""Regression tests for the isolated LangGraph learning lab."""
from __future__ import annotations

import unittest

from langgraph.types import Command

from order_exception_graph import build_graph


class OrderExceptionGraphTests(unittest.TestCase):
    def test_delayed_order_pauses_then_resumes_after_human_confirmation(self) -> None:
        app = build_graph()
        config = {"configurable": {"thread_id": "test-delay-confirm"}}

        paused = app.invoke(
            {"order_sn": "ORD-DELAY-001", "user_question": "为什么没到？"},
            config,
        )

        self.assertIn("__interrupt__", paused)
        self.assertIn("48 小时未更新", paused["recommended_action"])
        self.assertIn("物流异常核验", paused["policy_evidence"])
        self.assertNotIn("final_status", paused)

        resumed = app.invoke(Command(resume={"approved": True}), config)

        self.assertEqual(resumed["final_status"], "handoff_draft_created")
        self.assertEqual(resumed["confirmation"], {"approved": True})

    def test_delayed_order_can_cancel_after_resume(self) -> None:
        app = build_graph()
        config = {"configurable": {"thread_id": "test-delay-cancel"}}

        app.invoke({"order_sn": "ORD-DELAY-001", "user_question": "为什么没到？"}, config)
        resumed = app.invoke(Command(resume={"approved": False}), config)

        self.assertEqual(resumed["final_status"], "handoff_cancelled")

    def test_missing_order_stops_without_entering_human_confirmation(self) -> None:
        app = build_graph()
        result = app.invoke(
            {"order_sn": "ORD-NOT-FOUND", "user_question": "为什么没到？"},
            {"configurable": {"thread_id": "test-order-missing"}},
        )

        self.assertNotIn("__interrupt__", result)
        self.assertEqual(result["final_status"], "order_not_found_or_not_authorized")

    def test_normal_logistics_stops_without_policy_or_confirmation(self) -> None:
        app = build_graph()
        result = app.invoke(
            {"order_sn": "ORD-NORMAL-002", "user_question": "为什么没到？"},
            {"configurable": {"thread_id": "test-order-normal"}},
        )

        self.assertNotIn("__interrupt__", result)
        self.assertNotIn("policy_evidence", result)
        self.assertNotIn("final_status", result)


if __name__ == "__main__":
    unittest.main()
