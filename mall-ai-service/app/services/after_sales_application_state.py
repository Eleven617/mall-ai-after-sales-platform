"""Owner- and session-bound pending state for the unified after-sales flow."""
import hashlib
import time

from app.schemas.after_sales_application import (
    ActiveAfterSalesApplicationTarget,
    AfterSalesDraftField,
    AfterSalesDraftView,
    AfterSalesPendingActionView,
    AfterSalesProposalView,
    AfterSalesSelectionView,
    PendingAfterSalesAction,
    PendingAfterSalesDraft,
    PendingAfterSalesModificationDraft,
    PendingAfterSalesProposal,
    PendingAfterSalesSelection,
)
from app.services.conversation_state import get_conversation_state, save_conversation_state


PENDING_AFTER_SALES_DRAFT_TTL_SECONDS = 15 * 60
PENDING_AFTER_SALES_PROPOSAL_TTL_SECONDS = 10 * 60
PENDING_AFTER_SALES_ACTION_TTL_SECONDS = 10 * 60
PENDING_AFTER_SALES_SELECTION_TTL_SECONDS = 10 * 60
PENDING_AFTER_SALES_RECOVERY_TTL_SECONDS = 24 * 60 * 60
ACTIVE_AFTER_SALES_TARGET_TTL_SECONDS = 24 * 60 * 60


class AfterSalesPendingStateError(RuntimeError):
    pass


class AfterSalesTransactionGateConflictError(AfterSalesPendingStateError):
    """A second confirmation candidate must never replace the first one.

    Conversation tasks may continue while a proposal/action waits for
    confirmation. The transaction layer still owns exactly one durable,
    owner-bound write candidate, so callers must keep their task draft and ask
    the customer to resolve the existing gate before creating another card.
    """


