from app.schemas.agent import VerifiedFactCard
from app.schemas.after_sales_application import (
    AfterSalesActionKind,
    AfterSalesApplicationView,
    AfterSalesDraftView,
    AfterSalesEligibilityView,
    AfterSalesFlowResult,
    AfterSalesPendingActionView,
    AfterSalesProposalView,
    AfterSalesSelectionView,
)
from app.schemas.diagnosis import DiagnosisResult
from app.schemas.customer_service import (
    CustomerServiceRequest,
    CustomerServiceResponse,
    PendingActionView,
)
from app.schemas.intent import IntentResponse
from app.schemas.rag import RagSource
from app.services.agent_service import (
    resume_durable_diagnosis_result,
)
from app.services.after_sales_application_state import has_pending_after_sales_work
from app.services.answer_service import generate_answer_from_tool_result
from app.services.chat_scope_service import reply_for_chat_scope
from app.services.case_handoff_service import CaseHandoffError, register_case_handoff
from app.services.conversation_state import (
    cancel_pending_tool_call,
    get_conversation_model_context,
    record_assistant_message,
    record_user_message,
    resolve_pending_tool_call,
    save_pending_tool_call,
)
from app.services.intent_service import (
    INTENT_PROMPT_VERSION,
    IntentServiceError,
    detect_intent,
)
from app.services.mall_client import MallApiClientError
from app.services.rag_service import answer_after_sales_question
from app.services.unified_after_sales_graph import (
    run_unified_after_sales_graph,
    run_unified_after_sales_investigation,
)
from app.services.tool_context import ToolExecutionContext
from app.services.tool_registry import (
    ToolAccessDeniedError,
    ToolInputError,
    ToolNotFoundError,
    call_tool,
    get_missing_required_field,
)
from app.services.skill_catalog import SkillPolicyError, select_customer_skill
from app.services.fact_presentation_service import build_verified_facts
from app.services.trace_service import record_trace


