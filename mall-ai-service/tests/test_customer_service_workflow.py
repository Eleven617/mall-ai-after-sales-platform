import time
import unittest
from unittest.mock import patch

from app.schemas.after_sales_application import (
    AfterSalesApplicationView,
    AfterSalesEligibilityView,
    AfterSalesFlowResult,
    AfterSalesRequestExtraction,
    PendingAfterSalesProposal,
)
from app.schemas.agent import AgentRunResult
from app.schemas.customer_service import CustomerServiceRequest
from app.schemas.diagnosis import DiagnosisHandoff, DiagnosisResult
from app.schemas.intent import IntentToolCall
from app.schemas.rag import RagSource
from app.schemas.task_orchestration import TurnPlan
from app.schemas.tool import ToolCall
from app.services.after_sales_application_state import (
    owner_fingerprint,
    save_pending_after_sales_proposal,
    session_fingerprint,
)
from app.services.conversation_state import (
    get_conversation_state,
    reset_conversation_state_for_tests,
    set_conversation_manager_for_tests,
)
from app.services.customer_service import handle_customer_message
from app.services.intent_service import IntentServiceError
from app.services.rag_service import RagAnswer
from app.services.tool_context import ToolExecutionContext


AUTHORIZATION = "Bearer synthetic-member-token"
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
        self.context = ToolExecutionContext(authorization=AUTHORIZATION)

    def tearDown(self) -> None:
        set_conversation_manager_for_tests(None)

    @patch("app.services.customer_service.answer_after_sales_question")
    @patch("app.services.customer_service.detect_intent")
    def test_every_new_message_uses_turn_plan_before_policy_rag_dispatch(
        self,
        detect_intent,
        answer_after_sales_question,
    ) -> None:
        detect_intent.return_value = _turn_plan(
            intent="after_sales_policy",
            route="rag",
            relation="standalone_answer",
        )
        answer_after_sales_question.return_value = POLICY_ANSWER

        response = handle_customer_message(
            CustomerServiceRequest(session_id="session-a", message="退货运费谁承担？"),
            self.context,
        )

        self.assertEqual("after_sales_policy", response.intent.intent)
        detect_intent.assert_called_once()
        answer_after_sales_question.assert_called_once_with("退货运费谁承担？")

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
            CustomerServiceRequest(session_id="session-fallback", message="申请退货"),
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
    def test_agent_route_creates_normal_waiting_task_without_checkpoint_or_legacy_pending_field(
        self,
        detect_intent,
        run_unified_after_sales_investigation,
    ) -> None:
        detect_intent.return_value = _turn_plan(
            intent="query_logistics",
            route="agent",
            relation="start_new_task",
            task_kind="order_diagnosis",
        )
        run_unified_after_sales_investigation.return_value = AgentRunResult(
            answer="请提供订单号；收到后会继续只读诊断。",
            pending_tool_call=ToolCall(name="order_service", arguments={}),
            durable_checkpoint_pending=False,
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id="session-a", message="订单为什么没有按预期送达？"),
            self.context,
        )

        self.assertIsNotNone(response.task)
        self.assertEqual("active", response.task.task_status)
        self.assertEqual("订单异常诊断", response.task.task_label)
        self.assertIsNone(get_conversation_state("session-a").pending_tool_call)
        self.assertTrue(run_unified_after_sales_investigation.call_args.kwargs["requires_order_facts"])

    @patch("app.services.customer_service.register_case_handoff")
    @patch("app.services.customer_service.run_unified_after_sales_investigation")
    @patch("app.services.customer_service.detect_intent")
    def test_unverified_agent_result_is_held_as_waiting_task_without_handoff(
        self,
        detect_intent,
        run_unified_after_sales_investigation,
        register_case_handoff,
    ) -> None:
        detect_intent.return_value = _turn_plan(
            intent="query_logistics",
            route="agent",
            relation="start_new_task",
            task_kind="order_diagnosis",
        )
        run_unified_after_sales_investigation.return_value = AgentRunResult(
            answer="未经事实核验的模型文本",
            diagnosis=DiagnosisResult(
                category="policy_insufficient",
                evidence_status="insufficient",
                handoff=DiagnosisHandoff(
                    reason="insufficient_evidence",
                    summary="合成摘要",
                ),
            ),
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id="unverified-agent", message="订单为什么没发货？"),
            self.context,
        )

        self.assertEqual("needs_order_identifier", response.diagnosis.category)
        self.assertIsNotNone(response.task)
        self.assertEqual("active", response.task.task_status)
        self.assertIn("订单号", response.answer)
        self.assertIsNone(get_conversation_state("unverified-agent").pending_tool_call)
        register_case_handoff.assert_not_called()

    @patch("app.services.customer_service.answer_after_sales_question")
    @patch("app.services.customer_service.run_unified_after_sales_investigation")
    @patch("app.services.customer_service.detect_intent")
    def test_policy_detour_pauses_and_then_naturally_resumes_order_diagnosis(
        self,
        detect_intent,
        run_unified_after_sales_investigation,
        answer_after_sales_question,
    ) -> None:
        detect_intent.side_effect = [
            _turn_plan(
                intent="query_logistics",
                route="agent",
                relation="start_new_task",
                task_kind="order_diagnosis",
            ),
            _turn_plan(
                intent="after_sales_policy",
                route="rag",
                relation="temporary_detour",
            ),
            _turn_plan(
                intent="query_logistics",
                route="agent",
                relation="resume_paused",
                task_kind="order_diagnosis",
            ),
        ]
        run_unified_after_sales_investigation.side_effect = [
            AgentRunResult(
                answer="请提供订单号；收到后继续只读核验。",
                pending_tool_call=ToolCall(name="logistics_service", arguments={}),
            ),
            AgentRunResult(answer="已完成订单与物流核验。"),
        ]
        answer_after_sales_question.return_value = RagAnswer(
            answer="政策已说明。",
            retrieved_context=[],
            sources=[],
        )

        waiting = handle_customer_message(
            CustomerServiceRequest(session_id="task-switch", message="订单为什么还没到？"),
            self.context,
        )
        detour = handle_customer_message(
            CustomerServiceRequest(session_id="task-switch", message="那退款运费谁承担？"),
            self.context,
        )
        resumed = handle_customer_message(
            CustomerServiceRequest(session_id="task-switch", message="订单号是 202607240001"),
            self.context,
        )

        self.assertEqual("active", waiting.task.task_status)
        self.assertEqual("paused", detour.task.task_status)
        self.assertEqual("政策已说明。", detour.answer)
        self.assertEqual("已完成订单与物流核验。", resumed.answer)
        self.assertIsNone(resumed.task)
        state = get_conversation_state("task-switch")
        self.assertIsNone(state.active_task)
        self.assertIsNone(state.paused_task)
        self.assertIsNone(state.pending_tool_call)
        self.assertEqual(3, detect_intent.call_count)
        self.assertEqual(2, run_unified_after_sales_investigation.call_count)

    @patch("app.services.customer_service.run_unified_after_sales_investigation")
    @patch("app.services.customer_service.detect_intent")
    def test_general_chat_detour_keeps_the_waiting_task_without_legacy_pending_route(
        self,
        detect_intent,
        run_unified_after_sales_investigation,
    ) -> None:
        detect_intent.side_effect = [
            _turn_plan(
                intent="query_order_status",
                route="agent",
                relation="start_new_task",
                task_kind="order_diagnosis",
            ),
            _turn_plan(
                intent="general_chat",
                route="chat",
                relation="temporary_detour",
                chat_scope="capability",
            ),
        ]
        run_unified_after_sales_investigation.return_value = AgentRunResult(
            answer="请提供订单号。",
            pending_tool_call=ToolCall(name="order_service", arguments={}),
        )

        handle_customer_message(
            CustomerServiceRequest(session_id="chat-detour", message="订单状态怎么样？"),
            self.context,
        )
        reply = handle_customer_message(
            CustomerServiceRequest(session_id="chat-detour", message="你能做什么？"),
            self.context,
        )

        self.assertIn("订单、物流和库存", reply.answer)
        self.assertEqual("paused", reply.task.task_status)
        state = get_conversation_state("chat-detour")
        self.assertIsNone(state.active_task)
        self.assertEqual("order_diagnosis", state.paused_task.kind)
        self.assertIsNone(state.pending_tool_call)
        self.assertEqual(2, detect_intent.call_count)
        run_unified_after_sales_investigation.assert_called_once()

    @patch("app.services.after_sales_application_service.create_after_sales_application")
    @patch("app.services.customer_service.answer_after_sales_question")
    @patch("app.services.customer_service.detect_intent")
    def test_policy_question_does_not_submit_a_transaction_gate_but_natural_confirmation_does(
        self,
        detect_intent,
        answer_after_sales_question,
        create_after_sales_application,
    ) -> None:
        session_id = "proposal-detour"
        save_pending_after_sales_proposal(session_id, _proposal(session_id))
        detect_intent.side_effect = [
            _turn_plan(
                intent="after_sales_policy",
                route="rag",
                relation="standalone_answer",
            ),
            _turn_plan(
                intent="apply_after_sales",
                route="after_sales_flow",
                relation="standalone_answer",
                confirmation="confirm",
            ),
        ]
        answer_after_sales_question.return_value = RagAnswer(
            answer="政策回答。",
            retrieved_context=[],
            sources=[],
        )

        with patch(
            "app.services.task_orchestration_service.handle_pending_after_sales_confirmation",
            return_value=AfterSalesFlowResult(answer="已提交。"),
        ) as confirm_gate:
            policy = handle_customer_message(
                CustomerServiceRequest(session_id=session_id, message="退货运费谁承担？"),
                self.context,
            )
            confirmed = handle_customer_message(
                CustomerServiceRequest(session_id=session_id, message="那就按这个办"),
                self.context,
            )

        self.assertEqual("政策回答。", policy.answer)
        self.assertIsNotNone(get_conversation_state(session_id).pending_after_sales_proposal)
        self.assertIsNotNone(get_conversation_state(session_id).transaction_gate)
        confirm_gate.assert_called_once_with(session_id, "确认", AUTHORIZATION, None)
        self.assertEqual("已提交。", confirmed.answer)
        answer_after_sales_question.assert_called_once_with("退货运费谁承担？")
        create_after_sales_application.assert_not_called()

    @patch("app.services.after_sales_application_service.create_after_sales_application")
    @patch("app.services.customer_service.detect_intent")
    def test_natural_gate_cancellation_only_withdraws_the_proposal_and_never_writes(
        self,
        detect_intent,
        create_after_sales_application,
    ) -> None:
        session_id = "proposal-cancel"
        save_pending_after_sales_proposal(session_id, _proposal(session_id))
        detect_intent.return_value = _turn_plan(
            intent="apply_after_sales",
            route="after_sales_flow",
            relation="standalone_answer",
            confirmation="cancel",
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id=session_id, message="先不用了"),
            self.context,
        )

        self.assertIn("已取消", response.answer)
        self.assertIsNone(get_conversation_state(session_id).pending_after_sales_proposal)
        self.assertIsNone(get_conversation_state(session_id).transaction_gate)
        create_after_sales_application.assert_not_called()

    @patch("app.services.customer_service.run_unified_after_sales_graph")
    @patch("app.services.customer_service.detect_intent")
    def test_new_after_sales_task_is_dispatched_while_existing_transaction_gate_is_preserved(
        self,
        detect_intent,
        run_unified_after_sales_graph,
    ) -> None:
        session_id = "proposal-preserved"
        proposal = _proposal(session_id)
        save_pending_after_sales_proposal(session_id, proposal)
        detect_intent.return_value = _turn_plan(
            intent="apply_after_sales",
            route="after_sales_flow",
            relation="start_new_task",
            task_kind="after_sales_draft",
        )

        run_unified_after_sales_graph.return_value = AfterSalesFlowResult(
            answer="已开始收集另一笔售后申请的信息。"
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id=session_id, message="我还想再申请另一笔售后"),
            self.context,
        )

        self.assertIn("开始收集", response.answer)
        self.assertEqual(proposal, get_conversation_state(session_id).pending_after_sales_proposal)
        self.assertIsNotNone(get_conversation_state(session_id).transaction_gate)
        run_unified_after_sales_graph.assert_called_once_with(
            session_id=session_id,
            message="我还想再申请另一笔售后",
            authorization=AUTHORIZATION,
            member_id=None,
            intent_name="apply_after_sales",
        )

    @patch("app.services.customer_service.call_tool")
    @patch("app.services.customer_service.detect_intent")
    def test_direct_logistics_answer_and_fact_card_are_server_rendered(
        self,
        detect_intent,
        call_tool,
    ) -> None:
        detect_intent.return_value = _turn_plan(
            intent="query_logistics",
            route="tool_calling",
            relation="standalone_answer",
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
            CustomerServiceRequest(session_id="direct-logistics", message="请帮忙看这个"),
            self.context,
        )

        self.assertIn("测试物流", response.answer)
        self.assertIn("运输中", response.answer)
        self.assertIsNotNone(response.verified_facts)
        self.assertEqual("物流信息（商城系统）", response.verified_facts[0].title)
        self.assertNotIn("order_item_id", response.verified_facts[0].model_dump_json())

    @patch("app.services.customer_service.answer_after_sales_question")
    @patch("app.services.customer_service.detect_intent")
    def test_policy_answer_is_returned_through_read_only_rag_without_narration(
        self,
        detect_intent,
        answer_after_sales_question,
    ) -> None:
        original_answer = "质量问题退货时，商家承担退货运费。"
        detect_intent.return_value = _turn_plan(
            intent="after_sales_policy",
            route="rag",
            relation="standalone_answer",
        )
        answer_after_sales_question.return_value = RagAnswer(
            answer=original_answer,
            retrieved_context=[original_answer],
            sources=[],
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id="session-rag-answer", message="质量问题退货运费谁承担？"),
            self.context,
        )

        self.assertEqual(original_answer, response.answer)
        answer_after_sales_question.assert_called_once_with("质量问题退货运费谁承担？")

    @patch("app.services.customer_service.run_unified_after_sales_graph")
    @patch("app.services.customer_service.answer_after_sales_question")
    @patch("app.services.customer_service.detect_intent")
    def test_policy_rag_dependency_failure_stops_without_entering_business_flow(
        self,
        detect_intent,
        answer_after_sales_question,
        run_unified_after_sales_graph,
    ) -> None:
        detect_intent.return_value = _turn_plan(
            intent="after_sales_policy",
            route="rag",
            relation="standalone_answer",
        )
        answer_after_sales_question.return_value = RagAnswer(
            answer="synthetic retrieval outage",
            retrieved_context=[],
            sources=[],
            retrieval_unavailable=True,
        )

        response = handle_customer_message(
            CustomerServiceRequest(session_id="policy-rag-outage", message="退货运费谁承担？"),
            self.context,
        )

        self.assertIn("检索服务暂时不可用", response.answer)
        self.assertIsNone(response.rag_sources)
        run_unified_after_sales_graph.assert_not_called()

    @patch("app.services.customer_service.detect_intent")
    @patch("app.services.after_sales_application_service.create_after_sales_application")
    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_draft_proposal_and_confirmation_stay_behind_three_task_aware_turns(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
        create_after_sales_application,
        detect_intent,
    ) -> None:
        detect_intent.side_effect = [
            _turn_plan(
                intent="apply_after_sales",
                route="after_sales_flow",
                relation="start_new_task",
                task_kind="after_sales_draft",
            ),
            _turn_plan(
                intent="apply_after_sales",
                route="after_sales_flow",
                relation="continue_active",
                task_kind="after_sales_draft",
            ),
            _turn_plan(
                intent="apply_after_sales",
                route="after_sales_flow",
                relation="standalone_answer",
                confirmation="confirm",
            ),
        ]
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
            CustomerServiceRequest(session_id="apply-flow", message="订单号：202607240001，商品坏了，申请退货"),
            self.context,
        )
        second = handle_customer_message(
            CustomerServiceRequest(session_id="apply-flow", message="我要退耳机"),
            self.context,
        )
        self.assertIsNotNone(get_conversation_state("apply-flow").transaction_gate)
        third = handle_customer_message(
            CustomerServiceRequest(session_id="apply-flow", message="那就按这个办"),
            self.context,
        )

        self.assertIsNotNone(first.after_sales_draft)
        self.assertEqual(["product"], first.after_sales_draft.missing_fields)
        self.assertEqual(2, len(first.after_sales_draft.product_options))
        self.assertIsNotNone(second.after_sales_proposal)
        self.assertEqual("无线耳机", second.after_sales_proposal.product_name)
        self.assertNotIn("order_item_id", second.after_sales_proposal.model_dump())
        self.assertIn("已提交", third.answer)
        self.assertIsNone(get_conversation_state("apply-flow").pending_after_sales_proposal)
        self.assertIsNotNone(third.submitted_after_sales_application)
        create_after_sales_application.assert_called_once()
        submitted_kwargs = create_after_sales_application.call_args.kwargs
        self.assertEqual("202607240001", submitted_kwargs["order_sn"])
        self.assertEqual(501, submitted_kwargs["order_item_id"])
        self.assertEqual("质量问题", submitted_kwargs["reason"])
        self.assertEqual("商品损坏", submitted_kwargs["description"])
        self.assertEqual(AUTHORIZATION, submitted_kwargs["authorization"])
        self.assertEqual(32, len(submitted_kwargs["idempotency_key"]))
        self.assertEqual(3, detect_intent.call_count)