def owner_fingerprint(authorization: str | None, member_id: int | None = None) -> str:
    """Bind mutable workflow state to the authenticated member, never raw JWT."""
    if member_id is not None:
        material = f"member:{member_id}"
    elif authorization and authorization.startswith("Bearer "):
        material = authorization
    else:
        raise AfterSalesPendingStateError("请先登录后再办理售后申请。")
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def session_fingerprint(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def save_active_after_sales_application(
    session_id: str,
    authorization: str | None,
    member_id: int | None,
    application_id: int,
) -> None:
    """Remember one already-authorized customer-visible application number.

    The target is only a convenience for a follow-up message such as
    “这个售后进度怎么样”.  It is still reloaded from Java's current-member list
    before use, so this Redis value can never grant access by itself.
    """
    if application_id <= 0:
        raise AfterSalesPendingStateError("售后申请标识不合法。")
    state = get_conversation_state(session_id)
    state.active_after_sales_application = ActiveAfterSalesApplicationTarget(
        application_id=application_id,
        owner_fingerprint=owner_fingerprint(authorization, member_id),
        session_fingerprint=session_fingerprint(session_id),
        expires_at=time.time() + ACTIVE_AFTER_SALES_TARGET_TTL_SECONDS,
    )
    save_conversation_state(state)


def get_active_after_sales_application(
    session_id: str,
    authorization: str | None,
    member_id: int | None,
) -> int | None:
    """Return a recent target only for its original member and conversation.

    Unlike a pending write, a stale target merely means there is no usable
    conversational reference.  It is cleared silently instead of revealing
    that another account ever selected an application in this session key.
    """
    state = get_conversation_state(session_id)
    target = state.active_after_sales_application
    if target is None:
        return None
    if time.time() > target.expires_at:
        state.active_after_sales_application = None
        save_conversation_state(state)
        return None
    try:
        expected_owner = owner_fingerprint(authorization, member_id)
    except AfterSalesPendingStateError:
        return None
    if (
        target.owner_fingerprint != expected_owner
        or target.session_fingerprint != session_fingerprint(session_id)
    ):
        return None
    return target.application_id


def has_pending_after_sales_work(session_id: str) -> bool:
    """Check only for server-persisted work that may safely resume before routing.

    The check does not validate ownership or execute anything.  Each concrete
    pending handler still performs its normal owner/session/TTL validation
    before it can read, prepare, or write a business record.
    """
    state = get_conversation_state(session_id)
    return any(
        (
            state.pending_after_sales_draft,
            state.pending_after_sales_proposal,
            state.pending_after_sales_action,
            state.pending_after_sales_selection,
            state.pending_after_sales_modification_draft,
        )
    )


def save_pending_after_sales_draft(session_id: str, draft: PendingAfterSalesDraft) -> None:
    state = get_conversation_state(session_id)
    state.pending_after_sales_draft = draft
    state.pending_after_sales_selection = None
    state.pending_after_sales_modification_draft = None
    _set_non_transaction_status(state, "collecting_information")
    save_conversation_state(state)


def get_pending_after_sales_draft(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesDraft | None:
    state = get_conversation_state(session_id)
    draft = state.pending_after_sales_draft
    if draft is None:
        return None
    if time.time() > draft.expires_at:
        state.pending_after_sales_draft = None
        state.facts.pop("after_sales_flow_status", None)
        save_conversation_state(state)
        return None
    if draft.owner_fingerprint != owner_fingerprint(authorization, member_id):
        raise AfterSalesPendingStateError("登录用户已变化，请重新发起售后申请。")
    return draft


def clear_pending_after_sales_draft(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> bool:
    draft = get_pending_after_sales_draft(session_id, authorization, member_id)
    if draft is None:
        return False
    state = get_conversation_state(session_id)
    state.pending_after_sales_draft = None
    _clear_non_transaction_status(state)
    save_conversation_state(state)
    return True


def save_pending_after_sales_proposal(
    session_id: str,
    proposal: PendingAfterSalesProposal,
) -> None:
    if proposal.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后确认会话不匹配，请重新发起申请。")
    state = get_conversation_state(session_id)
    if _has_transaction_gate(state):
        raise AfterSalesTransactionGateConflictError(
            "当前已有待确认的售后方案或操作，不能覆盖。"
        )
    state.pending_after_sales_draft = None
    state.pending_after_sales_proposal = proposal
    state.pending_after_sales_action = None
    state.pending_after_sales_selection = None
    state.pending_after_sales_modification_draft = None
    state.facts["after_sales_flow_status"] = proposal.submission_state
    save_conversation_state(state)


def get_pending_after_sales_proposal(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesProposal | None:
    state = get_conversation_state(session_id)
    proposal = state.pending_after_sales_proposal
    if proposal is None:
        return None
    if time.time() > proposal.expires_at:
        state.pending_after_sales_proposal = None
        state.facts.pop("after_sales_flow_status", None)
        save_conversation_state(state)
        return None
    if proposal.owner_fingerprint != owner_fingerprint(authorization, member_id):
        raise AfterSalesPendingStateError("登录用户已变化，请重新发起售后申请。")
    if proposal.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后确认会话不匹配，请重新发起申请。")
    return proposal


def complete_pending_after_sales_proposal(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesProposal | None:
    proposal = get_pending_after_sales_proposal(session_id, authorization, member_id)
    if proposal is None:
        return None
    state = get_conversation_state(session_id)
    state.pending_after_sales_proposal = None
    _clear_non_transaction_status(state)
    save_conversation_state(state)
    return proposal


def cancel_pending_after_sales_proposal(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> bool:
    return complete_pending_after_sales_proposal(session_id, authorization, member_id) is not None


def mark_pending_after_sales_submission_unknown(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesProposal | None:
    proposal = get_pending_after_sales_proposal(session_id, authorization, member_id)
    if proposal is None:
        return None
    proposal.submission_state = "submission_unknown"
    proposal.expires_at = max(
        proposal.expires_at,
        time.time() + PENDING_AFTER_SALES_RECOVERY_TTL_SECONDS,
    )
    state = get_conversation_state(session_id)
    state.pending_after_sales_proposal = proposal
    state.facts["after_sales_flow_status"] = "submission_unknown"
    save_conversation_state(state)
    return proposal


def save_pending_after_sales_action(
    session_id: str,
    action: PendingAfterSalesAction,
) -> None:
    if action.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后确认会话不匹配，请重新发起操作。")
    state = get_conversation_state(session_id)
    if _has_transaction_gate(state):
        raise AfterSalesTransactionGateConflictError(
            "当前已有待确认的售后方案或操作，不能覆盖。"
        )
    state.pending_after_sales_draft = None
    state.pending_after_sales_proposal = None
    state.pending_after_sales_action = action
    state.pending_after_sales_selection = None
    state.pending_after_sales_modification_draft = None
    state.facts["after_sales_flow_status"] = action.execution_state
    save_conversation_state(state)


def get_pending_after_sales_action(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesAction | None:
    state = get_conversation_state(session_id)
    action = state.pending_after_sales_action
    if action is None:
        return None
    if time.time() > action.expires_at:
        state.pending_after_sales_action = None
        state.facts.pop("after_sales_flow_status", None)
        save_conversation_state(state)
        return None
    if action.owner_fingerprint != owner_fingerprint(authorization, member_id):
        raise AfterSalesPendingStateError("登录用户已变化，请重新发起售后操作。")
    if action.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后确认会话不匹配，请重新发起操作。")
    return action


def complete_pending_after_sales_action(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesAction | None:
    action = get_pending_after_sales_action(session_id, authorization, member_id)
    if action is None:
        return None
    state = get_conversation_state(session_id)
    state.pending_after_sales_action = None
    _clear_non_transaction_status(state)
    save_conversation_state(state)
    return action


def mark_pending_after_sales_action_unknown(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesAction | None:
    action = get_pending_after_sales_action(session_id, authorization, member_id)
    if action is None:
        return None
    action.execution_state = "execution_unknown"
    action.expires_at = max(
        action.expires_at, time.time() + PENDING_AFTER_SALES_RECOVERY_TTL_SECONDS
    )
    state = get_conversation_state(session_id)
    state.pending_after_sales_action = action
    state.facts["after_sales_flow_status"] = action.execution_state
    save_conversation_state(state)
    return action


def mark_pending_after_sales_action_retryable(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesAction | None:
    action = get_pending_after_sales_action(session_id, authorization, member_id)
    if action is None:
        return None
    action.execution_state = "awaiting_confirmation"
    state = get_conversation_state(session_id)
    state.pending_after_sales_action = action
    state.facts["after_sales_flow_status"] = action.execution_state
    save_conversation_state(state)
    return action


def to_after_sales_pending_action_view(
    action: PendingAfterSalesAction,
    *,
    application_type_label: str,
) -> AfterSalesPendingActionView:
    if action.action == "cancel":
        impact = "确认后将取消该待处理售后申请；取消后不能恢复。"
    else:
        impact = "确认后将更新该售后申请的原因或补充说明；订单、商品和申请类型不会改变。"
    return AfterSalesPendingActionView(
        action=action.action,
        application_id=action.application_id,
        application_type_label=application_type_label,
        impact_summary=impact,
        reason=action.reason,
        description=action.description,
    )


def save_pending_after_sales_selection(
    session_id: str,
    selection: PendingAfterSalesSelection,
) -> None:
    """Persist a member-owned ambiguity choice; never trust a later raw ID.

    Selection is a read/prepare step only.  It carries a fixed, server-derived
    set of applications and therefore does not allow the browser or model to
    switch to an arbitrary member's record before Java checks ownership again.
    """
    if selection.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后选择会话不匹配，请重新发起操作。")
    state = get_conversation_state(session_id)
    state.pending_after_sales_draft = None
    state.pending_after_sales_selection = selection
    state.pending_after_sales_modification_draft = None
    _set_non_transaction_status(state, "awaiting_application_selection")
    save_conversation_state(state)


def get_pending_after_sales_selection(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesSelection | None:
    state = get_conversation_state(session_id)
    selection = state.pending_after_sales_selection
    if selection is None:
        return None
    if time.time() > selection.expires_at:
        state.pending_after_sales_selection = None
        state.facts.pop("after_sales_flow_status", None)
        save_conversation_state(state)
        return None
    if selection.owner_fingerprint != owner_fingerprint(authorization, member_id):
        raise AfterSalesPendingStateError("登录用户已变化，请重新发起售后操作。")
    if selection.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后选择会话不匹配，请重新发起操作。")
    return selection


def complete_pending_after_sales_selection(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesSelection | None:
    selection = get_pending_after_sales_selection(session_id, authorization, member_id)
    if selection is None:
        return None
    state = get_conversation_state(session_id)
    state.pending_after_sales_selection = None
    _clear_non_transaction_status(state)
    save_conversation_state(state)
    return selection


def to_after_sales_selection_view(
    selection: PendingAfterSalesSelection,
) -> AfterSalesSelectionView:
    return AfterSalesSelectionView(
        purpose=selection.purpose,
        candidates=selection.candidates,
    )


def save_pending_after_sales_modification_draft(
    session_id: str,
    draft: PendingAfterSalesModificationDraft,
) -> None:
    if draft.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后修改会话不匹配，请重新发起操作。")
    state = get_conversation_state(session_id)
    state.pending_after_sales_draft = None
    state.pending_after_sales_selection = None
    state.pending_after_sales_modification_draft = draft
    _set_non_transaction_status(state, "collecting_modification")
    save_conversation_state(state)


def get_pending_after_sales_modification_draft(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesModificationDraft | None:
    state = get_conversation_state(session_id)
    draft = state.pending_after_sales_modification_draft
    if draft is None:
        return None
    if time.time() > draft.expires_at:
        state.pending_after_sales_modification_draft = None
        state.facts.pop("after_sales_flow_status", None)
        save_conversation_state(state)
        return None
    if draft.owner_fingerprint != owner_fingerprint(authorization, member_id):
        raise AfterSalesPendingStateError("登录用户已变化，请重新发起售后操作。")
    if draft.session_fingerprint != session_fingerprint(session_id):
        raise AfterSalesPendingStateError("售后修改会话不匹配，请重新发起操作。")
    return draft


def complete_pending_after_sales_modification_draft(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesModificationDraft | None:
    draft = get_pending_after_sales_modification_draft(session_id, authorization, member_id)
    if draft is None:
        return None
    state = get_conversation_state(session_id)
    state.pending_after_sales_modification_draft = None
    _clear_non_transaction_status(state)
    save_conversation_state(state)
    return draft


def mark_pending_after_sales_submission_retryable(
    session_id: str,
    authorization: str | None,
    member_id: int | None = None,
) -> PendingAfterSalesProposal | None:
    proposal = get_pending_after_sales_proposal(session_id, authorization, member_id)
    if proposal is None:
        return None
    proposal.submission_state = "awaiting_confirmation"
    state = get_conversation_state(session_id)
    state.pending_after_sales_proposal = proposal
    state.facts["after_sales_flow_status"] = "awaiting_confirmation"
    save_conversation_state(state)
    return proposal


def to_after_sales_draft_view(
    draft: PendingAfterSalesDraft,
    missing_fields: list[AfterSalesDraftField],
) -> AfterSalesDraftView:
    return AfterSalesDraftView(
        draft_id=draft.draft_id,
        missing_fields=missing_fields,
        goal=draft.goal,
        application_type=draft.application_type,
        application_type_label=(
            application_type_label(draft.application_type) if draft.application_type else None
        ),
        order_sn=draft.order_sn,
        product_options=draft.product_options,
    )


def to_after_sales_proposal_view(
    proposal: PendingAfterSalesProposal,
) -> AfterSalesProposalView:
    return AfterSalesProposalView(
        application_type=proposal.application_type,
        application_type_label=application_type_label(proposal.application_type),
        order_sn=proposal.order_sn,
        product_name=proposal.product_name,
        product_attr=proposal.product_attr,
        reason=proposal.reason,
        description=proposal.description,
    )


def application_type_label(value: str | None) -> str:
    return {
        "cancel_refund": "取消退款",
        "return_refund": "退货退款",
        "exchange": "换货",
        "repair": "维修/质保",
    }.get(value or "", "售后申请")


def _has_transaction_gate(state) -> bool:
    """Return whether a proposal/action already reserves the write gate."""

    now = time.time()
    return (
        (
            state.pending_after_sales_proposal is not None
            and state.pending_after_sales_proposal.expires_at > now
        )
        or (
            state.pending_after_sales_action is not None
            and state.pending_after_sales_action.expires_at > now
        )
    )


def _set_non_transaction_status(state, value: str) -> None:
    """Do not let task progress overwrite a confirmation marker."""

    if not _has_transaction_gate(state):
        state.facts["after_sales_flow_status"] = value


def _clear_non_transaction_status(state) -> None:
    """A task may finish while a separate transaction gate remains valid."""

    if not _has_transaction_gate(state):
        state.facts.pop("after_sales_flow_status", None)


__all__ = [
    "AfterSalesPendingStateError",
    "AfterSalesTransactionGateConflictError",
    "PENDING_AFTER_SALES_ACTION_TTL_SECONDS",
    "PENDING_AFTER_SALES_DRAFT_TTL_SECONDS",
    "PENDING_AFTER_SALES_PROPOSAL_TTL_SECONDS",
    "PENDING_AFTER_SALES_SELECTION_TTL_SECONDS",
    "application_type_label",
    "cancel_pending_after_sales_proposal",
    "clear_pending_after_sales_draft",
    "complete_pending_after_sales_proposal",
    "complete_pending_after_sales_action",
    "complete_pending_after_sales_modification_draft",
    "complete_pending_after_sales_selection",
    "get_pending_after_sales_action",
    "has_pending_after_sales_work",
    "get_pending_after_sales_modification_draft",
    "get_pending_after_sales_draft",
    "get_pending_after_sales_proposal",
    "get_pending_after_sales_selection",
    "mark_pending_after_sales_submission_retryable",
    "mark_pending_after_sales_submission_unknown",
    "mark_pending_after_sales_action_unknown",
    "mark_pending_after_sales_action_retryable",
    "owner_fingerprint",
    "save_pending_after_sales_draft",
    "save_pending_after_sales_proposal",
    "save_pending_after_sales_action",
    "save_pending_after_sales_modification_draft",
    "save_pending_after_sales_selection",
    "session_fingerprint",
    "to_after_sales_draft_view",
    "to_after_sales_pending_action_view",
    "to_after_sales_proposal_view",
    "to_after_sales_selection_view",
]