def handle_customer_message(
    request: CustomerServiceRequest,
    tool_context: ToolExecutionContext | None = None,
) -> CustomerServiceResponse:
    context = tool_context or ToolExecutionContext()
    conversation_context = get_conversation_model_context(request.session_id)
    record_user_message(request.session_id, request.message)
    # Pending unified work is resumed before LLM routing.  A bare “确认” or a
    # selected application number therefore never relies on the model to
    # rediscover an internal target, and no old return-flow can handle it.
    # Resume only server-persisted after-sales work.  A fresh natural-language
    # request must never enter the graph before the structured intent model has
    # chosen a bounded action.  This also guarantees that a model outage cannot
    # cause RAG, Java tools, or a write-capable workflow to run for a new input.
    if has_pending_after_sales_work(request.session_id):
        pending_after_sales_result = run_unified_after_sales_graph(
            session_id=request.session_id,
            message=request.message,
            authorization=context.authorization,
            member_id=context.member_id,
            intent_name="resume_pending",
            resume_only=True,
        )
        if pending_after_sales_result is not None:
            after_sales_intent = IntentResponse(
                intent="apply_after_sales",
                route="after_sales_flow",
                need_tool=False,
                source="system",
            )
            return _reply_from_after_sales_result(request, after_sales_intent, pending_after_sales_result)

    # Build 21 checks an owner-bound, sanitized LangGraph checkpoint before
    # generic pending-tool state or a new LLM route.  A resumed identifier is
    # consumed only by the already-authorized read-only diagnostic tool.
    durable_diagnosis = resume_durable_diagnosis_result(
        session_id=request.session_id,
        message=request.message,
        tool_context=context,
    )
    if durable_diagnosis is not None:
        return _reply_from_durable_diagnosis_resume(
            request,
            durable_diagnosis,
        )

    cancelled_tool_call = cancel_pending_tool_call(
        request.session_id,
        request.message,
    )
    if cancelled_tool_call is not None:
        intent = IntentResponse(
            intent="continue_tool_call",
            route="chat",
            need_tool=False,
            source="system",
        )
        return _reply(
            request,
            intent,
            f"已取消{_pending_tool_label(cancelled_tool_call.name)}，未执行任何查询。",
        )

    pending_tool_resolution = resolve_pending_tool_call(
        request.session_id,
        request.message,
    )
    if pending_tool_resolution.clarification:
        intent = IntentResponse(
            intent="continue_tool_call",
            route="ask_missing_info",
            need_tool=False,
            # This is the already-authorized, still-pending read-only tool.
            # It is recorded for the client but not executed until a single
            # valid identifier is supplied.
            tool_call=_intent_tool_call_payload(pending_tool_resolution.tool_call),
            source="system",
        )
        return _reply(
            request,
            intent,
            pending_tool_resolution.clarification,
            pending_action=_pending_action_from_tool_call(
                pending_tool_resolution.tool_call
            ),
        )

    if pending_tool_resolution.tool_call:
        intent = IntentResponse(
            intent="continue_tool_call",
            route="tool_calling",
            need_tool=True,
            tool_call=_intent_tool_call_payload(pending_tool_resolution.tool_call),
        )
        return _execute_tool_call(request, intent, context)

    # Every new natural-language request gets one bounded structured intent
    # decision.  Server code later enforces the resulting closed route contract;
    # it never substitutes keyword guesses when the model is unavailable.
    try:
        intent = detect_intent(request.message, conversation_context)
    except IntentServiceError:
        record_trace(
            "intent_routing",
            "model_unavailable",
            request.session_id,
            prompt_version=INTENT_PROMPT_VERSION,
        )
        fallback_intent = IntentResponse(
            intent="unknown",
            route="chat",
            need_tool=False,
            source="system",
        )
        return _reply(
            request,
            fallback_intent,
            "智能客服暂不可用，请稍后重试或联系人工客服。",
        )

    record_trace(
        "intent_routing",
        "resolved",
        request.session_id,
        prompt_version=INTENT_PROMPT_VERSION,
        intent=intent.intent,
        route=intent.route,
    )

    if intent.route == "ask_missing_info":
        if intent.tool_call:
            save_pending_tool_call(request.session_id, intent.tool_call)
        return _reply(
            request,
            intent,
            intent.reply or "请补充必要信息。",
            pending_action=_pending_action_from_tool_call(intent.tool_call),
        )

    if intent.route == "chat":
        # General chat is one structured intent call plus a reviewed local
        # template, not a second unrestricted LLM completion.
        return _reply(request, intent, reply_for_chat_scope(intent.chat_scope))

    if intent.route == "tool_calling":
        return _handle_tool_calling(request, intent, context)

    if intent.route == "rag":
        rag_answer = answer_after_sales_question(request.message)
        return _reply(
            request,
            intent,
            rag_answer.answer,
            rag_context=rag_answer.retrieved_context,
            rag_sources=rag_answer.sources,
        )

    if intent.route == "after_sales_flow":
        after_sales_result = run_unified_after_sales_graph(
            session_id=request.session_id,
            message=request.message,
            authorization=context.authorization,
            member_id=context.member_id,
            intent_name=intent.intent,
        )
        if after_sales_result is None:
            return _reply(request, intent, "暂时无法恢复售后流程，请重新描述你的需求。")
        return _reply_from_after_sales_result(request, intent, after_sales_result)

    if intent.route == "agent":
        # The existing bounded ReAct graph is now a read-only subflow of the
        # unified after-sales graph, rather than a parallel customer entry.
        # The route is still selected by the structured intent model; this
        # server branch does not infer an intent from keywords.
        agent_result = run_unified_after_sales_investigation(
            session_id=request.session_id,
            message=request.message,
            tool_context=context,
            conversation_context=conversation_context,
            require_order_identifier=True,
        )
        answer = _register_diagnosis_handoff_if_needed(
            request=request,
            diagnosis=agent_result.diagnosis,
            authorization=context.authorization,
            answer=agent_result.answer,
        )
        if (
            agent_result.pending_tool_call is not None
            and not agent_result.durable_checkpoint_pending
        ):
            save_pending_tool_call(request.session_id, agent_result.pending_tool_call)
        return _reply(
            request,
            intent,
            answer,
            verified_facts=agent_result.verified_facts or None,
            rag_sources=agent_result.policy_sources or None,
            diagnosis=agent_result.diagnosis,
            pending_action=_pending_action_from_tool_call(
                agent_result.pending_tool_call,
                resumable=agent_result.durable_checkpoint_pending,
            ),
        )

    return _reply(request, intent, "暂时无法判断你的问题，请换一种说法。")