def _turn_plan(
    *,
    intent: str,
    route: str,
    relation: str,
    task_kind: str | None = None,
    confirmation: str = "none",
    need_tool: bool = False,
    tool_call: IntentToolCall | None = None,
    chat_scope: str | None = None,
) -> TurnPlan:
    if route == "agent":
        need_tool = True
        tool_call = IntentToolCall(name="analysis_agent", arguments={})
    rationale = {
        "continue_active": "active_task_match",
        "temporary_detour": "temporary_detour",
        "resume_paused": "paused_task_match",
        "start_new_task": "new_long_running_goal",
        "standalone_answer": "standalone_question",
        "discard_active": "explicit_task_abandonment",
        "discard_paused": "explicit_task_abandonment",
        "resolve_task_conflict": "task_conflict",
    }[relation]
    return TurnPlan(
        business_intent=intent,
        task_relation=relation,
        route=route,
        task_kind=task_kind,
        confirmation_intent=confirmation,
        rationale_code=rationale,
        need_tool=need_tool,
        tool_call=tool_call,
        reply=None,
        chat_scope=chat_scope,
    )


def _proposal(session_id: str) -> PendingAfterSalesProposal:
    return PendingAfterSalesProposal(
        proposal_id="a" * 32,
        application_type="return_refund",
        order_sn="202607240001",
        order_item_id=501,
        product_name="无线耳机",
        product_attr="颜色：黑色",
        reason="质量问题",
        description="商品损坏",
        owner_fingerprint=owner_fingerprint(AUTHORIZATION),
        session_fingerprint=session_fingerprint(session_id),
        content_hash="b" * 64,
        expires_at=time.time() + 600,
    )


if __name__ == "__main__":
    unittest.main()
