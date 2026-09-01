import unittest
from unittest.mock import patch

from app.services.agent_service import run_agent, run_agent_result
from app.services.llm_service import LLMResponse
from app.services.trace_service import InMemoryTraceSink, set_trace_sink_for_tests


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace_sink = InMemoryTraceSink()
        set_trace_sink_for_tests(self.trace_sink)

    def tearDown(self) -> None:
        set_trace_sink_for_tests(None)

    @patch("app.services.agent_service.generate_with_tools")
    def test_blocks_non_read_only_tool_calls(self, generate_with_tools) -> None:
        generate_with_tools.return_value = LLMResponse(
            tool_calls=[{"name": "invented_business_write", "arguments": {}}]
        )

        answer = run_agent("帮我直接提交退货", session_id="session-a")

        self.assertIn("受控业务流程", answer)
        self.assertEqual(
            "tool_blocked",
            self.trace_sink.events[-1].event,
        )

    @patch("app.services.agent_service.generate_with_tools")
    def test_returns_safe_message_when_llm_is_unavailable(self, generate_with_tools) -> None:
        generate_with_tools.side_effect = RuntimeError("network unavailable")

        answer = run_agent("分析退款情况", session_id="session-a")

        self.assertIn("暂时不可用", answer)
        self.assertEqual("llm_unavailable", self.trace_sink.events[-1].event)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_records_read_only_tool_execution(self, generate_with_tools, call_tool) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(
                tool_calls=[
                    {
                        "name": "logistics_service",
                        "arguments": {"order_sn": "202607240001"},
                    }
                ]
            ),
            LLMResponse(content="订单正在运输中。"),
        ]
        call_tool.return_value = {
            "order_sn": "202607240001",
            "company": "测试物流",
            "tracking_no": "TEST-001",
            "order_status": "运输中",
            "product_names": ["测试耳机"],
        }

        answer = run_agent("帮我分析物流", session_id="session-a")

        self.assertIn("测试物流", answer)
        self.assertIn("运输中", answer)
        self.assertEqual(1, call_tool.call_count)
        self.assertIn(
            "tool_completed",
            [event.event for event in self.trace_sink.events],
        )

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_missing_logistics_order_number_becomes_resumable_task(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.return_value = LLMResponse(
            tool_calls=[{"name": "logistics_service", "arguments": {}}]
        )

        result = run_agent_result("查询物流", session_id="session-a")

        self.assertIn("订单号", result.answer)
        self.assertIsNotNone(result.pending_tool_call)
        self.assertEqual("logistics_service", result.pending_tool_call.name)
        self.assertEqual({}, result.pending_tool_call.arguments)
        call_tool.assert_not_called()
        self.assertIn(
            "tool_argument_requested",
            [event.event for event in self.trace_sink.events],
        )

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_replaces_hallucinated_final_text_with_server_verified_facts(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        generate_with_tools.side_effect = [
            LLMResponse(
                content="我来查询物流信息。",
                tool_calls=[
                    {
                        "name": "logistics_service",
                        "arguments": {"order_sn": "202607240001"},
                    }
                ],
            ),
            LLMResponse(content="订单已签收，物流公司是顺丰。"),
        ]
        call_tool.return_value = {
            "order_sn": "202607240001",
            "company": "测试物流",
            "tracking_no": "TEST-001",
            "order_status": "运输中",
            "product_names": ["测试耳机"],
        }

        result = run_agent_result("帮我查询物流", session_id="session-a")

        self.assertIn("测试物流", result.answer)
        self.assertIn("运输中", result.answer)
        self.assertNotIn("顺丰", result.answer)
        self.assertNotIn("已签收", result.answer)
        self.assertEqual("测试物流", result.verified_facts[0].fields[2].value)
        self.assertIn(
            "model_text_replaced_with_verified_facts",
            [event.event for event in self.trace_sink.events],
        )

    @patch("app.services.agent_service.generate_with_tools")
    def test_rejects_business_conclusion_without_verified_tool_result(
        self,
        generate_with_tools,
    ) -> None:
        generate_with_tools.return_value = LLMResponse(content="订单已经签收。")

        result = run_agent_result("订单现在怎么样", session_id="session-a")

        self.assertIn("暂未获得可核验", result.answer)
        self.assertNotIn("已签收", result.answer)
        self.assertEqual([], result.verified_facts)

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.agent_service.generate_with_tools")
    def test_stops_before_repeating_the_same_tool_call(
        self,
        generate_with_tools,
        call_tool,
    ) -> None:
        repeated_call = {
            "name": "logistics_service",
            "arguments": {"order_sn": "202607240001"},
        }
        generate_with_tools.side_effect = [
            LLMResponse(tool_calls=[repeated_call]),
            LLMResponse(tool_calls=[repeated_call]),
        ]
        call_tool.return_value = {"status": "运输中"}

        answer = run_agent("物流为什么还没到", session_id="session-a")

        self.assertIn("人工客服", answer)
        self.assertEqual(1, call_tool.call_count)
        self.assertEqual("repeated_tool_call", self.trace_sink.events[-1].event)

    def test_stops_before_calling_model_when_time_budget_is_exhausted(self) -> None:
        with (
            patch(
                "app.services.agent_service.time.time",
                # The imported time module is shared with trace_service:
                # run_started, start_time, loop check, then timeout trace.
                side_effect=[100.0, 100.0, 131.0, 131.0],
            ),
            patch("app.services.agent_service.generate_with_tools") as generate_with_tools,
        ):
            answer = run_agent("分析订单异常", session_id="session-a")

        self.assertIn("超时", answer)
        generate_with_tools.assert_not_called()
        self.assertEqual("timeout", self.trace_sink.events[-1].event)


if __name__ == "__main__":
    unittest.main()
