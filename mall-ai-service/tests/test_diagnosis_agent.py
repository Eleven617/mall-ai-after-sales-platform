import unittest
from unittest.mock import patch

from app.schemas.tool import ToolCall
from app.services.agent_service import run_agent_result
from app.services.llm_service import LLMResponse
from app.services.mall_client import MallOrderNotAccessibleError
from app.services.trace_service import InMemoryTraceSink, set_trace_sink_for_tests


class DiagnosisAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace_sink = InMemoryTraceSink()
        set_trace_sink_for_tests(self.trace_sink)

    def tearDown(self) -> None:
        set_trace_sink_for_tests(None)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_langgraph_runs_multi_tool_diagnosis_and_keeps_facts_server_owned(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "order_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(tool_calls=[{"name": "logistics_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(tool_calls=[{"name": "rag_search", "arguments": {"query": "物流运输中未收到货怎么办"}}]),
            LLMResponse(content="订单已签收，物流公司是顺丰。"),
        ]
        call_tool.side_effect = [
            {"order_sn": "202607240001", "status": "已发货", "product_names": ["测试耳机"]},
            {"order_sn": "202607240001", "company": "测试物流", "tracking_no": "TEST-001", "order_status": "运输中", "product_names": ["测试耳机"]},
            {"sources": [{"document_name": "售后政策知识库", "section_path": "物流异常处理"}], "no_evidence": False},
        ]

        result = run_agent_result("订单为什么没到，我现在怎么办？", session_id="diagnosis-a", diagnosis=True)

        self.assertIsNotNone(result.diagnosis)
        self.assertEqual("delivery_in_transit", result.diagnosis.category)
        self.assertEqual("complete", result.diagnosis.evidence_status)
        self.assertTrue(result.diagnosis.handoff)
        self.assertEqual("manual_review", result.diagnosis.handoff.reason)
        self.assertIn("运输中", result.answer)
        self.assertNotIn("顺丰", result.answer)
        self.assertEqual(3, call_tool.call_count)
        self.assertIn("diagnosis_completed", [event.event for event in self.trace_sink.events])

    @patch("app.services.agent_service.generate_with_tools")
    def test_langgraph_returns_pending_read_only_call_without_execution(self, generate_with_tools) -> None:
        generate_with_tools.return_value = LLMResponse(
            tool_calls=[{"name": "logistics_service", "arguments": {}}]
        )

        result = run_agent_result("诊断物流", session_id="diagnosis-b", diagnosis=True)

        self.assertEqual("logistics_service", result.pending_tool_call.name)
        self.assertEqual("needs_order_identifier", result.diagnosis.category)
        self.assertIn("订单号", result.answer)
        self.assertIn("tool_argument_requested", [event.event for event in self.trace_sink.events])

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_missing_order_identifier_is_normal_waiting_input_without_durable_interrupt(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.return_value = LLMResponse(
            tool_calls=[{"name": "order_service", "arguments": {}}]
        )
        result = run_agent_result(
            "订单为什么没有按预期送达，物流是否异常，我下一步怎么办？",
            session_id="diagnosis-durable-entry",
            diagnosis=True,
            diagnosis_requires_order_facts=True,
        )

        self.assertFalse(result.durable_checkpoint_pending)
        self.assertEqual("order_service", result.pending_tool_call.name)
        self.assertIn("订单号", result.answer)
        generate_with_tools.assert_called_once()
        call_tool.assert_not_called()

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_order_exception_model_plans_before_the_server_executes_its_read_only_tool(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        order_sn = "202608110100000008"

        def order_fact_before_model(call, _context):
            self.assertEqual("order_service", call.name)
            self.assertEqual(order_sn, call.arguments["order_sn"])
            self.assertEqual(1, generate_with_tools.call_count)
            return {
                "order_sn": order_sn,
                "status": "已发货",
                "product_names": ["测试耳机"],
            }

        call_tool.side_effect = order_fact_before_model
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "order_service", "arguments": {}}]),
            LLMResponse(content="已完成第一步核验。"),
        ]

        result = run_agent_result(
            f"订单号 {order_sn} 为什么没有按预期送达？",
            session_id="diagnosis-fixed-order-prerequisite",
            diagnosis=True,
            diagnosis_requires_order_facts=True,
        )

        self.assertEqual(1, call_tool.call_count)
        self.assertEqual(2, generate_with_tools.call_count)
        self.assertEqual("facts_incomplete", result.diagnosis.category)
        self.assertTrue(result.diagnosis.handoff)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_unverified_free_text_in_order_diagnosis_becomes_waiting_input(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.return_value = LLMResponse(
            content="请提供订单号后再查询。"
        )

        result = run_agent_result(
            "订单一直没有发货，怎么处理？",
            session_id="diagnosis-no-fact-free-text",
            diagnosis=True,
            diagnosis_requires_order_facts=True,
        )

        self.assertIsNotNone(result.pending_tool_call)
        self.assertEqual("order_service", result.pending_tool_call.name)
        self.assertEqual("needs_order_identifier", result.diagnosis.category)
        self.assertIn("订单号", result.answer)
        call_tool.assert_not_called()
        self.assertIn(
            "missing_identifier_fallback",
            [event.event for event in self.trace_sink.events],
        )

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_langgraph_binds_a_real_long_order_number_when_model_omits_it(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        order_sn = "202608110100000007"
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "order_service", "arguments": {}}]),
            LLMResponse(content="已完成核验。"),
        ]
        call_tool.return_value = {
            "order_sn": order_sn,
            "status": "已发货",
            "product_names": ["测试耳机"],
        }

        run_agent_result(
            f"订单号 {order_sn} 为什么一直没到？",
            session_id="diagnosis-long-order-sn",
            diagnosis=True,
        )

        bound_call = call_tool.call_args.args[0]
        self.assertEqual("order_service", bound_call.name)
        self.assertEqual(order_sn, bound_call.arguments["order_sn"])

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_langgraph_handoffs_when_policy_has_no_evidence(self, generate_with_tools, call_tool) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "order_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(tool_calls=[{"name": "logistics_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(tool_calls=[{"name": "rag_search", "arguments": {"query": "能否退货"}}]),
        ]
        call_tool.side_effect = [
            {"order_sn": "202607240001", "status": "已发货", "product_names": ["测试耳机"]},
            {"order_sn": "202607240001", "company": "测试物流", "tracking_no": "TEST-001", "order_status": "运输中", "product_names": ["测试耳机"]},
            {"sources": [], "no_evidence": True},
        ]

        result = run_agent_result("这个订单能直接退货吗？", session_id="diagnosis-c", diagnosis=True)

        self.assertEqual("policy_insufficient", result.diagnosis.category)
        self.assertEqual("insufficient", result.diagnosis.evidence_status)
        self.assertTrue(result.diagnosis.handoff)
        self.assertIn("政策证据", result.answer)
        self.assertIn("handoff_prepared", [event.event for event in self.trace_sink.events])

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_order_only_fact_never_becomes_policy_insufficient(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "order_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(tool_calls=[{"name": "rag_search", "arguments": {"query": "能否退货"}}]),
        ]
        call_tool.side_effect = [
            {"order_sn": "202607240001", "status": "已发货", "product_names": ["测试耳机"]},
            {"sources": [], "no_evidence": True},
        ]

        result = run_agent_result(
            "订单号 202607240001 的耳机一直没到，能退货吗？",
            session_id="diagnosis-facts-incomplete",
            diagnosis=True,
        )

        self.assertEqual("facts_incomplete", result.diagnosis.category)
        self.assertEqual("partial", result.diagnosis.evidence_status)
        self.assertNotEqual("policy_insufficient", result.diagnosis.category)
        self.assertTrue(result.diagnosis.handoff)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_logistics_facade_without_delivery_observation_is_facts_incomplete(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "order_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(tool_calls=[{"name": "logistics_service", "arguments": {"order_sn": "202607240001"}}]),
            LLMResponse(content="已完成核验。"),
        ]
        call_tool.side_effect = [
            {"order_sn": "202607240001", "status": "已支付", "product_names": ["测试耳机"]},
            {
                "order_sn": "202607240001",
                "company": None,
                "tracking_no": None,
                "order_status": "已支付",
                "product_names": ["测试耳机"],
            },
        ]

        result = run_agent_result(
            "订单号 202607240001 的物流长期停滞，请诊断。",
            session_id="diagnosis-logistics-fact-threshold",
            diagnosis=True,
        )

        self.assertEqual("facts_incomplete", result.diagnosis.category)
        self.assertEqual("partial", result.diagnosis.evidence_status)
        self.assertTrue(result.diagnosis.handoff)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_pure_policy_consultation_can_complete_without_order_or_logistics(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[{"name": "rag_search", "arguments": {"query": "质量问题退货运费"}}]),
            LLMResponse(content="已完成政策咨询。"),
        ]
        call_tool.return_value = {
            "sources": [{"document_name": "售后政策知识库", "section_path": "退货运费"}],
            "no_evidence": False,
        }

        result = run_agent_result(
            "商品质量问题退货，运费由谁承担？",
            session_id="diagnosis-policy-only",
            diagnosis=True,
        )

        self.assertEqual("policy_consultation", result.diagnosis.category)
        self.assertEqual("complete", result.diagnosis.evidence_status)
        self.assertFalse(result.diagnosis.handoff)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_langgraph_does_not_escalate_other_member_order_probe(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        order_sn = "202608180100000002"
        generate_with_tools.return_value = LLMResponse(
            tool_calls=[{"name": "order_service", "arguments": {"order_sn": order_sn}}]
        )
        call_tool.side_effect = MallOrderNotAccessibleError(
            "未找到当前账号可查询的订单，请核对订单号后重试。"
        )

        result = run_agent_result(
            f"订单号 {order_sn} 为什么一直没到？",
            session_id="diagnosis-order-access-boundary",
            diagnosis=True,
        )

        self.assertEqual("needs_order_identifier", result.diagnosis.category)
        self.assertEqual("unavailable", result.diagnosis.evidence_status)
        self.assertIsNone(result.diagnosis.handoff)
        self.assertEqual(["provide_order_sn"], result.diagnosis.allowed_next_steps)
        self.assertIn("核对订单号", result.answer)
        self.assertIn("order_not_accessible", [event.event for event in self.trace_sink.events])


if __name__ == "__main__":
    unittest.main()
