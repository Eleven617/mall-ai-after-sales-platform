"""Tests for the hybrid LangGraph Agent learning lab; no real model is called."""
from __future__ import annotations

import unittest

from langgraph.types import Command

from langgraph_agent_loop import ScriptedDecisionProvider, build_agent_graph


class LangGraphAgentLoopTests(unittest.TestCase):
    def test_scripted_agent_uses_tools_then_pauses_and_resumes(self) -> None:
        provider = ScriptedDecisionProvider(
            ["lookup_order", "load_logistics", "retrieve_policy", "prepare_handoff"]
        )
        app = build_agent_graph(provider)
        config = {"configurable": {"thread_id": "agent-test-confirm"}}

        paused = app.invoke(
            {"order_sn": "ORD-DELAY-001", "user_question": "为什么没到？"},
            config,
        )

        self.assertIn("__interrupt__", paused)
        self.assertEqual(paused["agent_decision_count"], 4)
        self.assertEqual(len(paused["decision_trace"]), 4)
        self.assertIn("物流异常核验", paused["policy_evidence"])

        resumed = app.invoke(Command(resume={"approved": True}), config)

        self.assertEqual(resumed["final_status"], "handoff_draft_created")

    def test_invalid_model_action_is_blocked_by_server_validation(self) -> None:
        app = build_agent_graph(ScriptedDecisionProvider(["delete_order"]))
        result = app.invoke(
            {"order_sn": "ORD-DELAY-001", "user_question": "删除订单"},
            {"configurable": {"thread_id": "agent-test-invalid-action"}},
        )

        self.assertEqual(result["final_status"], "invalid_or_unavailable_model_decision")
        self.assertNotIn("__interrupt__", result)
        self.assertIn("ValidationError", result["decision_trace"][0])

    def test_graph_stops_repeated_model_decisions_at_bound(self) -> None:
        app = build_agent_graph(ScriptedDecisionProvider(["load_logistics"] * 10))
        result = app.invoke(
            {"order_sn": "ORD-DELAY-001", "user_question": "为什么没到？"},
            {"configurable": {"thread_id": "agent-test-step-limit"}},
        )

        self.assertEqual(result["final_status"], "agent_step_limit_reached")
        self.assertEqual(result["agent_decision_count"], 5)

    def test_missing_order_is_finished_by_graph_without_more_model_steps(self) -> None:
        app = build_agent_graph(ScriptedDecisionProvider(["lookup_order", "retrieve_policy"]))
        result = app.invoke(
            {"order_sn": "ORD-NOT-FOUND", "user_question": "为什么没到？"},
            {"configurable": {"thread_id": "agent-test-order-missing"}},
        )

        self.assertEqual(result["final_status"], "order_not_found_or_not_authorized")
        self.assertEqual(result["agent_decision_count"], 1)

    def test_order_lookup_does_not_leak_logistics_before_logistics_node(self) -> None:
        app = build_agent_graph(ScriptedDecisionProvider(["lookup_order", "finish"]))
        result = app.invoke(
            {"order_sn": "ORD-DELAY-001", "user_question": "订单到了哪里？"},
            {"configurable": {"thread_id": "agent-test-tool-boundary"}},
        )

        self.assertTrue(result["order_found"])
        self.assertNotIn("logistics_status", result)


if __name__ == "__main__":
    unittest.main()
