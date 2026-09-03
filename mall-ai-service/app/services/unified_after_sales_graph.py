"""One bounded LangGraph subgraph for every customer after-sales request.

This is deliberately not a new customer-facing Agent.  It is a workflow
subgraph behind the existing customer-service entrypoint, alongside the
read-only order-diagnosis graph and policy RAG.  Redis owns durable work across
messages; this graph only orchestrates one request's safe branches.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.schemas.agent import AgentRunResult
from app.schemas.after_sales_application import (
    AfterSalesApplicationCandidateView,
    AfterSalesApplicationView,
    AfterSalesFlowResult,
    AfterSalesSelectionView,
    PendingAfterSalesSelection,
)
from app.services.after_sales_application_service import (
    AfterSalesApplicationError,
    handle_pending_after_sales_action_confirmation,
    handle_pending_after_sales_confirmation,
    handle_pending_after_sales_draft,
    handle_pending_after_sales_modification_draft,
    prepare_after_sales_action,
    start_after_sales_flow,
    start_after_sales_modification_draft,
)
from app.services.after_sales_application_state import (
    AfterSalesPendingStateError,
    PENDING_AFTER_SALES_SELECTION_TTL_SECONDS,
    complete_pending_after_sales_selection,
    get_active_after_sales_application,
    get_pending_after_sales_selection,
    owner_fingerprint,
    save_active_after_sales_application,
    save_pending_after_sales_selection,
    session_fingerprint,
    to_after_sales_selection_view,
)
from app.services.identifier_extraction import extract_order_sn
from app.services.diagnosis_agent import run_diagnosis_agent
from app.services.llm_service import LLMResponse, generate_with_tools
from app.services.mall_client import MallApiClientError, list_my_after_sales_applications
from app.services.trace_service import record_trace
from app.services.tool_context import ToolExecutionContext
from app.services.tool_registry import call_tool


UnifiedIntent = Literal[
    "after_sales_eligibility",
    "apply_after_sales",
    "list_after_sales",
    "status_after_sales",
    "cancel_after_sales",
    "modify_after_sales",
    "follow_up_after_sales",
]


class UnifiedAfterSalesState(TypedDict, total=False):
    session_id: str
    message: str
    authorization: str | None
    member_id: int | None
    tool_context: ToolExecutionContext
    conversation_context: str
    requires_order_facts: bool
    diagnosis_started_at: float | None
    intent_name: str
    resume_only: bool
    # The isolated quality evaluator invokes the same bounded read-only
    # investigation branch with synthetic tools.  It must never touch Redis
    # pending state, because that would turn an offline eval into a request
    # against a live conversation store.  Customer requests keep this false
    # and still recover server-owned pending work before any new dispatch.
    skip_pending_recovery: bool
    result: AfterSalesFlowResult | AgentRunResult
    next_node: Literal["dispatch", "finish"]


def run_unified_after_sales_graph(
    *,
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None,
    intent_name: str,
) -> AfterSalesFlowResult | None:
    """Run one bounded request without giving the model business write access."""
    graph = build_unified_after_sales_graph()
    initial: UnifiedAfterSalesState = {
        "session_id": session_id,
        "message": message,
        "authorization": authorization,
        "member_id": member_id,
        "intent_name": intent_name,
    }
    final = graph.invoke(initial)
    result = final.get(
        "result",
        AfterSalesFlowResult(answer="暂时无法处理本次售后请求，请稍后重试或联系人工客服。"),
    )
    if isinstance(result, AfterSalesFlowResult):
        return result
    return AfterSalesFlowResult(answer="暂时无法处理本次售后请求，请稍后重试或联系人工客服。")


def resume_unified_after_sales_task(
    *,
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None,
    resume_from_task: bool = False,
) -> AfterSalesFlowResult | None:
    """Continue only a task payload already selected by task-aware P0.

    This function is intentionally not called for a new message before P0.
    Proposal/action confirmation is a separate transaction gate and never
    participates in this task continuation list.
    """

    for handler in (
        handle_pending_after_sales_modification_draft,
        _handle_pending_selection,
    ):
        result = handler(session_id, message, authorization, member_id)
        if result is not None:
            return result
    result = handle_pending_after_sales_draft(
        session_id,
        message,
        authorization,
        member_id,
        resume_from_task=resume_from_task,
    )
    if result is not None:
        return result
    return None


GenerateWithTools = Callable[[list[dict[str, Any]], list[dict[str, Any]]], LLMResponse]
CallTool = Callable[[Any, ToolExecutionContext | None], dict[str, Any]]


def run_unified_after_sales_investigation(
    *,
    session_id: str,
    message: str,
    tool_context: ToolExecutionContext,
    conversation_context: str = "",
    requires_order_facts: bool = False,
    generate_fn: GenerateWithTools | None = None,
    call_tool_fn: CallTool | None = None,
    diagnosis_started_at: float | None = None,
) -> AgentRunResult:
    """Run the existing ReAct graph as a read-only unified-after-sales subflow.

    This is the sole customer-service entry for multi-step investigation. The
    model still only proposes allow-listed reads; fixed after-sales actions and
    all business writes remain outside this path.
    """

    graph = build_unified_after_sales_graph(
        generate_fn=generate_fn,
        call_tool_fn=call_tool_fn,
    )
    final = graph.invoke(
        {
            "session_id": session_id,
            "message": message,
            "authorization": tool_context.authorization,
            "member_id": tool_context.member_id,
            "tool_context": tool_context.for_skill("order_exception_diagnosis"),
            "conversation_context": conversation_context,
            "requires_order_facts": requires_order_facts,
            "intent_name": "read_only_investigation",
            "resume_only": False,
            "skip_pending_recovery": True,
            "diagnosis_started_at": diagnosis_started_at,
        }
    )
    result = final.get("result")
    if isinstance(result, AgentRunResult):
        return result
    return AgentRunResult(
        answer="订单与物流调查暂时不可用，请稍后重试或联系人工客服；系统未执行任何写操作。"
    )


def build_unified_after_sales_graph(
    *,
    generate_fn: GenerateWithTools | None = None,
    call_tool_fn: CallTool | None = None,
):
    """Build a small, explicit graph; cross-message state remains in Redis."""

    diagnosis_generate_fn = generate_fn or generate_with_tools
    diagnosis_call_tool_fn = call_tool_fn or call_tool

    def dispatch(state: UnifiedAfterSalesState) -> dict[str, Any]:
        session_id = state["session_id"]
        intent_name = state.get("intent_name", "")
        record_trace(
            "unified_after_sales",
            "graph_node_entered",
            session_id,
            node="dispatch",
            intent=intent_name,
        )
        if intent_name == "read_only_investigation":
            context = state.get("tool_context")
            if context is None:
                result = AgentRunResult(
                    answer="订单与物流调查暂时不可用，请稍后重试；系统未执行任何写操作。"
                )
            else:
                record_trace(
                    "unified_after_sales",
                    "graph_node_entered",
                    session_id,
                    node="read_only_investigation",
                )
                started_at = time.perf_counter()
                try:
                    result = run_diagnosis_agent(
                        user_message=state["message"],
                        tool_context=context,
                        session_id=session_id,
                        conversation_context=state.get("conversation_context", ""),
                        generate_fn=diagnosis_generate_fn,
                        call_tool_fn=diagnosis_call_tool_fn,
                        member_id=context.member_id,
                        requires_order_facts=state.get("requires_order_facts", False),
                        started_at=state.get("diagnosis_started_at"),
                    )
                    # A provider failure before any verified fact exists is a
                    # safe availability stop, not a customer-visible diagnosis
                    # explanation.  Preserve partial verified facts from a
                    # later tool failure, but make the no-fact case actionable.
                    if (
                        result.diagnosis is not None
                        and result.diagnosis.category == "tool_failure"
                        and not result.verified_facts
                    ):
                        result = result.model_copy(
                            update={
                                "answer": (
                                    "订单与物流调查暂时不可用，请稍后重试或联系人工客服；"
                                    "系统未执行任何写操作。"
                                )
                            }
                        )
                    result_kind = (
                        "pending"
                        if result.durable_checkpoint_pending
                        else "failure"
                        if result.diagnosis and result.diagnosis.category == "tool_failure"
                        else "success"
                    )
                except Exception:
                    result = AgentRunResult(
                        answer="订单与物流调查暂时不可用，请稍后重试；系统未执行任何写操作。"
                    )
                    result_kind = "failure"
                record_trace(
                    "unified_after_sales",
                    "read_only_investigation_finished",
                    session_id,
                    node="read_only_investigation",
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    result_kind=result_kind,
                )
        elif intent_name in {"after_sales_eligibility", "apply_after_sales"}:
            result = start_after_sales_flow(
                session_id,
                state["message"],
                state.get("authorization"),
                state.get("member_id"),
            )
        elif intent_name == "list_after_sales":
            result = _list_result(state.get("authorization"))
        elif intent_name in {
            "status_after_sales",
            "cancel_after_sales",
            "modify_after_sales",
            "follow_up_after_sales",
        }:
            result = _handle_existing_application_intent(
                session_id=session_id,
                message=state["message"],
                authorization=state.get("authorization"),
                member_id=state.get("member_id"),
                intent_name=intent_name,
            )
        else:
            result = AfterSalesFlowResult(
                answer="请说明是咨询售后政策、核验资格、办理申请，还是查询已有售后进度。"
            )
        return {"result": result, "next_node": "finish"}

    graph = StateGraph(UnifiedAfterSalesState)
    graph.add_node("dispatch", dispatch)
    graph.add_node("finish", lambda state: {})
    graph.add_edge(START, "dispatch")
    graph.add_edge("dispatch", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def _list_result(authorization: str | None) -> AfterSalesFlowResult:
    try:
        applications = list_my_after_sales_applications(authorization)
    except MallApiClientError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    if not applications:
        return AfterSalesFlowResult(answer="当前账号没有已提交的统一售后申请。", applications=[])
    return AfterSalesFlowResult(
        answer=f"已查到当前账号 {len(applications)} 笔售后申请，可查看申请与履约状态。",
        applications=applications,
    )


def _handle_existing_application_intent(
    *,
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None,
    intent_name: str,
) -> AfterSalesFlowResult:
    try:
        applications = list_my_after_sales_applications(authorization)
    except MallApiClientError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    contextual = _session_context_application(
        session_id=session_id,
        authorization=authorization,
        member_id=member_id,
        applications=applications,
        message=message,
    )
    if contextual is not None:
        return _handle_selected_application(
            session_id=session_id,
            authorization=authorization,
            member_id=member_id,
            application=contextual,
            purpose=_selection_purpose(intent_name),
            message=message,
        )
    candidates = _filter_candidates(applications, message, intent_name)
    if not candidates:
        return AfterSalesFlowResult(
            answer="当前账号没有可匹配的售后申请；请先核对申请号或订单号，也可以发起新的资格核验。",
            applications=applications,
        )
    selected = _explicit_selected_application(candidates, message)
    if selected is None and len(candidates) == 1:
        selected = candidates[0]
    if selected is None:
        return _save_selection(
            session_id=session_id,
            authorization=authorization,
            member_id=member_id,
            purpose=_selection_purpose(intent_name),
            candidates=candidates,
            message=message,
        )
    return _handle_selected_application(
        session_id=session_id,
        authorization=authorization,
        member_id=member_id,
        application=selected,
        purpose=_selection_purpose(intent_name),
        message=message,
    )


def _handle_pending_selection(
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None,
) -> AfterSalesFlowResult | None:
    try:
        selection = get_pending_after_sales_selection(session_id, authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    if selection is None:
        return None
    selected_candidate = _selected_from_pending_selection(selection, message)
    if selected_candidate is None:
        if _looks_like_selection_attempt(message):
            return AfterSalesFlowResult(
                answer="请选择上方列出的售后申请编号或序号；为保护账号数据，系统不会猜测目标申请。",
                selection=to_after_sales_selection_view(selection),
            )
        return None
    try:
        current_applications = list_my_after_sales_applications(authorization)
    except MallApiClientError as exc:
        return AfterSalesFlowResult(
            answer=str(exc), selection=to_after_sales_selection_view(selection)
        )
    selected = next(
        (
            item
            for item in current_applications
            if item.application_id == selected_candidate.application_id
        ),
        None,
    )
    if selected is None:
        complete_pending_after_sales_selection(session_id, authorization, member_id)
        return AfterSalesFlowResult(
            answer="所选售后申请已不存在或当前账号无权访问，请重新查询售后记录。"
        )
    complete_pending_after_sales_selection(session_id, authorization, member_id)
    return _handle_selected_application(
        session_id=session_id,
        authorization=authorization,
        member_id=member_id,
        application=selected,
        purpose=selection.purpose,
        message=message,
        carried_reason=selection.reason,
        carried_description=selection.description,
    )


def _handle_selected_application(
    *,
    session_id: str,
    authorization: str | None,
    member_id: int | None,
    application: AfterSalesApplicationView,
    purpose: Literal["status", "cancel", "modify", "follow_up"],
    message: str,
    carried_reason: str | None = None,
    carried_description: str | None = None,
) -> AfterSalesFlowResult:
    try:
        save_active_after_sales_application(
            session_id, authorization, member_id, application.application_id
        )
    except AfterSalesPendingStateError:
        # Java-derived data remains usable for this read-only reply.  A missing
        # local convenience target must never turn into a different write path.
        pass
    if purpose == "status":
        return _status_result(application)
    if purpose == "cancel":
        return prepare_after_sales_action(
            session_id=session_id,
            authorization=authorization,
            member_id=member_id,
            application=application,
            action="cancel",
        )
    if purpose == "modify":
        reason, description = _narrative_from_message(message, carried_reason, carried_description)
        reason, description = _normalize_modification_for_application(
            application, reason, description
        )
        if reason is None and description is None:
            return start_after_sales_modification_draft(
                session_id=session_id,
                authorization=authorization,
                member_id=member_id,
                application=application,
            )
        return prepare_after_sales_action(
            session_id=session_id,
            authorization=authorization,
            member_id=member_id,
            application=application,
            action="modify",
            reason=reason,
            description=description,
        )
    return _follow_up_result(application)


def _status_result(application: AfterSalesApplicationView) -> AfterSalesFlowResult:
    detail = application.handling_note or "暂无新的审核说明。"
    fulfillment_note = application.fulfillment_note or "暂无新的履约说明。"
    return AfterSalesFlowResult(
        answer=(
            f"售后单 #{application.application_id} 当前申请状态为“{application.status_label}”，"
            f"履约状态为“{application.fulfillment_status_label}”。{detail} {fulfillment_note}"
        ),
        applications=[application],
    )


def _follow_up_result(application: AfterSalesApplicationView) -> AfterSalesFlowResult:
    if application.status == "pending_review":
        next_step = "该申请仍待审核；如需变更，可说“修改售后申请”，也可说“取消售后申请”。"
    elif application.status in {"accepted", "unknown"}:
        if application.fulfillment_status == "failed":
            next_step = "履约出现失败，请依据上述真实说明补充信息或联系人工客服；系统不会自动重开申请。"
        elif application.can_supplement:
            next_step = "申请已进入处理阶段；可补充必要说明，或联系人工客服跟进。"
        else:
            next_step = "申请已进入处理阶段，请以真实履约进度为准；需要人工协助时可联系商城客服。"
    elif application.status == "completed":
        next_step = "该申请已完成；如商品仍有问题，可重新核验当前订单是否符合新的售后资格，系统不会自动重开。"
    else:
        next_step = "该申请当前不能直接修改或取消；如对处理结果有疑问，请联系人工客服。"
    return AfterSalesFlowResult(
        answer=(
            f"售后单 #{application.application_id} 当前申请状态为“{application.status_label}”，"
            f"履约状态为“{application.fulfillment_status_label}”。{application.fulfillment_note or application.handling_note or ''} {next_step}"
        ).strip(),
        applications=[application],
    )


def _filter_candidates(
    applications: list[AfterSalesApplicationView],
    message: str,
    intent_name: str,
) -> list[AfterSalesApplicationView]:
    if intent_name == "follow_up_after_sales":
        active = [
            item
            for item in applications
            if item.status not in {"completed", "rejected", "cancelled"}
        ]
        return active or applications
    explicit_id = _application_id_from_message(message)
    if explicit_id is not None:
        return [item for item in applications if item.application_id == explicit_id]
    order_resolution = extract_order_sn(message)
    if order_resolution.value:
        by_order = [item for item in applications if item.order_sn == order_resolution.value]
        if by_order:
            return by_order
    return applications[:10]


def _session_context_application(
    *,
    session_id: str,
    authorization: str | None,
    member_id: int | None,
    applications: list[AfterSalesApplicationView],
    message: str,
) -> AfterSalesApplicationView | None:
    """Resolve a pronoun-like follow-up from a server-bound prior selection.

    An explicit application or order reference always wins.  The target is
    also checked against the freshly Java-filtered list, so Redis never acts
    as an authorization source.
    """
    if _application_id_from_message(message) is not None or extract_order_sn(message).value:
        return None
    target_id = get_active_after_sales_application(session_id, authorization, member_id)
    if target_id is None:
        return None
    return next((item for item in applications if item.application_id == target_id), None)


def _save_selection(
    *,
    session_id: str,
    authorization: str | None,
    member_id: int | None,
    purpose: Literal["status", "cancel", "modify", "follow_up"],
    candidates: list[AfterSalesApplicationView],
    message: str,
) -> AfterSalesFlowResult:
    try:
        fingerprint = owner_fingerprint(authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    reason, description = _narrative_from_message(message, None, None)
    selection = PendingAfterSalesSelection(
        selection_id=uuid4().hex,
        purpose=purpose,
        owner_fingerprint=fingerprint,
        session_fingerprint=session_fingerprint(session_id),
        candidates=[_candidate_view(item) for item in candidates[:10]],
        reason=reason,
        description=description,
        expires_at=time.time() + PENDING_AFTER_SALES_SELECTION_TTL_SECONDS,
    )
    save_pending_after_sales_selection(session_id, selection)
    record_trace(
        "unified_after_sales",
        "application_selection_requested",
        session_id,
        purpose=purpose,
        candidate_count=len(selection.candidates),
    )
    return AfterSalesFlowResult(
        answer="查询到多笔可匹配的售后申请，请选择申请编号或序号后继续。",
        selection=to_after_sales_selection_view(selection),
        applications=candidates[:10],
    )


def _selection_purpose(intent_name: str) -> Literal["status", "cancel", "modify", "follow_up"]:
    return {
        "status_after_sales": "status",
        "cancel_after_sales": "cancel",
        "modify_after_sales": "modify",
        "follow_up_after_sales": "follow_up",
    }.get(intent_name, "status")


def _candidate_view(application: AfterSalesApplicationView) -> AfterSalesApplicationCandidateView:
    return AfterSalesApplicationCandidateView(
        application_id=application.application_id,
        application_type_label=application.application_type_label,
        status_label=application.status_label,
        product_name=application.product_name,
        created_at=application.created_at,
    )


def _explicit_selected_application(
    candidates: list[AfterSalesApplicationView], message: str
) -> AfterSalesApplicationView | None:
    application_id = _application_id_from_message(message)
    if application_id is None:
        return None
    return next((item for item in candidates if item.application_id == application_id), None)


def _selected_from_pending_selection(
    selection: PendingAfterSalesSelection,
    message: str,
) -> AfterSalesApplicationCandidateView | None:
    application_id = _application_id_from_message(message)
    if application_id is not None:
        return next(
            (
                candidate
                for candidate in selection.candidates
                if candidate.application_id == application_id
            ),
            None,
        )
    match = re.fullmatch(r"(?:第)?\s*([1-9]|10)\s*(?:个|号|项)?", message.strip())
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < len(selection.candidates):
            return selection.candidates[index]
    return None


def _application_id_from_message(message: str) -> int | None:
    # Accept only an explicit customer-visible application reference.  A bare
    # long number may be an order number and must not be treated as an ID.
    match = re.search(r"(?:申请号|售后单|售后申请|#)\s*(\d{1,12})", message)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None


def _looks_like_selection_attempt(message: str) -> bool:
    return bool(
        re.fullmatch(r"(?:第)?\s*\d{1,12}\s*(?:个|号|项)?", message.strip())
        or _application_id_from_message(message) is not None
    )


def _narrative_from_message(
    message: str,
    carried_reason: str | None,
    carried_description: str | None,
) -> tuple[str | None, str | None]:
    """Use only grounded fields from the semantic extractor.

    A later message cannot become a modification merely because it contains a
    familiar keyword. If extraction fails or has no evidence span, the caller
    collects the missing narrative in a server-owned pending draft instead.
    """
    from app.services.after_sales_application_service import _safe_extract

    extraction = _safe_extract(message)
    return (
        carried_reason or extraction.reason,
        carried_description or extraction.description,
    )


def _normalize_modification_for_application(
    application: AfterSalesApplicationView,
    reason: str | None,
    description: str | None,
) -> tuple[str | None, str | None]:
    """Keep accepted applications within Java's supplement-only contract."""
    if application.can_supplement and not application.can_modify:
        return None, description or reason
    return reason, description
