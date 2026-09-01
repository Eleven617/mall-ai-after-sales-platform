import time
import unittest
from unittest.mock import patch

from app.schemas.customer_service import CustomerServiceRequest
from app.schemas.agent import AgentRunResult
from app.schemas.intent import IntentResponse, IntentToolCall
from app.schemas.rag import RagSource
from app.schemas.after_sales_application import (
    AfterSalesApplicationView,
    AfterSalesEligibilityView,
    AfterSalesFlowResult,
    AfterSalesRequestExtraction,
)
from app.schemas.tool import ToolCall
from app.services.conversation_state import (
    get_conversation_state,
    reset_conversation_state_for_tests,
    save_pending_tool_call,
    set_conversation_manager_for_tests,
)
from app.services.customer_service import handle_customer_message
from app.services.durable_diagnosis import (
    DurableDiagnosisManager,
    SanitizedMemorySaver,
    set_durable_diagnosis_manager_for_tests,
)
from app.services.intent_service import IntentServiceError
from app.services.llm_service import LLMResponse
from app.services.rag_service import RagAnswer
from app.services.tool_context import ToolExecutionContext


AUTHORIZATION = "Bearer user-token"
ORDER_WITH_TWO_ITEMS = {
    "order_sn": "202607240001",
    "status_code": 2,
    "status": "已发货",
    "order_items": [
        {
            "order_item_id": 501,
            "product_name": "无线耳机",
            "product_attr": "颜色：黑色",
            "product_quantity": 1,
        },
        {
            "order_item_id": 502,
            "product_name": "手机壳",
            "product_attr": "颜色：蓝色",
            "product_quantity": 1,
        },
    ],
}
POLICY_ANSWER = RagAnswer(
    answer="质量问题导致退货时，退货运费由商家承担。",
    retrieved_context=["质量问题导致退货时，退货运费由商家承担。"],
    sources=[
        RagSource(
            chunk_id="policy-transport-001",
            document_name="售后政策知识库",
            section_path="售后政策知识库 > 退货运费",
            distance=0.18,
        )
    ],
)

ELIGIBLE_AFTER_SALES = AfterSalesEligibilityView(
    order_sn="202607240001",
    application_type="return_refund",
    application_type_label="退货退款",
    order_status="已发货",
    eligible=True,
    requires_product_selection=False,
    decision="eligible_to_apply",
    message="订单状态允许提交售后申请，最终处理结果以审核和适用政策为准。",
    product_name="无线耳机",
    product_attr="颜色：黑色",
)

SUBMITTED_AFTER_SALES = AfterSalesApplicationView(
    application_id=801,
    order_sn="202607240001",
    application_type="return_refund",
    application_type_label="退货退款",
    product_name="无线耳机",
    product_attr="颜色：黑色",
    reason="质量问题",
    description="商品损坏",
    status="pending_review",
    status_label="待审核",
    created_at=1720000000000,
    can_cancel=True,
    can_modify=True,
)


class CustomerServiceWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_conversation_state_for_tests()
        set_durable_diagnosis_manager_for_tests(
            DurableDiagnosisManager(SanitizedMemorySaver(), ttl_seconds=600)
        )
        self.context = ToolExecutionContext(authorization=AUTHORIZATION)

    def tearDown(self) -> None:
        set_conversation_manager_for_tests(None)
        set_durable_diagnosis_manager_for_tests(None)

    def test_ambiguous_pending_order_keeps_tool_contract_without_execution(self) -> None:
        save_pending_tool_call(
            "session-a",
            ToolCall(name="logistics_service", arguments={}),
        )

        with patch("app.services.customer_service.call_tool") as call_tool:
            response = handle_customer_message(
                CustomerServiceRequest(
                    session_id="session-a",
                    message="202607240001 或者 202607240002 都有问题",
                ),
                self.context,
            )

        self.assertEqual("ask_missing_info", response.intent.route)
        self.assertFalse(response.intent.need_tool)
        self.assertIsNotNone(response.intent.tool_call)
        self.assertEqual("logistics_service", response.intent.tool_call.name)
        self.assertIn("多个", response.answer)
        self.assertIsNotNone(get_conversation_state("session-a").pending_tool_call)
        call_tool.assert_not_called()

    @patch("app.services.after_sales_application_service.create_after_sales_application")
    @patch("app.services.customer_service.run_unified_after_sales_graph")
    @patch("app.services.customer_service.run_unified_after_sales_investigation")
    @patch("app.services.customer_service.answer_after_sales_question")
    @patch("app.services.customer_service.call_tool")
    @patch("app.services.customer_service.detect_intent")
    def test_model_unavailability_stops_before_any_downstream_execution(
        self,
        detect_intent,
        call_tool,
        answer_after_sales_question,
        run_unified_after_sales_investigation,
        run_unified_after_sales_graph,
        create_after_sales_application,
    ) -> None:
        detect_intent.side_effect = IntentServiceError("模型路由暂不可用")

        response = handle_customer_message(
            CustomerServiceRequest(
                session_id="session-fallback",
                message="申请退货",
            ),
            self.context,
        )

        self.assertEqual("system", response.intent.source)
        self.assertEqual("chat", response.intent.route)
        self.assertIn("智能客服暂不可用", response.answer)
        detect_intent.assert_called_once()
        call_tool.assert_not_called()
        answer_after_sales_question.assert_not_called()
        run_unified_after_sales_investigation.assert_not_called()
        run_unified_after_sales_graph.assert_not_called()
        create_after_sales_application.assert_not_called()

    @patch("app.services.customer_service.run_unified_after_sales_investigation")
    @patch("app.services.customer_service.detect_intent")
    def test_delivery_diagnosis_route_is_selected_by_structured_model_output(
        self,
        detect_intent,
        run_unified_after_sales_investigation,
    ) -> None:
        detect_intent.return_value = IntentResponse(
            intent="query_logistics",
            route="agent",
            need_tool=True,
            tool_call=IntentToolCall(name="analysis_agent", arguments={}),
        )
        run_unified_after_sales_investigation.return_value = AgentRunResult(
            answer="已完成订单异常诊断。"
        )

        response = handle_customer_message(
            CustomerServiceRequest(
                session_id="session-delivery-diagnosis",
                message="订单号 202607240001 为什么一直没到，我现在怎么办？",
            ),
            self.context,
        )

        self.assertEqual("llm", response.intent.source)
        self.assertEqual("agent", response.intent.route)
        self.assertEqual("已完成订单异常诊断。", response.answer)
        detect_intent.assert_called_once()
        self.assertTrue(
            run_unified_after_sales_investigation.call_args.kwargs["require_order_identifier"]
        )

    @patch("app.services.customer_service.run_unified_after_sales_graph")
    @patch("app.services.customer_service.detect_intent")
    def test_short_after_sales_requests_always_use_structured_intent_routing(
        self,
        detect_intent,
        run_unified_after_sales_graph,
    ) -> None:
        cases = (
            ("申请退货", "apply_after_sales"),
            ("能否退款", "after_sales_eligibility"),
            ("查售后进度", "status_after_sales"),
            ("帮我处理上次那个售后，东西还是坏的", "follow_up_after_sales"),
        )

        def graph_result(**kwargs):
            self.assertFalse(kwargs.get("resume_only", False))
            return AfterSalesFlowResult(answer=f"已进入 {kwargs['intent_name']} 流程。")

        run_unified_after_sales_graph.side_effect = graph_result
        for index, (message, action) in enumerate(cases, start=1):
            with self.subTest(message=message):
                detect_intent.reset_mock()
                detect_intent.return_value = IntentResponse(
                    intent=action,
                    route="after_sales_flow",
                    need_tool=False,
                )
                response = handle_customer_message(
                    CustomerServiceRequest(session_id=f"semantic-route-{index}", message=message),
                    self.context,
                )

                self.assertEqual(action, response.intent.intent)
                self.assertEqual("after_sales_flow", response.intent.route)
                detect_intent.assert_called_once()
                self.assertEqual(message, detect_intent.call_args.args[0])
                self.assertIn(action, response.answer)

        self.assertEqual(4, run_unified_after_sales_graph.call_count)

    @patch("app.services.customer_service.run_unified_after_sales_graph")
    @patch("app.services.customer_service.detect_intent")
    def test_all_after_sales_actions_dispatch_only_to_the_unified_graph(
        self,
        detect_intent,
        run_unified_after_sales_graph,
    ) -> None:
        actions = (
            "after_sales_policy",
            "after_sales_eligibility",
            "apply_after_sales",
            "list_after_sales",
            "status_after_sales",
            "cancel_after_sales",
            "modify_after_sales",
            "follow_up_after_sales",
        )
        run_unified_after_sales_graph.side_effect = lambda **kwargs: AfterSalesFlowResult(
            answer=f"统一流程：{kwargs['intent_name']}"
        )
        for index, action in enumerate(actions, start=1):
            with self.subTest(action=action):
                detect_intent.reset_mock()
                detect_intent.return_value = IntentResponse(
                    intent=action,
                    route="after_sales_flow",
                    need_tool=False,
                )
                response = handle_customer_message(
                    CustomerServiceRequest(session_id=f"closed-route-{index}", message="请处理我的请求"),
                    self.context,
                )

                self.assertEqual(action, response.intent.intent)
                detect_intent.assert_called_once()
                self.assertEqual(action, run_unified_after_sales_graph.call_args.kwargs["intent_name"])

        self.assertEqual(8, run_unified_after_sales_graph.call_count)

    @patch("app.services.customer_service.run_unified_after_sales_investigation")
    @patch("app.services.customer_service.detect_intent")
    def test_agent_route_uses_unified_investigation_without_legacy_pending_tool_state(
        self,
        detect_intent,
        run_unified_after_sales_investigation,
    ) -> None:
        detect_intent.return_value = IntentResponse(
            intent="query_logistics",
            route="agent",
            need_tool=True,
            tool_call=IntentToolCall(name="analysis_agent", arguments={}),
        )
        run_unified_after_sales_investigation.return_value = AgentRunResult(
            answer="请提供订单号；收到后会继续只读诊断。",
            pending_tool_call=ToolCall(name="order_service", arguments={}),
            durable_checkpoint_pending=True,
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id="session-a", message="订单为什么没有按预期送达？"),
            self.context,
        )

        self.assertIsNotNone(response.pending_action)
        self.assertTrue(response.pending_action.resumable)
        self.assertIsNone(get_conversation_state("session-a").pending_tool_call)
        self.assertEqual(
            "session-a",
            run_unified_after_sales_investigation.call_args.kwargs["session_id"],
        )
        self.assertTrue(
            run_unified_after_sales_investigation.call_args.kwargs["require_order_identifier"]
        )

    @patch("app.services.agent_service.call_tool")
    @patch("app.services.unified_after_sales_graph.generate_with_tools")
    @patch("app.services.customer_service.detect_intent")
    def test_diagnosis_missing_identifier_uses_durable_resume_not_old_pending_tool_state(
        self,
        detect_intent,
        generate_with_tools,
        call_tool,
    ) -> None:
        context = ToolExecutionContext(authorization=AUTHORIZATION, member_id=8)
        detect_intent.return_value = IntentResponse(
            intent="query_logistics",
            route="agent",
            need_tool=True,
            tool_call=IntentToolCall(name="analysis_agent", arguments={}),
        )
        generate_with_tools.return_value = LLMResponse(
            tool_calls=[{"name": "logistics_service", "arguments": {}}]
        )

        paused = handle_customer_message(
            CustomerServiceRequest(session_id="durable-diagnosis", message="订单一直没到怎么办"),
            context,
        )

        self.assertIsNotNone(paused.pending_action)
        self.assertTrue(paused.pending_action.resumable)
        self.assertIsNone(get_conversation_state("durable-diagnosis").pending_tool_call)
        self.assertIn("不会创建售后单", paused.answer)
        call_tool.assert_not_called()
        generate_with_tools.assert_not_called()

        call_tool.side_effect = [
            {
                "order_sn": "202607240001",
                "status": "已发货",
                "delivery_company": "测试物流",
                "tracking_no": "TEST-001",
                "product_names": ["测试耳机"],
            },
            {
                "order_sn": "202607240001",
                "company": "测试物流",
                "tracking_no": "TEST-001",
                "order_status": "运输中",
                "product_names": ["测试耳机"],
            },
        ]
        resumed = handle_customer_message(
            CustomerServiceRequest(session_id="durable-diagnosis", message="订单号：202607240001"),
            context,
        )

        self.assertEqual("system", resumed.intent.source)
        self.assertEqual("tool_calling", resumed.intent.route)
        self.assertIn("测试物流", resumed.answer)
        self.assertEqual(2, call_tool.call_count)
        # The second message is a Command(resume=opaque-ref), not a new model
        # routing call or a legacy pending-tool continuation.
        detect_intent.assert_called_once()
        self.assertEqual("202607240001", call_tool.call_args_list[0].args[0].arguments["order_sn"])
        self.assertEqual("logistics_service", call_tool.call_args_list[1].args[0].name)

    @patch("app.services.customer_service.detect_intent")
    def test_explicit_cancel_clears_pending_logistics_without_execution(
        self,
        detect_intent,
    ) -> None:
        save_pending_tool_call(
            "session-a",
            ToolCall(name="logistics_service", arguments={}),
        )

        with patch("app.services.customer_service.call_tool") as call_tool:
            cancelled = handle_customer_message(
                CustomerServiceRequest(session_id="session-a", message="取消查询"),
                self.context,
            )

        self.assertEqual("chat", cancelled.intent.route)
        self.assertIn("已取消", cancelled.answer)
        self.assertIsNone(get_conversation_state("session-a").pending_tool_call)
        call_tool.assert_not_called()
        detect_intent.assert_not_called()

        detect_intent.return_value = IntentResponse(
            intent="general_chat",
            route="chat",
            need_tool=False,
            chat_scope="capability",
        )

        follow_up = handle_customer_message(
                CustomerServiceRequest(
                    session_id="session-a",
                    message="商城有什么活动？",
                ),
            self.context,
        )

        self.assertEqual("chat", follow_up.intent.route)
        self.assertIn("订单、物流和库存", follow_up.answer)
        detect_intent.assert_called_once()

    @patch("app.services.customer_service.call_tool")
    @patch("app.services.customer_service.detect_intent")
    def test_direct_logistics_answer_and_fact_card_are_server_rendered(
        self,
        detect_intent,
        call_tool,
    ) -> None:
        detect_intent.return_value = IntentResponse(
            intent="query_logistics",
            route="tool_calling",
            need_tool=True,
            tool_call=IntentToolCall(
                name="logistics_service",
                arguments={"order_sn": "202607240001"},
            ),
        )
        call_tool.return_value = {
            "order_sn": "202607240001",
            "company": "测试物流",
            "tracking_no": "TEST-001",
            "order_status": "运输中",
            "product_names": ["测试耳机"],
        }

        response = handle_customer_message(
            CustomerServiceRequest(session_id="session-a", message="请帮忙看这个"),
            self.context,
        )

        self.assertIn("测试物流", response.answer)
        self.assertIn("运输中", response.answer)
        self.assertIsNotNone(response.verified_facts)
        self.assertEqual("物流信息（商城系统）", response.verified_facts[0].title)
        self.assertNotIn("order_item_id", response.verified_facts[0].model_dump_json())

    @patch("app.services.unified_after_sales_graph.answer_after_sales_question")
    @patch("app.services.customer_service.detect_intent")
    def test_policy_answer_is_returned_through_the_unified_graph_without_narration(
        self,
        detect_intent,
        answer_after_sales_question,
    ) -> None:
        original_answer = "质量问题退货时，商家承担退货运费。"
        detect_intent.return_value = IntentResponse(
            intent="after_sales_policy",
            route="after_sales_flow",
            need_tool=False,
        )
        answer_after_sales_question.return_value = RagAnswer(
            answer=original_answer,
            retrieved_context=[original_answer],
            sources=[],
        )

        response = handle_customer_message(
            CustomerServiceRequest(
                session_id="session-rag-answer",
                message="质量问题退货运费谁承担？",
            ),
            self.context,
        )

        self.assertEqual(original_answer, response.answer)
        answer_after_sales_question.assert_called_once_with("质量问题退货运费谁承担？")

    @patch("app.services.customer_service.detect_intent")
    @patch("app.services.after_sales_application_service.create_after_sales_application")
    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_unified_after_sales_draft_proposal_and_confirmation_are_wired_through_entrypoint(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
        create_after_sales_application,
        detect_intent,
    ) -> None:
        detect_intent.return_value = IntentResponse(
            intent="apply_after_sales",
            route="after_sales_flow",
            need_tool=False,
        )
        extract_after_sales_request.side_effect = [
            AfterSalesRequestExtraction(
                goal="apply",
                application_type="return_refund",
                reason="质量问题",
                description="商品损坏",
            ),
            AfterSalesRequestExtraction(product_hint="耳机"),
        ]
        get_order_snapshot.return_value = ORDER_WITH_TWO_ITEMS
        check_after_sales_eligibility.return_value = ELIGIBLE_AFTER_SALES
        answer_after_sales_question.return_value = POLICY_ANSWER
        create_after_sales_application.return_value = SUBMITTED_AFTER_SALES

        first = handle_customer_message(
            CustomerServiceRequest(
                session_id="session-a",
                message="订单号：202607240001，商品坏了，申请退货",
            ),
            self.context,
        )

        self.assertEqual("after_sales_flow", first.intent.route)
        self.assertIsNotNone(first.after_sales_draft)
        self.assertEqual(["product"], first.after_sales_draft.missing_fields)
        self.assertEqual(2, len(first.after_sales_draft.product_options))
        self.assertIsNone(first.after_sales_proposal)

        second = handle_customer_message(
            CustomerServiceRequest(session_id="session-a", message="我要退耳机"),
            self.context,
        )

        self.assertIsNotNone(second.after_sales_proposal)
        self.assertEqual("无线耳机", second.after_sales_proposal.product_name)
        self.assertEqual("policy-transport-001", second.rag_sources[0].chunk_id)
        self.assertNotIn("order_item_id", second.after_sales_proposal.model_dump())
        self.assertIsNone(get_conversation_state("session-a").pending_after_sales_draft)

        third = handle_customer_message(
            CustomerServiceRequest(session_id="session-a", message="确认"),
            self.context,
        )

        self.assertIn("已提交", third.answer)
        self.assertIsNone(get_conversation_state("session-a").pending_after_sales_proposal)
        self.assertIsNotNone(third.submitted_after_sales_application)
        self.assertEqual(801, third.submitted_after_sales_application.application_id)
        create_after_sales_application.assert_called_once()
        submitted_kwargs = create_after_sales_application.call_args.kwargs
        self.assertEqual("202607240001", submitted_kwargs["order_sn"])
        self.assertEqual(501, submitted_kwargs["order_item_id"])
        self.assertEqual("质量问题", submitted_kwargs["reason"])
        self.assertEqual("商品损坏", submitted_kwargs["description"])
        self.assertEqual(AUTHORIZATION, submitted_kwargs["authorization"])
        self.assertEqual(32, len(submitted_kwargs["idempotency_key"]))
        # The later product choice and confirmation were resumed from
        # server-owned state and did not need a second model route decision.
        detect_intent.assert_called_once()


if __name__ == "__main__":
    unittest.main()
