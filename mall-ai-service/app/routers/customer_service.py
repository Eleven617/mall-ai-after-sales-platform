"""Customer-safe chat and member-owned conversation history endpoints."""
import time
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path

from app.schemas.conversation_history import (
    ConversationHistoryDetail,
    ConversationHistorySummary,
)
from app.schemas.after_sales_application import (
    AfterSalesApplicationView,
)
from app.schemas.customer_service import (
    CustomerServicePublicResponse,
    CustomerServiceRequest,
    to_public_customer_service_response,
)
from app.schemas.agent_ops import CustomerFeedbackRequest, CustomerFeedbackView
from app.schemas.service_case import (
    CustomerServiceCaseCancelRequest,
    CustomerServiceCaseInformationRequest,
    CustomerServiceCaseReopenRequest,
    CustomerServiceCaseTimelineEntry,
    CustomerServiceCaseView,
)
from app.services.conversation_history_client import (
    ConversationHistoryError,
    append_customer_conversation_exchange,
    create_customer_conversation,
    delete_customer_conversation,
    get_customer_conversation,
    list_customer_conversations,
)
from app.services.conversation_history_state import restore_history_context
from app.services.conversation_scope import build_conversation_state_key
from app.services.conversation_state import (
    delete_conversation_state,
    get_conversation_state,
)
from app.services.durable_diagnosis import (
    DiagnosisCheckpointError,
    clear_durable_diagnosis,
)
from app.services.customer_service import handle_customer_message
from app.services.feedback_governance_service import (
    FeedbackGovernanceError,
    feedback_governance_store,
)
from app.services.mall_client import (
    MallApiClientError,
    MallAuthenticationError,
    get_current_member,
    list_my_after_sales_applications,
)
from app.services.service_case_client import (
    ServiceCaseApiError,
    cancel_my_service_case,
    get_my_service_case_timeline,
    list_my_service_cases,
    reopen_my_service_case,
    submit_customer_information,
)
from app.services.tool_context import ToolExecutionContext
from app.services.trace_service import record_trace
from app.services.reliability_service import (
    ConcurrentOperationError,
    RateLimitExceeded,
    ReliabilityBackendUnavailable,
    reliability_governor,
)


router = APIRouter(tags=["customer-service"])


