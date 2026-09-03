"""Task-aware runtime for the customer-service entrypoint.

This service owns *conversation task* transitions only.  It deliberately does
not decide business facts, call Java write APIs, or interpret raw customer text.
Those remain respectively with Java, the unified after-sales workflow, and the
bounded P0 ``TurnPlan`` model.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from uuid import uuid4

from app.schemas.after_sales_application import AfterSalesFlowResult
from app.schemas.conversation import TaskRuntimePayload
from app.schemas.intent import IntentResponse
from app.schemas.task_orchestration import (
    TaskKind,
    TaskPublicState,
    TaskSnapshot,
    TransactionGate,
    TurnPlan,
)
from app.schemas.tool import ToolCall
from app.services.after_sales_application_service import (
    handle_pending_after_sales_action_confirmation,
    handle_pending_after_sales_confirmation,
    handle_pending_after_sales_draft,
    handle_pending_after_sales_modification_draft,
)
from app.services.after_sales_application_state import (
    AfterSalesPendingStateError,
    owner_fingerprint,
    session_fingerprint,
)
from app.services.conversation_state import (
    get_conversation_state,
    save_conversation_state,
)


TASK_TTL_SECONDS = 15 * 60


class TaskOrchestrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskTurnDecision:
    mode: str
    active_kind: TaskKind | None = None
    clarification: str | None = None


class TaskOrchestrationService:
    """Persist at most one active and one paused task for a session."""

    def prepare_turn(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
        plan: TurnPlan,
    ) -> TaskTurnDecision:
        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        self._synchronize_transaction_gate(state)

        # A transaction gate has a separate lifecycle.  It is never allowed to
        # turn an unrelated policy/chat message into a pending-write handler.
        if plan.confirmation_intent in {"confirm", "cancel"}:
            if state.transaction_gate is None:
                save_conversation_state(state)
                return TaskTurnDecision(
                    mode="gate_missing",
                    clarification="当前没有可确认的售后方案或操作，请先查看或重新发起售后请求。",
                )
            save_conversation_state(state)
            return TaskTurnDecision(mode="transaction_gate")
        if plan.confirmation_intent == "modify" and state.transaction_gate is not None:
            # This is an explicit request to alter the currently displayed
            # confirmation candidate, not a fresh task. A gate is immutable
            # once shown: changing it silently would invalidate its content
            # hash and the customer's prior review. The customer may still
            # start an independently classified task on any later turn.
            save_conversation_state(state)
            return TaskTurnDecision(
                mode="gate_modify",
                clarification=(
                    "当前待确认方案不能直接改写。请先取消当前确认卡，"
                    "再重新说明需要办理或调整的内容。"
                ),
            )
        # A transaction gate is deliberately *not* a conversation task.  P0
        # has already interpreted this message, so an unrelated new inquiry or
        # a new after-sales task must continue through the ordinary task
        # transition rules below.  The state layer preserves the existing
        # owner-bound gate and rejects only an attempt to replace it with a
        # second confirmation candidate.  This keeps one exact future Java
        # write replay-safe without letting a confirmation card claim every
        # subsequent customer message.

        relation = plan.task_relation
        if relation == "resolve_task_conflict":
            save_conversation_state(state)
            return TaskTurnDecision(
                mode="clarify",
                clarification=(
                    "当前会话还保留两项未完成事项。请说明要继续哪一项，"
                    "或先说“放弃刚才的事项”后再开始新的查询。"
                ),
            )

        # P0 normally emits ``resolve_task_conflict`` for this state.  Keep a
        # deterministic guard as well: a malformed or semantically weak model
        # result must never turn a third multi-turn goal into an overwrite of
        # the two server-owned task slots. This reads only the closed TurnPlan
        # contract and state occupancy, never raw customer wording.
        if (
            state.active_task is not None
            and state.paused_task is not None
            and _would_require_a_third_task(plan)
        ):
            save_conversation_state(state)
            return TaskTurnDecision(
                mode="clarify",
                clarification=(
                    "当前会话还保留两项未完成事项。请先说明保留哪一项，"
                    "我再为你开始新的处理。"
                ),
            )

        if relation == "discard_active":
            self._discard_task(state, "active")
            save_conversation_state(state)
            return TaskTurnDecision(mode="discarded")
        if relation == "discard_paused":
            self._discard_task(state, "paused")
            save_conversation_state(state)
            return TaskTurnDecision(mode="discarded")

        if relation == "temporary_detour":
            if state.active_task is not None and state.paused_task is None:
                state.active_task.status = "paused"
                state.active_task.updated_at = time.time()
                state.paused_task = state.active_task
                state.active_task = None
            # When both slots are already occupied, a one-turn detour is still
            # safe: it does not need a third persistent slot, so preserve both.
            save_conversation_state(state)
            return TaskTurnDecision(mode="dispatch")

        if relation == "resume_paused":
            if state.paused_task is None:
                save_conversation_state(state)
                return TaskTurnDecision(
                    mode="clarify",
                    clarification="没有找到可恢复的已暂存事项，请重新说明你希望查询或办理的内容。",
                )
            if plan.task_kind is not None and plan.task_kind != state.paused_task.kind:
                save_conversation_state(state)
                return TaskTurnDecision(
                    mode="clarify",
                    clarification="暂存事项与当前描述不一致，请说明要继续哪一项，或重新描述新的需求。",
                )
            if state.active_task is not None:
                state.active_task.status = "paused"
                state.paused_task.status = "active"
                state.active_task, state.paused_task = state.paused_task, state.active_task
            else:
                state.active_task = state.paused_task
                state.active_task.status = "active"
                state.paused_task = None
            state.active_task.updated_at = time.time()
            save_conversation_state(state)
            return TaskTurnDecision(mode="continue_task", active_kind=state.active_task.kind)

        if relation == "start_new_task" and plan.task_kind is not None:
            if state.active_task is not None and state.paused_task is not None:
                save_conversation_state(state)
                return TaskTurnDecision(
                    mode="clarify",
                    clarification=(
                        "当前会话还保留两项未完成事项。请先说明保留哪一项，"
                        "我再为你开始新的处理。"
                    ),
                )
            if state.active_task is not None:
                state.active_task.status = "paused"
                state.active_task.updated_at = time.time()
                state.paused_task = state.active_task
            state.active_task = self._new_task(
                session_id=session_id,
                authorization=authorization,
                member_id=member_id,
                kind=plan.task_kind,
                goal_summary=_goal_summary(plan),
            )
            save_conversation_state(state)
            return TaskTurnDecision(mode="dispatch", active_kind=plan.task_kind)

        if relation == "continue_active":
            if state.active_task is None:
                if plan.task_kind is None:
                    save_conversation_state(state)
                    return TaskTurnDecision(mode="dispatch")
                state.active_task = self._new_task(
                    session_id=session_id,
                    authorization=authorization,
                    member_id=member_id,
                    kind=plan.task_kind,
                    goal_summary=_goal_summary(plan),
                )
                save_conversation_state(state)
                return TaskTurnDecision(mode="dispatch", active_kind=plan.task_kind)
            if plan.task_kind is not None and plan.task_kind != state.active_task.kind:
                save_conversation_state(state)
                return TaskTurnDecision(
                    mode="clarify",
                    clarification="当前事项与这条消息的目标不一致，请说明是继续当前事项还是开始新的处理。",
                )
            state.active_task.status = "active"
            state.active_task.updated_at = time.time()
            save_conversation_state(state)
            return TaskTurnDecision(mode="continue_task", active_kind=state.active_task.kind)

        save_conversation_state(state)
        return TaskTurnDecision(mode="dispatch", active_kind=state.active_task.kind if state.active_task else None)

    def activate_active_payload(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
    ) -> TaskKind | None:
        """Expose one active task payload to the old bounded workflow adapter.

        The payload is copied back out immediately after the adapter returns;
        this is an implementation bridge, not a second routing mechanism.
        """

        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        task = state.active_task
        if task is None:
            return None
        payload = state.task_payloads.get(task.task_id)
        if payload is None:
            return task.kind
        state.pending_tool_call = payload.pending_tool_call
        state.pending_after_sales_draft = payload.pending_after_sales_draft
        state.pending_after_sales_selection = payload.pending_after_sales_selection
        state.pending_after_sales_modification_draft = payload.pending_after_sales_modification_draft
        save_conversation_state(state)
        return task.kind

    def capture_active_payload(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
        pending_question: str | None = None,
    ) -> None:
        """Move non-transaction pending state back behind the active task slot."""

        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        task = state.active_task
        if task is None:
            return
        payload = TaskRuntimePayload(
            task_id=task.task_id,
            pending_tool_call=state.pending_tool_call,
            pending_after_sales_draft=state.pending_after_sales_draft,
            pending_after_sales_selection=state.pending_after_sales_selection,
            pending_after_sales_modification_draft=state.pending_after_sales_modification_draft,
            expires_at=task.expires_at,
        )
        if _payload_has_work(payload):
            state.task_payloads[task.task_id] = payload
            task.status = "waiting_input"
            # Do not persist an Agent response, RAG text, or user wording in a
            # task snapshot.  A fixed, task-kind hint is enough for a later P0
            # turn to decide whether the new message resumes it.
            task.pending_question = _task_waiting_hint(task.kind)
            task.updated_at = time.time()
        else:
            state.task_payloads.pop(task.task_id, None)
            # A proposal/action has become a transaction gate, or a task
            # finished.  Neither should keep a phantom active task alive.
            state.active_task = None
        state.pending_tool_call = None
        state.pending_after_sales_draft = None
        state.pending_after_sales_selection = None
        state.pending_after_sales_modification_draft = None
        self._synchronize_transaction_gate(state)
        save_conversation_state(state)

    def capture_after_sales_work(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
        pending_question: str | None = None,
    ) -> None:
        """Capture a newly-created draft/selection/modification task if needed."""

        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        has_payload = any(
            (
                state.pending_after_sales_draft,
                state.pending_after_sales_selection,
                state.pending_after_sales_modification_draft,
            )
        )
        if has_payload and state.active_task is None:
            kind: TaskKind = (
                "after_sales_modification"
                if state.pending_after_sales_modification_draft is not None
                else "after_sales_draft"
            )
            state.active_task = self._new_task(
                session_id=session_id,
                authorization=authorization,
                member_id=member_id,
                kind=kind,
                goal_summary=(
                    "补充或修改售后申请说明"
                    if kind == "after_sales_modification"
                    else "收集售后申请信息并核验资格"
                ),
            )
            save_conversation_state(state)
        self.capture_active_payload(
            session_id=session_id,
            authorization=authorization,
            member_id=member_id,
            pending_question=pending_question,
        )

    def complete_active_task(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
    ) -> None:
        """Clear only a finished non-transaction task after a verified read."""

        state = get_conversation_state(session_id)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        self._discard_task(state, "active")
        save_conversation_state(state)

    def record_waiting_diagnosis(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
        pending_tool_call: ToolCall,
        answer: str,
    ) -> None:
        """Store a normal waiting-input task, never a default LangGraph interrupt."""

        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        task = state.active_task
        if task is None or task.kind != "order_diagnosis":
            if task is not None and state.paused_task is None:
                task.status = "paused"
                state.paused_task = task
            task = self._new_task(
                session_id=session_id,
                authorization=authorization,
                member_id=member_id,
                kind="order_diagnosis",
                goal_summary="订单与物流异常诊断",
            )
            state.active_task = task
        required = "订单号" if pending_tool_call.name in {"order_service", "logistics_service"} else "SKU 编码"
        task.status = "waiting_input"
        task.known_slots = {"awaiting_input": required, "tool_kind": pending_tool_call.name}
        task.pending_question = _task_waiting_hint(task.kind)
        task.next_agent_hint = "收到相关标识后继续只读核验。"
        task.updated_at = time.time()
        # The full tool arguments are intentionally not persisted for this
        # task.  P0 must judge the next message first; the Agent then proposes
        # the next allow-listed read again.
        state.pending_tool_call = None
        state.task_payloads.pop(task.task_id, None)
        save_conversation_state(state)

    def current_public_state(self, session_id: str) -> TaskPublicState:
        state = get_conversation_state(session_id)
        self._drop_expired(state)
        task = state.paused_task or state.active_task
        if task is None:
            return TaskPublicState()
        return TaskPublicState(
            task_status="paused" if task is state.paused_task else "active",
            task_label=_task_label(task.kind),
            task_hint=_task_hint(task),
        )

    def execute_transaction_gate(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
        plan: TurnPlan,
    ) -> AfterSalesFlowResult:
        """Map a semantic confirmation decision to a server-owned gate only."""

        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._synchronize_transaction_gate(state)
        gate = state.transaction_gate
        if gate is None:
            return AfterSalesFlowResult(answer="当前没有可确认的售后方案或操作，请重新发起请求。")
        message = "确认" if plan.confirmation_intent == "confirm" else "取消"
        if gate.kind == "proposal":
            result = handle_pending_after_sales_confirmation(
                session_id, message, authorization, member_id
            )
        else:
            result = handle_pending_after_sales_action_confirmation(
                session_id, message, authorization, member_id
            )
        # The confirmation handlers load and save their own session state.
        # Refresh before projecting the gate again so we never overwrite a
        # completed/cancelled proposal with this stale pre-handler object.
        state = get_conversation_state(session_id)
        self._drop_expired(state)
        self._synchronize_transaction_gate(state)
        save_conversation_state(state)
        return result or AfterSalesFlowResult(answer="当前确认操作未完成，请稍后重试。")

    def discard_active_task(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
    ) -> None:
        state = get_conversation_state(session_id)
        self._assert_owned_tasks(state, session_id, authorization, member_id)
        self._discard_task(state, "active")
        save_conversation_state(state)

    def _new_task(
        self,
        *,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
        kind: TaskKind,
        goal_summary: str,
    ) -> TaskSnapshot:
        now = time.time()
        owner = _task_owner_fingerprint(session_id, authorization, member_id)
        return TaskSnapshot(
            task_id=uuid4().hex,
            owner_fingerprint=owner,
            session_fingerprint=session_fingerprint(session_id),
            kind=kind,
            status="active",
            goal_summary=goal_summary,
            expires_at=now + TASK_TTL_SECONDS,
        )

    def _assert_owned_tasks(
        self,
        state,
        session_id: str,
        authorization: str | None,
        member_id: int | None,
    ) -> None:
        expected_owner = _task_owner_fingerprint(session_id, authorization, member_id)
        expected_session = session_fingerprint(session_id)
        for slot in ("active_task", "paused_task"):
            task = getattr(state, slot)
            if task is None:
                continue
            if task.owner_fingerprint != expected_owner or task.session_fingerprint != expected_session:
                # Never describe another identity's pending work.  Remove only
                # the isolated task cache; Java still authorizes all reads/writes.
                state.task_payloads.pop(task.task_id, None)
                setattr(state, slot, None)

    def _drop_expired(self, state) -> None:
        now = time.time()
        for slot in ("active_task", "paused_task"):
            task = getattr(state, slot)
            if task is not None and task.expires_at <= now:
                state.task_payloads.pop(task.task_id, None)
                setattr(state, slot, None)
        if state.transaction_gate is not None and state.transaction_gate.expires_at <= now:
            state.transaction_gate = None

    def _discard_task(self, state, slot: str) -> None:
        task = getattr(state, f"{slot}_task")
        if task is None:
            return
        state.task_payloads.pop(task.task_id, None)
        setattr(state, f"{slot}_task", None)
        if slot == "active":
            # These fields are only an in-process adapter while the selected
            # active task is handed to an older bounded workflow.  They must
            # not become a second resumable route after the task is discarded.
            state.pending_tool_call = None
            state.pending_after_sales_draft = None
            state.pending_after_sales_selection = None
            state.pending_after_sales_modification_draft = None

    def _synchronize_transaction_gate(self, state) -> None:
        proposal = state.pending_after_sales_proposal
        action = state.pending_after_sales_action
        now = time.time()
        if proposal is not None and proposal.expires_at <= now:
            state.pending_after_sales_proposal = None
            state.facts.pop("after_sales_flow_status", None)
            proposal = None
        if action is not None and action.expires_at <= now:
            state.pending_after_sales_action = None
            state.facts.pop("after_sales_flow_status", None)
            action = None
        if proposal is not None:
            state.transaction_gate = TransactionGate(
                kind="proposal",
                status=(
                    "result_unknown"
                    if proposal.submission_state == "submission_unknown"
                    else "awaiting_confirmation"
                ),
                label="待确认售后申请方案",
                expires_at=proposal.expires_at,
            )
            return
        if action is not None:
            state.transaction_gate = TransactionGate(
                kind="after_sales_action",
                status=(
                    "result_unknown"
                    if action.execution_state == "execution_unknown"
                    else "awaiting_confirmation"
                ),
                label="待确认售后操作",
                expires_at=action.expires_at,
            )
            return
        state.transaction_gate = None


def get_task_orchestration_service() -> TaskOrchestrationService:
    return _service


def normalize_turn_plan(value: TurnPlan | IntentResponse) -> TurnPlan:
    """Keep test seams and internal callers explicit during the P0 cutover.

    Production ``detect_intent`` always returns ``TurnPlan``.  This adapter
    exists only for deterministic unit-test mocks that still construct the
    previous validated ``IntentResponse`` contract; it never reads customer
    text or recreates a keyword router.
    """

    if isinstance(value, TurnPlan):
        return value
    if not isinstance(value, IntentResponse):
        raise TaskOrchestrationError("任务协调器收到非法 P0 输出。")
    if value.route == "agent":
        task_kind: TaskKind | None = "order_diagnosis"
        relation = "continue_active"
    elif value.intent in {"after_sales_eligibility", "apply_after_sales"}:
        task_kind = "after_sales_draft"
        relation = "continue_active"
    elif value.intent == "modify_after_sales":
        task_kind = "after_sales_modification"
        relation = "continue_active"
    else:
        task_kind = None
        relation = "standalone_answer"
    return TurnPlan(
        business_intent=value.intent,
        task_relation=relation,
        route=value.route,
        task_kind=task_kind,
        confirmation_intent="none",
        rationale_code=(
            "active_task_match" if task_kind is not None else "standalone_question"
        ),
        need_tool=value.need_tool,
        tool_call=value.tool_call,
        reply=value.reply,
        chat_scope=value.chat_scope,
        source=value.source,
    )


def _task_owner_fingerprint(
    session_id: str,
    authorization: str | None,
    member_id: int | None,
) -> str:
    try:
        return owner_fingerprint(authorization, member_id)
    except AfterSalesPendingStateError:
        # Anonymous read-only conversations are still scoped to one opaque
        # session.  They cannot confirm a transaction gate because that later
        # path requires the normal owner-bound after-sales state validation.
        return hashlib.sha256(f"anonymous-task:{session_id}".encode("utf-8")).hexdigest()


def _payload_has_work(payload: TaskRuntimePayload) -> bool:
    return any(
        (
            payload.pending_tool_call,
            payload.pending_after_sales_draft,
            payload.pending_after_sales_selection,
            payload.pending_after_sales_modification_draft,
        )
    )


def _would_require_a_third_task(plan: TurnPlan) -> bool:
    """Reject only closed-plan shapes that can allocate a third long task.

    One-turn policy/chat/status questions remain available while two tasks are
    retained. The guard covers a provider error such as treating a new
    logistics request with a missing identifier as a standalone query.
    """

    if plan.task_relation == "start_new_task":
        return True
    if plan.task_relation not in {"standalone_answer", "temporary_detour"}:
        return False
    if plan.route in {"agent", "ask_missing_info"}:
        return True
    return plan.business_intent in {
        "after_sales_eligibility",
        "apply_after_sales",
        "modify_after_sales",
    }


def _goal_summary(plan: TurnPlan) -> str:
    if plan.task_kind == "order_diagnosis":
        return "订单与物流异常诊断"
    if plan.task_kind == "after_sales_modification":
        return "补充或修改售后申请说明"
    return "收集售后申请信息并核验资格"


def _task_label(kind: TaskKind) -> str:
    return {
        "order_diagnosis": "订单异常诊断",
        "after_sales_draft": "售后申请信息收集",
        "after_sales_modification": "售后申请说明修改",
    }[kind]


def _task_hint(task: TaskSnapshot) -> str:
    # Never expose an arbitrary persisted task string.  Older Redis records
    # may predate the stricter snapshot contract; a static hint keeps those
    # records harmless until their normal TTL expires.
    return _task_waiting_hint(task.kind)


def _task_waiting_hint(kind: TaskKind) -> str:
    return {
        "order_diagnosis": "还可继续：补充订单号后核验物流。",
        "after_sales_draft": "还可继续：补充必要信息后核验售后资格。",
        "after_sales_modification": "还可继续：补充新的售后原因或说明。",
    }[kind]


_service = TaskOrchestrationService()
