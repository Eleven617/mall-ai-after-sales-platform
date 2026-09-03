import time
import unittest

from app.schemas.after_sales_application import PendingAfterSalesProposal
from app.schemas.intent import IntentToolCall
from app.schemas.task_orchestration import TaskSnapshot, TurnPlan
from app.schemas.tool import ToolCall
from app.services.conversation_state import (
    ConversationManager,
    get_conversation_state,
    reset_conversation_state_for_tests,
    save_conversation_state,
    set_conversation_manager_for_tests,
)
from app.services.conversation_store import InMemoryConversationStore
from app.services.after_sales_application_state import (
    owner_fingerprint,
    save_pending_after_sales_proposal,
    session_fingerprint,
)
from app.services.task_orchestration_service import TaskOrchestrationService


class TaskOrchestrationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_conversation_state_for_tests()
        self.runtime = TaskOrchestrationService()
        self.session_id = "task-orchestration-session"
        self.member_id = 7

    def tearDown(self) -> None:
        set_conversation_manager_for_tests(None)

    def test_temporary_detour_pauses_the_waiting_task_without_parsing_new_message(self) -> None:
        self._start_waiting_diagnosis()

        decision = self._prepare(
            _plan("after_sales_policy", "rag", "temporary_detour")
        )

        state = get_conversation_state(self.session_id)
        self.assertEqual("dispatch", decision.mode)
        self.assertIsNone(state.active_task)
        self.assertEqual("order_diagnosis", state.paused_task.kind)
        self.assertEqual("paused", state.paused_task.status)
        self.assertIsNone(state.pending_tool_call)

    def test_two_occupied_slots_reject_a_misclassified_standalone_logistics_request(self) -> None:
        self._start_waiting_diagnosis()
        self._prepare(_plan("after_sales_policy", "rag", "temporary_detour"))
        self._prepare(
            _plan(
                "apply_after_sales",
                "after_sales_flow",
                "start_new_task",
                task_kind="after_sales_draft",
            )
        )

        decision = self._prepare(
            _plan("query_logistics", "ask_missing_info", "standalone_answer")
        )

        state = get_conversation_state(self.session_id)
        self.assertEqual("clarify", decision.mode)
        self.assertEqual("after_sales_draft", state.active_task.kind)
        self.assertEqual("order_diagnosis", state.paused_task.kind)

    def test_resume_paused_restores_only_the_matching_task(self) -> None:
        self._start_waiting_diagnosis()
        self._prepare(_plan("after_sales_policy", "rag", "temporary_detour"))

        decision = self._prepare(
            _plan(
                "query_logistics",
                "agent",
                "resume_paused",
                task_kind="order_diagnosis",
            )
        )

        state = get_conversation_state(self.session_id)
        self.assertEqual("continue_task", decision.mode)
        self.assertEqual("order_diagnosis", decision.active_kind)
        self.assertEqual("order_diagnosis", state.active_task.kind)
        self.assertIsNone(state.paused_task)

    def test_standalone_chat_does_not_discard_an_active_task(self) -> None:
        self._start_waiting_diagnosis()
        before = get_conversation_state(self.session_id).active_task.task_id

        decision = self._prepare(_plan("general_chat", "chat", "standalone_answer", chat_scope="capability"))

        state = get_conversation_state(self.session_id)
        self.assertEqual("dispatch", decision.mode)
        self.assertEqual(before, state.active_task.task_id)
        self.assertIsNone(state.paused_task)

    def test_transaction_gate_does_not_block_a_new_after_sales_task(self) -> None:
        proposal = PendingAfterSalesProposal(
            proposal_id="p" * 32,
            application_type="return_refund",
            order_sn="202609020001",
            order_item_id=501,
            product_name="合成商品",
            reason="合成原因",
            description="合成说明",
            owner_fingerprint=owner_fingerprint(None, self.member_id),
            session_fingerprint=session_fingerprint(self.session_id),
            content_hash="h" * 64,
            expires_at=time.time() + 600,
        )
        save_pending_after_sales_proposal(self.session_id, proposal)

        decision = self._prepare(
            _plan(
                "apply_after_sales",
                "after_sales_flow",
                "start_new_task",
                task_kind="after_sales_draft",
            )
        )

        state = get_conversation_state(self.session_id)
        self.assertEqual("dispatch", decision.mode)
        self.assertEqual("after_sales_draft", state.active_task.kind)
        self.assertEqual(proposal, state.pending_after_sales_proposal)
        self.assertIsNotNone(state.transaction_gate)

    def test_third_long_running_task_requires_clarification_instead_of_overwriting(self) -> None:
        self._start_waiting_diagnosis()
        self._prepare(_plan("after_sales_policy", "rag", "temporary_detour"))
        self._prepare(
            _plan(
                "apply_after_sales",
                "after_sales_flow",
                "start_new_task",
                task_kind="after_sales_draft",
            )
        )
        before = get_conversation_state(self.session_id)
        active_id = before.active_task.task_id
        paused_id = before.paused_task.task_id

        decision = self._prepare(
            _plan(
                "modify_after_sales",
                "after_sales_flow",
                "start_new_task",
                task_kind="after_sales_modification",
            )
        )

        after = get_conversation_state(self.session_id)
        self.assertEqual("clarify", decision.mode)
        self.assertIn("两项未完成事项", decision.clarification)
        self.assertEqual(active_id, after.active_task.task_id)
        self.assertEqual(paused_id, after.paused_task.task_id)

    def test_ambiguous_a_or_b_recovery_requests_clarification_without_state_change(self) -> None:
        self._start_waiting_diagnosis()
        self._prepare(_plan("after_sales_policy", "rag", "temporary_detour"))
        self._prepare(
            _plan(
                "apply_after_sales",
                "after_sales_flow",
                "start_new_task",
                task_kind="after_sales_draft",
            )
        )
        before = get_conversation_state(self.session_id)

        decision = self._prepare(_plan("unknown", "chat", "resolve_task_conflict"))

        after = get_conversation_state(self.session_id)
        self.assertEqual("clarify", decision.mode)
        self.assertEqual(before.active_task.task_id, after.active_task.task_id)
        self.assertEqual(before.paused_task.task_id, after.paused_task.task_id)

    def test_paused_task_survives_a_new_conversation_manager_instance(self) -> None:
        store = InMemoryConversationStore()
        manager = ConversationManager(store, ttl_seconds=600)
        set_conversation_manager_for_tests(manager)
        self._start_waiting_diagnosis()
        self._prepare(_plan("after_sales_policy", "rag", "temporary_detour"))

        set_conversation_manager_for_tests(ConversationManager(store, ttl_seconds=600))
        recovered = get_conversation_state(self.session_id)

        self.assertIsNone(recovered.active_task)
        self.assertEqual("order_diagnosis", recovered.paused_task.kind)
        self.assertEqual("paused", recovered.paused_task.status)

    def test_different_member_cannot_reuse_or_view_a_task(self) -> None:
        self._start_waiting_diagnosis()

        decision = self.runtime.prepare_turn(
            session_id=self.session_id,
            authorization=None,
            member_id=8,
            plan=_plan("general_chat", "chat", "standalone_answer", chat_scope="greeting"),
        )

        state = get_conversation_state(self.session_id)
        self.assertEqual("dispatch", decision.mode)
        self.assertIsNone(state.active_task)
        self.assertIsNone(state.paused_task)

    def test_expired_task_is_not_resumed(self) -> None:
        self._start_waiting_diagnosis()
        state = get_conversation_state(self.session_id)
        state.active_task.expires_at = time.time() - 1
        save_conversation_state(state)

        decision = self._prepare(
            _plan(
                "query_logistics",
                "agent",
                "resume_paused",
                task_kind="order_diagnosis",
            )
        )

        self.assertEqual("clarify", decision.mode)
        self.assertIsNone(get_conversation_state(self.session_id).active_task)

    def test_snapshot_contract_rejects_identifier_and_credential_payloads(self) -> None:
        base = {
            "task_id": "a" * 32,
            "owner_fingerprint": "b" * 64,
            "session_fingerprint": "c" * 64,
            "kind": "order_diagnosis",
            "status": "waiting_input",
            "goal_summary": "订单与物流异常诊断",
            "expires_at": time.time() + 600,
        }
        with self.assertRaises(ValueError):
            TaskSnapshot(**base, known_slots={"order_sn": "202607240001"})
        with self.assertRaises(ValueError):
            TaskSnapshot(**base, next_agent_hint="Bearer not-allowed")
        with self.assertRaises(ValueError):
            TaskSnapshot(**base, unexpected="must-not-be-persisted")

    def _start_waiting_diagnosis(self) -> None:
        decision = self._prepare(
            _plan(
                "query_logistics",
                "agent",
                "start_new_task",
                task_kind="order_diagnosis",
            )
        )
        self.assertEqual("dispatch", decision.mode)
        self.runtime.record_waiting_diagnosis(
            session_id=self.session_id,
            authorization=None,
            member_id=self.member_id,
            pending_tool_call=ToolCall(name="logistics_service", arguments={}),
            answer="synthetic answer is deliberately not stored in the task snapshot",
        )

    def _prepare(self, plan: TurnPlan):
        return self.runtime.prepare_turn(
            session_id=self.session_id,
            authorization=None,
            member_id=self.member_id,
            plan=plan,
        )


def _plan(
    intent: str,
    route: str,
    relation: str,
    *,
    task_kind: str | None = None,
    chat_scope: str | None = None,
) -> TurnPlan:
    if route == "agent":
        need_tool = True
        tool_call = IntentToolCall(name="analysis_agent", arguments={})
    elif route == "ask_missing_info":
        need_tool = False
        tool_call = IntentToolCall(name="logistics_service", arguments={})
    else:
        need_tool = False
        tool_call = None
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
        confirmation_intent="none",
        rationale_code=rationale,
        need_tool=need_tool,
        tool_call=tool_call,
        reply=None,
        chat_scope=chat_scope,
    )


if __name__ == "__main__":
    unittest.main()