@router.post("/customer-service", response_model=CustomerServicePublicResponse)
def customer_service(
    request: CustomerServiceRequest,
    authorization: str | None = Header(default=None),
) -> CustomerServicePublicResponse:
    started_at = time.monotonic()
    member_id: int | None = None
    history: ConversationHistoryDetail | None = None
    public_conversation_id = request.session_id

    if authorization is not None:
        try:
            member = get_current_member(authorization)
            member_id = member.member_id
            # A signed-in chat must be an already-created member conversation.
            # This prevents a browser from pointing its request at a guessed
            # session label and turns Java into the final ownership authority.
            public_conversation_id = _normalize_conversation_id(request.session_id)
            history = get_customer_conversation(public_conversation_id, authorization)
        except MallAuthenticationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except ConversationHistoryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    scoped_session_id = build_conversation_state_key(public_conversation_id, member_id)
    if history is not None and _needs_history_restore(scoped_session_id):
        restore_history_context(scoped_session_id, history.messages)

    try:
        reliability_governor.check_rate_limit(
            actor_scope=(f"member:{member_id}" if member_id is not None else f"anonymous:{public_conversation_id}"),
            role="unified_after_sales",
            action="customer_service",
        )
        scoped_request = request.model_copy(update={"session_id": scoped_session_id})
        # A single session lock prevents two simultaneous browser requests from
        # overwriting an owner-bound Redis draft or both consuming a pending
        # confirmation. Business writes remain separately protected by Java.
        with reliability_governor.lock(scope=scoped_session_id, kind="session"):
            internal_response = handle_customer_message(
                scoped_request,
                ToolExecutionContext(authorization=authorization, member_id=member_id),
            )
        public_response = to_public_customer_service_response(internal_response)
        if member_id is not None:
            # Only a logged-in member gets an opaque feedback reference. The store
            # retains hashes/references, never the raw customer message or answer.
            public_response = public_response.model_copy(
                update={
                    "response_ref": feedback_governance_store.register_response(
                        member_id=member_id,
                        session_id=scoped_session_id,
                    )
                }
            )
    except RateLimitExceeded as exc:
        reliability_governor.record_request(
            "customer_service", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ConcurrentOperationError as exc:
        reliability_governor.record_request(
            "customer_service", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReliabilityBackendUnavailable as exc:
        reliability_governor.record_request(
            "customer_service", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=503, detail="客服会话保护暂时不可用，请稍后重试。") from exc

    if history is not None:
        _append_public_exchange_without_blocking_customer(
            conversation_id=public_conversation_id,
            request=request,
            response=public_response,
            authorization=authorization,
            scoped_session_id=scoped_session_id,
        )
    reliability_governor.record_request(
        "customer_service", succeeded=True, duration_ms=_elapsed_ms(started_at)
    )
    return public_response


@router.post(
    "/customer-service/feedback",
    response_model=CustomerFeedbackView,
)
def submit_customer_feedback(
    request: CustomerFeedbackRequest,
    authorization: str | None = Header(default=None),
) -> CustomerFeedbackView:
    """Store one consented, structured feedback record for human governance.

    The endpoint intentionally has no free-text field and no route to an LLM,
    EvalCase or training process. A quality developer must later create and
    approve a separate synthetic candidate.
    """

    try:
        member = get_current_member(authorization)
        return feedback_governance_store.submit_feedback(
            member_id=member.member_id,
            request=request,
        )
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FeedbackGovernanceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/customer-service/conversations/{conversation_id}",
    response_model=ConversationHistorySummary,
)
def create_conversation(
    conversation_id: str = Path(..., min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
) -> ConversationHistorySummary:
    try:
        get_current_member(authorization)
        return create_customer_conversation(
            _normalize_conversation_id(conversation_id), authorization
        )
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ConversationHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/customer-service/conversations",
    response_model=list[ConversationHistorySummary],
)
def list_conversations(
    authorization: str | None = Header(default=None),
) -> list[ConversationHistorySummary]:
    try:
        get_current_member(authorization)
        return list_customer_conversations(authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ConversationHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/customer-service/conversations/{conversation_id}",
    response_model=ConversationHistoryDetail,
)
def get_conversation(
    conversation_id: str = Path(..., min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
) -> ConversationHistoryDetail:
    try:
        get_current_member(authorization)
        return get_customer_conversation(_normalize_conversation_id(conversation_id), authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ConversationHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.delete("/customer-service/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str = Path(..., min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
) -> None:
    try:
        member = get_current_member(authorization)
        normalized_id = _normalize_conversation_id(conversation_id)
        scoped_session_id = build_conversation_state_key(normalized_id, member.member_id)
        # Delete the owner-bound durable read-only checkpoint before Java
        # removes the chat.  If Redis cannot confirm deletion, fail closed
        # rather than leave a restorable workflow attached to a deleted chat.
        clear_durable_diagnosis(scoped_session_id, member.member_id)
        delete_customer_conversation(normalized_id, authorization)
        delete_conversation_state(scoped_session_id)
        # Feedback is optional local governance state, not a Java business
        # record.  Remove all feedback references/candidates still tied to the
        # deleted conversation so a stale response reference cannot be reused.
        feedback_governance_store.delete_session_data(
            member_id=member.member_id,
            session_id=scoped_session_id,
        )
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ConversationHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except DiagnosisCheckpointError as exc:
        raise HTTPException(status_code=503, detail="诊断进度暂时不可用，请稍后重试删除会话。") from exc


@router.get(
    "/customer-service/after-sales-applications",
    response_model=list[AfterSalesApplicationView],
)
def list_after_sales_applications(
    authorization: str | None = Header(default=None),
) -> list[AfterSalesApplicationView]:
    """List only generic applications owned by the current authenticated member."""
    try:
        get_current_member(authorization)
        return list_my_after_sales_applications(authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except MallApiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/customer-service/service-cases",
    response_model=list[CustomerServiceCaseView],
)
def list_service_cases(
    authorization: str | None = Header(default=None),
) -> list[CustomerServiceCaseView]:
    """List only Java-projected cases owned by the authenticated member."""
    try:
        get_current_member(authorization)
        return list_my_service_cases(authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ServiceCaseApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/customer-service/service-cases/{case_id}/timeline",
    response_model=list[CustomerServiceCaseTimelineEntry],
)
def service_case_timeline(
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> list[CustomerServiceCaseTimelineEntry]:
    try:
        get_current_member(authorization)
        return get_my_service_case_timeline(case_id, authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ServiceCaseApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/customer-service/service-cases/{case_id}/customer-information",
    response_model=CustomerServiceCaseView,
)
def service_case_customer_information(
    request: CustomerServiceCaseInformationRequest,
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> CustomerServiceCaseView:
    try:
        get_current_member(authorization)
        return submit_customer_information(case_id, request, authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ServiceCaseApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/customer-service/service-cases/{case_id}/cancel",
    response_model=CustomerServiceCaseView,
)
def service_case_cancel(
    request: CustomerServiceCaseCancelRequest,
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> CustomerServiceCaseView:
    try:
        get_current_member(authorization)
        return cancel_my_service_case(case_id, request, authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ServiceCaseApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/customer-service/service-cases/{case_id}/reopen",
    response_model=CustomerServiceCaseView,
)
def service_case_reopen(
    request: CustomerServiceCaseReopenRequest,
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> CustomerServiceCaseView:
    try:
        get_current_member(authorization)
        return reopen_my_service_case(case_id, request, authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ServiceCaseApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _normalize_conversation_id(value: str) -> str:
    try:
        return str(UUID(value.strip()))
    except (AttributeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="会话标识不合法。") from exc


def _needs_history_restore(scoped_session_id: str) -> bool:
    state = get_conversation_state(scoped_session_id)
    return not (
        state.summary
        or state.recent_messages
        or state.facts
        or state.pending_tool_call
        or state.pending_after_sales_draft
        or state.pending_after_sales_proposal
        or state.pending_after_sales_action
        or state.pending_after_sales_selection
        or state.pending_after_sales_modification_draft
        or state.active_after_sales_application
    )


def _append_public_exchange_without_blocking_customer(
    *,
    conversation_id: str,
    request: CustomerServiceRequest,
    response: CustomerServicePublicResponse,
    authorization: str | None,
    scoped_session_id: str,
) -> None:
    try:
        append_customer_conversation_exchange(
            conversation_id=conversation_id,
            title=_safe_conversation_title(response),
            user_message=request.message,
            assistant_message=response.answer,
            public_response=response,
            authorization=authorization,
        )
    except ConversationHistoryError:
        # The customer has already received the public response. History is a
        # convenience feature, not a reason to falsely report that their
        # read-only answer or completed business action failed.
        record_trace("conversation_history", "append_unavailable", scoped_session_id)


def _safe_conversation_title(response: CustomerServicePublicResponse) -> str:
    """Choose only allow-listed generic labels; never derive from raw text."""
    if (
        response.after_sales_draft
        or response.after_sales_proposal
        or response.submitted_after_sales_application
        or response.after_sales_eligibility
        or response.after_sales_pending_action
        or response.after_sales_selection
        or response.after_sales_applications
    ):
        return "售后申请"
    if response.diagnosis and response.diagnosis.category == "policy_insufficient":
        return "售后政策咨询"
    if response.verified_facts:
        sources = {card.source for card in response.verified_facts}
        if sources & {"order_service", "logistics_service"}:
            return "订单与物流咨询"
    if response.diagnosis:
        return "订单问题咨询"
    return "售后咨询"


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))
