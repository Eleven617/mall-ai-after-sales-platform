import time
import unittest
from unittest.mock import patch

from app.schemas.after_sales_application import (
    AfterSalesApplicationView,
    AfterSalesEligibilityView,
    AfterSalesRequestExtraction,
    PendingAfterSalesProposal,
)
from app.schemas.rag import RagSource
from app.services.after_sales_application_service import (
    AfterSalesApplicationError,
    extract_after_sales_request,
    handle_pending_after_sales_confirmation,
    handle_pending_after_sales_draft,
    handle_pending_after_sales_modification_draft,
    prepare_after_sales_action,
    start_after_sales_modification_draft,
    start_after_sales_flow,
)
from app.services.conversation_state import (
    get_conversation_state,
    reset_conversation_state_for_tests,
    set_conversation_manager_for_tests,
)
from app.services.after_sales_application_state import (
    complete_pending_after_sales_proposal,
    owner_fingerprint,
    save_pending_after_sales_proposal,
    session_fingerprint,
)
from app.services.rag_service import RagAnswer


AUTHORIZATION = "Bearer user-token"
ORDER_ONE = {
    "order_sn": "202608210001",
    "status_code": 2,
    "status": "已发货",
    "order_items": [
        {
            "order_item_id": 501,
            "product_name": "无线耳机",
            "product_attr": "颜色：黑色",
            "product_quantity": 1,
        }
    ],
}
ORDER_TWO = {
    **ORDER_ONE,
    "order_items": [
        ORDER_ONE["order_items"][0],
        {
            "order_item_id": 502,
            "product_name": "手机壳",
            "product_attr": "颜色：蓝色",
            "product_quantity": 1,
        },
    ],
}
POLICY_ANSWER = RagAnswer(
    answer="商品质量问题可按售后政策申请处理。",
    retrieved_context=["商品质量问题可按售后政策申请处理。"],
    sources=[
        RagSource(
            chunk_id="policy-return-001",
            document_name="售后政策知识库",
            section_path="售后政策知识库 > 退货退款",
            distance=0.2,
        )
    ],
)
NO_EVIDENCE_ANSWER = RagAnswer(
    answer="知识库中没有足够依据确认该问题。",
    retrieved_context=[],
    sources=[],
    no_evidence=True,
)
ELIGIBLE_RETURN = AfterSalesEligibilityView(
    order_sn="202608210001",
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
BLOCKED_RETURN = ELIGIBLE_RETURN.model_copy(
    update={
        "eligible": False,
        "decision": "not_eligible",
        "message": "当前订单状态不支持提交售后申请。",
    }
)
SUBMITTED_APPLICATION = AfterSalesApplicationView(
    application_id=801,
    order_sn="202608210001",
    application_type="return_refund",
    application_type_label="退货退款",
    product_name="无线耳机",
    product_attr="颜色：黑色",
    reason="商品存在质量问题",
    description="耳机无法充电",
    status="pending_review",
    status_label="待审核",
    created_at=1720000000000,
    can_cancel=True,
    can_modify=True,
)


class AfterSalesApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_conversation_state_for_tests()

    def tearDown(self) -> None:
        set_conversation_manager_for_tests(None)

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_new_ready_draft_preserves_existing_gate_instead_of_overwriting_it(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
    ) -> None:
        session_id = "session-gate-and-new-draft"
        original_gate = _pending_proposal(session_id)
        save_pending_after_sales_proposal(session_id, original_gate)
        extract_after_sales_request.return_value = AfterSalesRequestExtraction(
            goal="apply",
            application_type="return_refund",
            product_hint="耳机",
            reason="商品存在质量问题",
            description="耳机无法充电",
        )
        get_order_snapshot.return_value = ORDER_ONE
        check_after_sales_eligibility.return_value = ELIGIBLE_RETURN
        answer_after_sales_question.return_value = POLICY_ANSWER

        result = start_after_sales_flow(
            session_id,
            "订单号：202608210001，另一笔订单的耳机无法充电，申请退货退款",
            AUTHORIZATION,
        )

        state = get_conversation_state(session_id)
        self.assertIn("待确认", result.answer)
        self.assertIsNotNone(result.draft)
        self.assertEqual(original_gate, state.pending_after_sales_proposal)
        self.assertIsNotNone(state.pending_after_sales_draft)
        self.assertIsNone(state.pending_after_sales_action)

    def test_new_action_never_replaces_an_existing_transaction_gate(self) -> None:
        session_id = "session-gate-and-new-action"
        original_gate = _pending_proposal(session_id)
        save_pending_after_sales_proposal(session_id, original_gate)

        result = prepare_after_sales_action(
            session_id=session_id,
            authorization=AUTHORIZATION,
            member_id=None,
            application=SUBMITTED_APPLICATION,
            action="cancel",
        )

        state = get_conversation_state(session_id)
        self.assertIn("待确认", result.answer)
        self.assertIsNone(result.pending_action)
        self.assertEqual(original_gate, state.pending_after_sales_proposal)
        self.assertIsNone(state.pending_after_sales_action)

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_ready_draft_can_resume_after_existing_gate_is_resolved(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
    ) -> None:
        session_id = "session-gate-resume"
        original_gate = _pending_proposal(session_id)
        save_pending_after_sales_proposal(session_id, original_gate)
        extract_after_sales_request.side_effect = [
            AfterSalesRequestExtraction(
                goal="apply",
                application_type="return_refund",
                product_hint="耳机",
                reason="商品存在质量问题",
                description="耳机无法充电",
            ),
            AfterSalesRequestExtraction(),
        ]
        get_order_snapshot.return_value = ORDER_ONE
        check_after_sales_eligibility.return_value = ELIGIBLE_RETURN
        answer_after_sales_question.return_value = POLICY_ANSWER

        waiting = start_after_sales_flow(
            session_id,
            "订单号：202608210001，另一笔订单的耳机无法充电，申请退货退款",
            AUTHORIZATION,
        )
        complete_pending_after_sales_proposal(session_id, AUTHORIZATION)
        resumed = handle_pending_after_sales_draft(
            session_id,
            "继续刚才的售后申请",
            AUTHORIZATION,
            resume_from_task=True,
        )

        state = get_conversation_state(session_id)
        self.assertIsNotNone(waiting.draft)
        self.assertIsNotNone(resumed)
        self.assertIsNotNone(resumed.proposal)
        self.assertNotEqual(original_gate.proposal_id, state.pending_after_sales_proposal.proposal_id)
        self.assertEqual("商品存在质量问题", state.pending_after_sales_proposal.reason)

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_builds_one_confirmation_gated_return_refund_proposal(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
    ) -> None:
        extract_after_sales_request.return_value = AfterSalesRequestExtraction(
            goal="apply",
            application_type="return_refund",
            product_hint="耳机",
            reason="商品存在质量问题",
            description="耳机无法充电",
        )
        get_order_snapshot.return_value = ORDER_ONE
        check_after_sales_eligibility.return_value = ELIGIBLE_RETURN
        answer_after_sales_question.return_value = POLICY_ANSWER

        result = start_after_sales_flow(
            "session-a",
            "订单号：202608210001 的耳机无法充电，申请退货退款",
            AUTHORIZATION,
        )

        self.assertIsNotNone(result.proposal)
        self.assertEqual("退货退款", result.proposal.application_type_label)
        self.assertEqual("无线耳机", result.proposal.product_name)
        self.assertNotIn("order_item_id", result.proposal.model_dump())
        self.assertIsNotNone(result.eligibility)
        self.assertIsNone(result.submitted_application)
        self.assertIsNotNone(
            get_conversation_state("session-a").pending_after_sales_proposal
        )
        check_after_sales_eligibility.assert_called_once_with(
            "202608210001",
            "return_refund",
            AUTHORIZATION,
            order_item_id=501,
        )

    @patch("app.services.after_sales_application_service.create_after_sales_application")
    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_confirmation_is_required_before_java_write(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
        create_after_sales_application,
    ) -> None:
        extract_after_sales_request.return_value = AfterSalesRequestExtraction(
            goal="apply",
            application_type="return_refund",
            product_hint="耳机",
            reason="商品存在质量问题",
            description="耳机无法充电",
        )
        get_order_snapshot.return_value = ORDER_ONE
        check_after_sales_eligibility.return_value = ELIGIBLE_RETURN
        answer_after_sales_question.return_value = POLICY_ANSWER
        create_after_sales_application.return_value = SUBMITTED_APPLICATION

        first = start_after_sales_flow(
            "session-confirm",
            "订单号：202608210001 的耳机无法充电，申请退货退款",
            AUTHORIZATION,
        )

        self.assertIsNotNone(first.proposal)
        create_after_sales_application.assert_not_called()
        second = handle_pending_after_sales_confirmation(
            "session-confirm", "确认", AUTHORIZATION
        )

        self.assertIsNotNone(second)
        self.assertEqual(801, second.submitted_application.application_id)
        self.assertIsNone(
            get_conversation_state("session-confirm").pending_after_sales_proposal
        )
        submitted_kwargs = create_after_sales_application.call_args.kwargs
        self.assertEqual("202608210001", submitted_kwargs["order_sn"])
        self.assertEqual("return_refund", submitted_kwargs["application_type"])
        self.assertEqual(501, submitted_kwargs["order_item_id"])
        self.assertEqual(AUTHORIZATION, submitted_kwargs["authorization"])
        self.assertEqual(32, len(submitted_kwargs["idempotency_key"]))

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_java_eligibility_block_stops_before_policy_or_proposal(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
    ) -> None:
        extract_after_sales_request.return_value = AfterSalesRequestExtraction(
            goal="apply",
            application_type="return_refund",
            product_hint="耳机",
            reason="商品存在质量问题",
        )
        get_order_snapshot.return_value = ORDER_ONE
        check_after_sales_eligibility.return_value = BLOCKED_RETURN

        result = start_after_sales_flow(
            "session-blocked",
            "订单号：202608210001 的耳机坏了，申请退货退款",
            AUTHORIZATION,
        )

        self.assertEqual("当前订单状态不支持提交售后申请。", result.answer)
        self.assertIsNone(result.proposal)
        self.assertIsNotNone(result.eligibility)
        self.assertIsNone(get_conversation_state("session-blocked").pending_after_sales_draft)
        answer_after_sales_question.assert_not_called()

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_collects_product_for_multi_item_order(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
    ) -> None:
        extract_after_sales_request.side_effect = [
            AfterSalesRequestExtraction(
                goal="apply",
                application_type="exchange",
                reason="商品错发或漏发",
            ),
            AfterSalesRequestExtraction(product_hint="手机壳"),
        ]
        get_order_snapshot.return_value = ORDER_TWO
        check_after_sales_eligibility.return_value = ELIGIBLE_RETURN.model_copy(
            update={
                "application_type": "exchange",
                "application_type_label": "换货",
                "product_name": "手机壳",
                "product_attr": "颜色：蓝色",
            }
        )
        answer_after_sales_question.return_value = POLICY_ANSWER

        first = start_after_sales_flow(
            "session-product",
            "订单号：202608210001，我要申请换货，商品发错了",
            AUTHORIZATION,
        )
        self.assertIsNotNone(first.draft)
        self.assertEqual(["product"], first.draft.missing_fields)
        self.assertEqual(2, len(first.draft.product_options))

        second = handle_pending_after_sales_draft(
            "session-product", "我选择手机壳", AUTHORIZATION
        )
        self.assertIsNotNone(second)
        self.assertIsNotNone(second.proposal)
        self.assertEqual("换货", second.proposal.application_type_label)
        self.assertEqual("手机壳", second.proposal.product_name)
        self.assertEqual(
            502,
            get_conversation_state("session-product")
            .pending_after_sales_proposal.order_item_id,
        )

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.check_after_sales_eligibility")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_no_policy_evidence_never_creates_proposal(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        check_after_sales_eligibility,
        answer_after_sales_question,
    ) -> None:
        extract_after_sales_request.return_value = AfterSalesRequestExtraction(
            goal="apply",
            application_type="repair",
            product_hint="耳机",
            reason="商品存在质量问题",
        )
        get_order_snapshot.return_value = ORDER_ONE
        check_after_sales_eligibility.return_value = ELIGIBLE_RETURN.model_copy(
            update={"application_type": "repair", "application_type_label": "维修/质保"}
        )
        answer_after_sales_question.return_value = NO_EVIDENCE_ANSWER

        result = start_after_sales_flow(
            "session-no-evidence",
            "订单号：202608210001 的耳机坏了，申请维修",
            AUTHORIZATION,
        )

        self.assertIsNone(result.proposal)
        self.assertIn("没有足够政策依据", result.answer)
        self.assertIsNone(
            get_conversation_state("session-no-evidence").pending_after_sales_draft
        )

    def test_unrelated_message_does_not_consume_a_pending_draft(self) -> None:
        from app.schemas.after_sales_application import PendingAfterSalesDraft
        from app.services.after_sales_application_state import owner_fingerprint, save_pending_after_sales_draft

        save_pending_after_sales_draft(
            "session-paused",
            PendingAfterSalesDraft(
                draft_id="draft-paused",
                owner_fingerprint=owner_fingerprint(AUTHORIZATION),
                goal="apply",
                application_type="repair",
                expires_at=time.time() + 300,
            ),
        )

        result = handle_pending_after_sales_draft(
            "session-paused", "优惠券怎么使用？", AUTHORIZATION
        )

        self.assertIsNone(result)
        self.assertIsNotNone(
            get_conversation_state("session-paused").pending_after_sales_draft
        )

    @patch("app.services.after_sales_application_service.answer_after_sales_question")
    @patch("app.services.after_sales_application_service.get_order_snapshot")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_new_draft_never_guesses_goal_type_or_reason_from_keywords(
        self,
        extract_after_sales_request,
        get_order_snapshot,
        answer_after_sales_question,
    ) -> None:
        extract_after_sales_request.return_value = AfterSalesRequestExtraction()

        result = start_after_sales_flow(
            "session-no-keyword-fallback",
            "订单号：202608210001，耳机坏了，申请退货退款",
            AUTHORIZATION,
        )

        self.assertIsNotNone(result.draft)
        self.assertIsNone(result.draft.goal)
        self.assertIsNone(result.draft.application_type)
        self.assertIn("先核验售后资格", result.answer)
        get_order_snapshot.assert_not_called()
        answer_after_sales_question.assert_not_called()
        pending = get_conversation_state("session-no-keyword-fallback").pending_after_sales_draft
        self.assertIsNotNone(pending)
        self.assertIsNone(pending.reason)

    @patch("app.services.after_sales_application_service.prepare_after_sales_action")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_pending_modification_without_grounded_fields_keeps_draft_and_never_prepares_action(
        self,
        extract_after_sales_request,
        prepare_after_sales_action,
    ) -> None:
        start_after_sales_modification_draft(
            session_id="session-modification-grounding",
            authorization=AUTHORIZATION,
            member_id=7,
            application=SUBMITTED_APPLICATION,
        )
        extract_after_sales_request.return_value = AfterSalesRequestExtraction()

        result = handle_pending_after_sales_modification_draft(
            "session-modification-grounding",
            "耳机坏了",
            AUTHORIZATION,
            7,
        )

        self.assertIsNotNone(result)
        self.assertIn("原话中核验到依据", result.answer)
        self.assertIsNotNone(
            get_conversation_state("session-modification-grounding")
            .pending_after_sales_modification_draft
        )
        prepare_after_sales_action.assert_not_called()

    @patch("app.services.after_sales_application_service.prepare_after_sales_action")
    @patch("app.services.after_sales_application_service.extract_after_sales_request")
    def test_pending_modification_model_failure_keeps_draft_and_never_prepares_action(
        self,
        extract_after_sales_request,
        prepare_after_sales_action,
    ) -> None:
        start_after_sales_modification_draft(
            session_id="session-modification-unavailable",
            authorization=AUTHORIZATION,
            member_id=7,
            application=SUBMITTED_APPLICATION,
        )
        extract_after_sales_request.side_effect = AfterSalesApplicationError("unavailable")

        result = handle_pending_after_sales_modification_draft(
            "session-modification-unavailable",
            "请更新原因",
            AUTHORIZATION,
            7,
        )

        self.assertIsNotNone(result)
        self.assertIn("原修改草稿已保留", result.answer)
        self.assertIsNotNone(
            get_conversation_state("session-modification-unavailable")
            .pending_after_sales_modification_draft
        )
        prepare_after_sales_action.assert_not_called()

    @patch("app.services.after_sales_application_service.generate_json")
    def test_extractor_discards_non_contiguous_evidence_span(self, generate_json) -> None:
        generate_json.return_value = {
            "goal": {"value": "apply", "evidence_span": "申请退货"},
            "application_type": {"value": "return_refund", "evidence_span": "退货"},
            "reason": {"value": "商品存在质量问题", "evidence_span": "质量问题"},
            "description": {"value": "耳机坏了", "evidence_span": "耳机坏了"},
        }

        extraction = extract_after_sales_request("我想申请退货，耳机坏了")

        self.assertEqual("apply", extraction.goal)
        self.assertEqual("return_refund", extraction.application_type)
        self.assertIsNone(extraction.reason)
        self.assertEqual("耳机坏了", extraction.description)

    @patch("app.services.after_sales_application_service.generate_json")
    def test_extractor_corrects_missing_evidence_span_once(self, generate_json) -> None:
        generate_json.side_effect = [
            {
                "goal": {"value": "apply", "evidence_span": "申请退货"},
                "application_type": {"value": "return_refund", "evidence_span": "退货"},
                "reason": {"value": "质量问题", "evidence_span": None},
            },
            {
                "goal": {"value": "apply", "evidence_span": "申请退货"},
                "application_type": {"value": "return_refund", "evidence_span": "退货"},
                "reason": {"value": "耳机坏了", "evidence_span": "耳机坏了"},
            },
        ]

        extraction = extract_after_sales_request("我想申请退货，耳机坏了")

        self.assertEqual("apply", extraction.goal)
        self.assertEqual("return_refund", extraction.application_type)
        self.assertEqual("耳机坏了", extraction.reason)
        self.assertEqual(2, generate_json.call_count)
        self.assertIn(
            '"validationErrors":["evidence_span_missing"]',
            generate_json.call_args_list[1].kwargs["message"],
        )


def _pending_proposal(session_id: str) -> PendingAfterSalesProposal:
    return PendingAfterSalesProposal(
        proposal_id="p" * 32,
        application_type="return_refund",
        order_sn="202608210001",
        order_item_id=501,
        product_name="无线耳机",
        product_attr="颜色：黑色",
        reason="商品存在质量问题",
        description="耳机无法充电",
        owner_fingerprint=owner_fingerprint(AUTHORIZATION),
        session_fingerprint=session_fingerprint(session_id),
        content_hash="h" * 64,
        expires_at=time.time() + 600,
    )


if __name__ == "__main__":
    unittest.main()