def _register_diagnosis_handoff_if_needed(
    *,
    request: CustomerServiceRequest,
    diagnosis: DiagnosisResult | None,
    authorization: str | None,
    answer: str,
) -> str:
    """Persist only existing safe handoffs; keep every internal detail private."""
    if diagnosis is None or diagnosis.handoff is None or not authorization:
        return answer
    try:
        register_case_handoff(
            session_id=request.session_id,
            diagnosis=diagnosis,
            authorization=authorization,
        )
    except CaseHandoffError:
        record_trace(
            "case_handoff",
            "persistence_unavailable",
            request.session_id,
            handoff=True,
            diagnosis_category=diagnosis.category,
            evidence_status=diagnosis.evidence_status,
        )
        return "当前已识别到需要人工跟进，但暂时无法登记，请稍后重试或联系客服。"
    record_trace(
        "case_handoff",
        "persisted",
        request.session_id,
        handoff=True,
        diagnosis_category=diagnosis.category,
        evidence_status=diagnosis.evidence_status,
    )
    return "已为你登记人工跟进。处理人员会依据业务系统进一步核实；如有紧急情况，请直接联系商城客服。"


def _handle_tool_calling(
    request: CustomerServiceRequest,
    intent: IntentResponse,
    tool_context: ToolExecutionContext,
) -> CustomerServiceResponse:
    if not intent.tool_call:
        return _reply(request, intent, "当前问题缺少要调用的工具。")

    if _missing_required_arguments(intent):
        save_pending_tool_call(request.session_id, intent.tool_call)
        return _reply(
            request,
            intent,
            intent.reply or "请补充必要信息。",
            pending_action=_pending_action_from_tool_call(intent.tool_call),
        )

    return _execute_tool_call(request, intent, tool_context)


def _execute_tool_call(
    request: CustomerServiceRequest,
    intent: IntentResponse,
    tool_context: ToolExecutionContext,
) -> CustomerServiceResponse:
    if not intent.tool_call:
        return _reply(request, intent, "当前问题缺少要调用的工具。")

    try:
        skill_id = select_customer_skill(
            intent_name=intent.intent,
            route=intent.route,
            tool_name=intent.tool_call.name,
        )
        result = call_tool(intent.tool_call, tool_context.for_skill(skill_id))
    except SkillPolicyError:
        return _reply(request, intent, "当前受控能力暂不可执行该查询。")
    except ToolAccessDeniedError:
        return _reply(request, intent, "当前受控能力不允许执行该查询。")
    except ToolNotFoundError:
        return _reply(request, intent, "当前工具暂未实现。")
    except ToolInputError:
        return _reply(request, intent, "查询参数不完整或格式不正确，请补充后再试。")
    except MallApiClientError as exc:
        return _reply(request, intent, str(exc))

    answer = generate_answer_from_tool_result(request.message, intent, result)
    return _reply(
        request,
        intent,
        answer,
        result,
        verified_facts=build_verified_facts([(intent.tool_call.name, result)]),
    )


def _missing_required_arguments(intent: IntentResponse) -> bool:
    if intent.tool_call is None:
        return True
    return get_missing_required_field(intent.tool_call) is not None


