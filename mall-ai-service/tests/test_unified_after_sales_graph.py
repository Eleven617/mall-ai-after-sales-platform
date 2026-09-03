import unittest
from unittest.mock import patch

from app.schemas.after_sales_application import AfterSalesApplicationView
from app.schemas.after_sales_application import AfterSalesRequestExtraction
from app.schemas.customer_service import CustomerServiceResponse, to_public_customer_service_response
from app.schemas.intent import IntentResponse
from app.schemas.rag import RagSource
from app.services.llm_service import LLMResponse
from app.services.tool_context import ToolExecutionContext
from app.services.after_sales_application_service import (
    handle_pending_after_sales_action_confirmation,
    prepare_after_sales_action,
)
from app.services.conversation_state import (
    get_conversation_state,
    reset_conversation_state_for_tests,
    set_conversation_manager_for_tests,
)
from app.services.unified_after_sales_graph import (
    _narrative_from_message,
    _normalize_modification_for_application,
    run_unified_after_sales_graph,
    run_unified_after_sales_investigation,
)


AUTH_A = "Bearer member-a"
AUTH_B = "Bearer member-b"


def application(
    application_id: int,
    *,
    status: str = "pending_review",
    can_cancel: bool = True,
    can_modify: bool = True,
    can_supplement: bool = False,
) -> AfterSalesApplicationView:
    return AfterSalesApplicationView(
        application_id=application_id,
        order_sn=f"20260824{application_id:04d}",
        application_type="return_refund",
        application_type_label="退货退款",
        product_name="无线耳机",
        product_attr="颜色：黑色",
        reason="商品存在质量问题",
        description="无法充电",
        status=status,
        status_label={
            "pending_review": "待审核",
            "accepted": "已受理",
            "completed": "已完成",
        }.get(status, "状态待确认"),
        created_at=1720000000000,
        fulfillment_status="not_started",
        fulfillment_status_label="待履约",
        fulfillment_note=None,
        can_cancel=can_cancel,
        can_modify=can_modify,
        can_supplement=can_supplement,
    )


class UnifiedAfterSalesGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_conversation_state_for_tests()

    def tearDown(self) -> None:
        set_conversation_manager_for_tests(None)

    def test_read_only_react_is_a_unified_after_sales_subflow(self) -> None:
        planned = [
            LLMResponse(
                tool_calls=[
                    {"name": "order_service", "arguments": {"order_sn": "synthetic-order"}}
                ]
            ),
            LLMResponse(
                tool_calls=[
                    {"name": "logistics_service", "arguments": {"order_sn": "synthetic-order"}}
                ]
            ),
            LLMResponse(content="synthetic complete"),
        ]
        calls = []

        def generate_fn(_messages, _tools):
            return planned.pop(0)

        def call_tool_fn(call, _context):
            calls.append(call.name)
            if call.name == "order_service":
                return {"status": "已发货", "product_names": ["合成商品"]}
            return {
                "order_status": "运输中",
                "company": "合成物流",
                "product_names": ["合成商品"],
            }

        result = run_unified_after_sales_investigation(
            session_id="unified-investigation",
            message="合成订单为什么还没到？",
            tool_context=ToolExecutionContext(authorization=AUTH_A, member_id=1),
            requires_order_facts=False,
            generate_fn=generate_fn,
            call_tool_fn=call_tool_fn,
        )

        self.assertEqual(["order_service", "logistics_service"], calls)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual("delivery_in_transit", result.diagnosis.category)
        self.assertTrue(result.verified_facts)
        self.assertFalse(result.durable_checkpoint_pending)
        self.assertNotIn("申请已提交", result.answer)

    def test_read_only_investigation_fails_closed_when_model_is_unavailable(self) -> None:
        calls = []

        def unavailable(_messages, _tools):
            raise RuntimeError("synthetic provider unavailable")

        result = run_unified_after_sales_investigation(
            session_id="unified-investigation-unavailable",
            message="合成订单异常",
            tool_context=ToolExecutionContext(authorization=AUTH_A, member_id=1),
            requires_order_facts=False,
            generate_fn=unavailable,
            call_tool_fn=lambda call, _context: calls.append(call) or {},
        )

        self.assertEqual([], calls)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual("tool_failure", result.diagnosis.category)
        self.assertIn("暂时", result.answer)

    @patch("app.services.unified_after_sales_graph.record_trace")
    @patch("app.services.unified_after_sales_graph.list_my_after_sales_applications")
    def test_multiple_applications_require_explicit_customer_selection(
        self, list_applications, _record_trace
    ) -> None:
        first_application = application(101)
        second_application = application(202)
        list_applications.return_value = [first_application, second_application]

        first = run_unified_after_sales_graph(
            session_id="member-a-session",
            message="帮我查看售后进度",
            authorization=AUTH_A,
            member_id=7,
            intent_name="status_after_sales",
        )

        self.assertIsNotNone(first.selection)
        self.assertEqual([101, 202], [x.application_id for x in first.selection.candidates])

        selected = run_unified_after_sales_graph(
            session_id="member-a-session",
            message="售后申请 #202",
            authorization=AUTH_A,
            member_id=7,
            intent_name="status_after_sales",
        )

        self.assertIsNone(selected.selection)
        self.assertEqual([202], [x.application_id for x in selected.applications])
        self.assertIn("售后单 #202", selected.answer)

    @patch("app.services.unified_after_sales_graph.record_trace")
    @patch("app.services.unified_after_sales_graph.list_my_after_sales_applications")
    def test_same_member_can_use_recent_verified_target_but_other_member_cannot(
        self, list_applications, _record_trace
    ) -> None:
        selected_application = application(301)
        alternative = application(302)
        list_applications.return_value = [selected_application, alternative]

        explicit = run_unified_after_sales_graph(
            session_id="shared-looking-session",
            message="查询售后申请 #301 的进度",
            authorization=AUTH_A,
            member_id=7,
            intent_name="status_after_sales",
        )
        self.assertEqual([301], [x.application_id for x in explicit.applications])
        self.assertEqual(
            301,
            get_conversation_state("shared-looking-session")
            .active_after_sales_application.application_id,
        )

        same_member = run_unified_after_sales_graph(
            session_id="shared-looking-session",
            message="上次那个售后还没处理吗？",
            authorization=AUTH_A,
            member_id=7,
            intent_name="follow_up_after_sales",
        )
        self.assertIsNone(same_member.selection)
        self.assertEqual([301], [x.application_id for x in same_member.applications])

        # The list returned for a different member is independently Java-scoped.
        # Its request must not reuse member A's Redis target even when an opaque
        # session string is accidentally reused.
        list_applications.return_value = [application(401), application(402)]
        other_member = run_unified_after_sales_graph(
            session_id="shared-looking-session",
            message="上次那个售后还没处理吗？",
            authorization=AUTH_B,
            member_id=8,
            intent_name="follow_up_after_sales",
        )
        self.assertIsNotNone(other_member.selection)
        self.assertEqual(
            [401, 402],
            [x.application_id for x in other_member.selection.candidates],
        )

    @patch("app.services.after_sales_application_service.record_trace")
    @patch("app.services.after_sales_application_service.execute_after_sales_action")
    def test_cancel_write_only_happens_after_server_pending_action_is_confirmed(
        self, execute_action, _record_trace
    ) -> None:
        pending = prepare_after_sales_action(
            session_id="confirmation-session",
            authorization=AUTH_A,
            member_id=7,
            application=application(501),
            action="cancel",
        )
        self.assertIsNotNone(pending.pending_action)
        self.assertEqual("cancel", pending.pending_action.action)

        waiting = handle_pending_after_sales_action_confirmation(
            "confirmation-session", "先等等", AUTH_A, 7
        )
        self.assertIsNotNone(waiting.pending_action)
        execute_action.assert_not_called()

        execute_action.return_value = application(
            501, status="completed", can_cancel=False, can_modify=False
        )
        completed = handle_pending_after_sales_action_confirmation(
            "confirmation-session", "确认", AUTH_A, 7
        )
        self.assertIsNotNone(completed.submitted_application)
        self.assertEqual("cancel", completed.completed_action)
        execute_action.assert_called_once()
        call = execute_action.call_args.kwargs
        self.assertEqual("cancel", call["action"])
        self.assertEqual(501, call["application_id"])
        self.assertNotIn("proposal_id", call)

    def test_accepted_application_normalizes_change_to_supplement_only(self) -> None:
        accepted = application(
            601,
            status="accepted",
            can_cancel=False,
            can_modify=False,
            can_supplement=True,
        )

        reason, description = _normalize_modification_for_application(
            accepted, "补充：仍然无法充电", None
        )

        self.assertIsNone(reason)
        self.assertEqual("补充：仍然无法充电", description)

    @patch("app.services.after_sales_application_service._safe_extract")
    def test_direct_modification_narrative_never_uses_keyword_fallback(
        self, safe_extract
    ) -> None:
        safe_extract.return_value = AfterSalesRequestExtraction()

        reason, description = _narrative_from_message("耳机坏了", None, None)

        self.assertIsNone(reason)
        self.assertIsNone(description)

    def test_public_completed_action_remains_customer_safe_and_hides_rag(self) -> None:
        internal = CustomerServiceResponse(
            message="取消售后申请 #701",
            answer="售后申请已取消。",
            intent=IntentResponse(
                intent="cancel_after_sales",
                route="after_sales_flow",
                need_tool=False,
            ),
            submitted_after_sales_application=application(
                701, status="completed", can_cancel=False, can_modify=False
            ),
            after_sales_completed_action="cancel",
            rag_sources=[
                RagSource(
                    chunk_id="internal-policy-chunk",
                    document_name="内部政策库",
                    section_path="内部 > 退货",
                    distance=0.1,
                )
            ],
        )

        public = to_public_customer_service_response(internal).model_dump()

        self.assertEqual("cancel", public["after_sales_completed_action"])
        self.assertEqual(701, public["submitted_after_sales_application"]["application_id"])
        self.assertNotIn("rag_sources", public)
        self.assertNotIn("intent", public)


if __name__ == "__main__":
    unittest.main()