def _intent_tool_call_payload(tool_call: object) -> dict | None:
    """Adapt durable ToolCall state to the stricter IntentToolCall schema."""
    if tool_call is None:
        return None
    model_dump = getattr(tool_call, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return tool_call if isinstance(tool_call, dict) else None


def _pending_action_from_tool_call(
    tool_call: object,
    *,
    resumable: bool = False,
) -> PendingActionView | None:
    """Expose only the waiting state and a fixed cancellation action to Vue."""
    tool_name = getattr(tool_call, "name", None)
    if tool_name in {"order_service", "logistics_service"}:
        return PendingActionView(
            kind="awaiting_order_sn",
            label="正在等待订单号",
            resumable=resumable,
        )
    if tool_name == "inventory_service":
        return PendingActionView(
            kind="awaiting_sku_id",
            label="正在等待 SKU 编码",
            resumable=resumable,
        )
    return None


def _pending_tool_label(tool_name: str) -> str:
    """Use a stable human label in the explicit pending-query cancellation reply."""
    return {
        "order_service": "订单查询",
        "logistics_service": "物流查询",
        "inventory_service": "库存查询",
    }.get(tool_name, "当前查询")


def _reply_from_durable_diagnosis_resume(
    request: CustomerServiceRequest,
    result: object,
) -> CustomerServiceResponse:
    """Project a safe checkpoint outcome without exposing its thread or payload."""
    status = getattr(result, "status", "unavailable")
    answer = getattr(result, "answer", None) or "诊断恢复未完成，请稍后重试。"
    tool_call = getattr(result, "tool_call", None)
    tool_result = getattr(result, "tool_result", None)
    tool_results = getattr(result, "tool_results", None) or []
    diagnosis = getattr(result, "diagnosis", None)

    if status == "awaiting_input" and tool_call is not None:
        intent = IntentResponse(
            intent="continue_tool_call",
            route="ask_missing_info",
            need_tool=False,
            tool_call=_intent_tool_call_payload(tool_call),
            source="system",
        )
        return _reply(
            request,
            intent,
            answer,
            pending_action=_pending_action_from_tool_call(tool_call, resumable=True),
        )

    if status == "resumed" and tool_call is not None and isinstance(tool_result, dict):
        intent = IntentResponse(
            intent="continue_tool_call",
            route="tool_calling",
            need_tool=True,
            tool_call=_intent_tool_call_payload(tool_call),
            source="system",
        )
        safe_results = [
            (call.name, payload)
            for call, payload in tool_results
            if getattr(call, "name", None) and isinstance(payload, dict)
        ]
        return _reply(
            request,
            intent,
            answer
            if safe_results and answer != "诊断恢复未完成，请稍后重试。"
            else generate_answer_from_tool_result(request.message, intent, tool_result),
            tool_result=tool_result,
            verified_facts=build_verified_facts(safe_results or [(tool_call.name, tool_result)]),
            diagnosis=diagnosis,
        )

    intent = IntentResponse(
        intent="continue_tool_call",
        route="chat",
        need_tool=False,
        source="system",
    )
    return _reply(request, intent, answer)


def _reply_from_after_sales_result(
    request: CustomerServiceRequest,
    intent: IntentResponse,
    result: AfterSalesFlowResult,
) -> CustomerServiceResponse:
    """Project one unified graph result through the existing internal DTO."""
    return _reply(
        request,
        intent,
        result.answer,
        rag_sources=result.policy_sources,
        after_sales_draft=result.draft,
        after_sales_proposal=result.proposal,
        after_sales_eligibility=result.eligibility,
        submitted_after_sales_application=result.submitted_application,
        after_sales_completed_action=result.completed_action,
        after_sales_pending_action=result.pending_action,
        after_sales_selection=result.selection,
        after_sales_applications=result.applications,
    )


def _reply(
    request: CustomerServiceRequest,
    intent: IntentResponse,
    answer: str,
    tool_result: dict | None = None,
    verified_facts: list[VerifiedFactCard] | None = None,
    rag_context: list[str] | None = None,
    rag_sources: list[RagSource] | None = None,
    after_sales_draft: AfterSalesDraftView | None = None,
    after_sales_proposal: AfterSalesProposalView | None = None,
    after_sales_eligibility: AfterSalesEligibilityView | None = None,
    submitted_after_sales_application: AfterSalesApplicationView | None = None,
    after_sales_completed_action: AfterSalesActionKind | None = None,
    after_sales_pending_action: AfterSalesPendingActionView | None = None,
    after_sales_selection: AfterSalesSelectionView | None = None,
    after_sales_applications: list[AfterSalesApplicationView] | None = None,
    pending_action: PendingActionView | None = None,
    diagnosis: DiagnosisResult | None = None,
) -> CustomerServiceResponse:
    response = CustomerServiceResponse(
        message=request.message,
        answer=answer,
        intent=intent,
        tool_result=tool_result,
        verified_facts=verified_facts,
        rag_context=rag_context,
        rag_sources=rag_sources,
        after_sales_draft=after_sales_draft,
        after_sales_proposal=after_sales_proposal,
        after_sales_eligibility=after_sales_eligibility,
        submitted_after_sales_application=submitted_after_sales_application,
        after_sales_completed_action=after_sales_completed_action,
        after_sales_pending_action=after_sales_pending_action,
        after_sales_selection=after_sales_selection,
        after_sales_applications=after_sales_applications,
        pending_action=pending_action,
        diagnosis=diagnosis,
    )
    record_assistant_message(request.session_id, response.answer)
    return response
