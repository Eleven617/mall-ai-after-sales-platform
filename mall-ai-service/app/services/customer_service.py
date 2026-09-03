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
)
from app.schemas.intent import IntentResponse
from app.schemas.rag import RagSource
from app.schemas.tool import ToolCall
from app.services.answer_service import generate_answer_from_tool_result
from app.services.chat_scope_service import reply_for_chat_scope
from app.services.case_handoff_service import CaseHandoffError, register_case_handoff
from app.services.conversation_state import (
    get_conversation_model_context,
    record_assistant_message,
    record_user_message,
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
    resume_unified_after_sales_task,
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
from app.services.task_orchestration_service import (
    get_task_orchestration_service,
    normalize_turn_plan,
)


def handle_customer_message(
    request: CustomerServiceRequest,
    tool_context: ToolExecutionContext | None = None,
) -> CustomerServiceResponse:
    context = tool_context or ToolExecutionContext()
    conversation_context = get_conversation_model_context(request.session_id)
    record_user_message(request.session_id, request.message)
    # Every message, including one sent while a draft/Proposal exists, first
    # receives a bounded task-aware P0 decision.  There is deliberately no
    # pending-work, durable-checkpoint, or identifier parser before this point.
    try:
        plan = normalize_turn_plan(detect_intent(request.message, conversation_context))
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

    intent = plan.to_intent_response()
    task_runtime = get_task_orchestration_service()
    decision = task_runtime.prepare_turn(
        session_id=request.session_id,
        authorization=context.authorization,
        member_id=context.member_id,
        plan=plan,
    )

    record_trace(
        "task_routing",
        "resolved",
        request.session_id,
        prompt_version=INTENT_PROMPT_VERSION,
        intent=intent.intent,
        route=intent.route,
        task_relation=plan.task_relation,
        task_kind=plan.task_kind,
        confirmation_intent=plan.confirmation_intent,
        rationale_code=plan.rationale_code,
    )

    if decision.clarification:
        return _reply(
            request,
            intent.model_copy(update={"source": "system"}),
            decision.clarification,
        )

    if decision.mode == "transaction_gate":
        gate_result = task_runtime.execute_transaction_gate(
            session_id=request.session_id,
            authorization=context.authorization,
            member_id=context.member_id,
            plan=plan,
        )
        return _reply_from_after_sales_result(request, intent, gate_result)

    if decision.mode == "continue_task":
        active_kind = task_runtime.activate_active_payload(
            session_id=request.session_id,
            authorization=context.authorization,
            member_id=context.member_id,
        )
        if active_kind in {"after_sales_draft", "after_sales_modification"}:
            resumed = resume_unified_after_sales_task(
                session_id=request.session_id,
                message=request.message,
                authorization=context.authorization,
                member_id=context.member_id,
                resume_from_task=True,
            )
            if resumed is not None:
                task_runtime.capture_after_sales_work(
                    session_id=request.session_id,
                    authorization=context.authorization,
                    member_id=context.member_id,
                    pending_question=resumed.answer,
                )
                return _reply_from_after_sales_result(request, intent, resumed)
            # A P0-selected task must not fall through into a brand-new flow
            # when an adapter cannot safely resume it. Keep the server-owned
            # payload and ask for a bounded clarification instead of replacing
            # its fields with the new message.
            task_runtime.capture_after_sales_work(
                session_id=request.session_id,
                authorization=context.authorization,
                member_id=context.member_id,
            )
            return _reply(
                request,
                intent.model_copy(update={"source": "system"}),
                "当前暂存的售后事项还需要你补充已提示的信息；也可以重新说明要办理的内容。",
            )
        if active_kind == "order_diagnosis":
            return _run_task_aware_investigation(
                request=request,
                intent=intent,
                context=context,
                conversation_context=conversation_context,
                task_runtime=task_runtime,
            )

    if intent.route == "ask_missing_info":
        if intent.tool_call:
            # The tool is a server-validated future capability, not a parser
            # that may claim the next arbitrary message.  P0 must relate the
            # later message to this waiting task before the Agent runs again.
            task_runtime.record_waiting_diagnosis(
                session_id=request.session_id,
                authorization=context.authorization,
                member_id=context.member_id,
                pending_tool_call=intent.tool_call,
                answer=intent.reply or "请补充必要信息后继续查询。",
            )
        return _reply(
            request,
            intent,
            intent.reply or "请补充必要信息。",
        )

    if intent.route == "chat":
        # General chat is one structured intent call plus a reviewed local
        # template, not a second unrestricted LLM completion.
        return _reply(request, intent, reply_for_chat_scope(intent.chat_scope))

    if intent.route == "tool_calling":
        if _missing_required_arguments(intent):
            if intent.tool_call:
                task_runtime.record_waiting_diagnosis(
                    session_id=request.session_id,
                    authorization=context.authorization,
                    member_id=context.member_id,
                    pending_tool_call=intent.tool_call,
                    answer=intent.reply or "请补充必要信息后继续查询。",
                )
            return _reply(request, intent, intent.reply or "请补充必要信息。")
        return _execute_tool_call(request, plan, context)

    if intent.route == "rag":
        rag_answer = answer_after_sales_question(request.message)
        if rag_answer.retrieval_unavailable:
            return _reply(
                request,
                intent,
                "售后政策检索服务暂时不可用，暂无法给出可靠结论，请稍后重试或联系人工客服。",
            )
        if (
            rag_answer.evidence_verification_unavailable
            or rag_answer.answer_generation_unavailable
        ):
            return _reply(
                request,
                intent,
                "售后政策证据暂时无法完成核验，暂不提供不可靠的结论，请稍后重试。",
            )
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
        task_runtime.capture_after_sales_work(
            session_id=request.session_id,
            authorization=context.authorization,
            member_id=context.member_id,
            pending_question=after_sales_result.answer,
        )
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
            # P0 has already selected ``order_diagnosis``. This is an evidence
            # threshold inside that read-only subflow, not a fixed identifier
            # parser or a pre-model interrupt.
            requires_order_facts=True,
        )
        agent_result, answer = _settle_investigation_task(
            request=request,
            context=context,
            task_runtime=task_runtime,
            agent_result=agent_result,
        )
        return _reply(
            request,
            intent,
            answer,
            verified_facts=agent_result.verified_facts or None,
            rag_sources=agent_result.policy_sources or None,
            diagnosis=agent_result.diagnosis,
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
    if (
        diagnosis is None
        or diagnosis.handoff is None
        or not diagnosis.verified_facts
        or not authorization
    ):
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


def _run_task_aware_investigation(
    *,
    request: CustomerServiceRequest,
    intent: IntentResponse,
    context: ToolExecutionContext,
    conversation_context: str,
    task_runtime,
) -> CustomerServiceResponse:
    """Run one read-only diagnosis only after P0 selected/recovered the task."""

    agent_result = run_unified_after_sales_investigation(
        session_id=request.session_id,
        message=request.message,
        tool_context=context,
        conversation_context=conversation_context,
        # Missing identifiers become a normal waiting-input task emitted by the
        # Agent; they are no longer a fixed pre-model interrupt.
        # The resumed task is the same P0-selected read-only order diagnosis.
        # Missing facts remain a normal waiting task rather than an interrupt.
        requires_order_facts=True,
    )
    agent_result, answer = _settle_investigation_task(
        request=request,
        context=context,
        task_runtime=task_runtime,
        agent_result=agent_result,
    )
    return _reply(
        request,
        intent,
        answer,
        verified_facts=agent_result.verified_facts or None,
        rag_sources=agent_result.policy_sources or None,
        diagnosis=agent_result.diagnosis,
    )


def _settle_investigation_task(
    *,
    request: CustomerServiceRequest,
    context: ToolExecutionContext,
    task_runtime,
    agent_result,
):
    """Persist only verified diagnosis progress behind a task-aware turn.

    A provider may return an otherwise valid AgentRunResult with zero verified
    facts and no pending read.  That must not complete the P0-selected
    ``order_diagnosis`` task or create an operations handoff.  The normal graph
    now prevents that shape, while this boundary guard keeps a future adapter
    or provider regression fail-closed as ordinary waiting input.
    """

    if _is_unverified_order_diagnosis(agent_result):
        agent_result = agent_result.model_copy(
            update={
                "answer": "请提供订单号；收到后我会继续完成订单与物流核验。",
                "pending_tool_call": ToolCall(name="order_service", arguments={}),
                "diagnosis": DiagnosisResult(
                    category="needs_order_identifier",
                    evidence_status="partial",
                    allowed_next_steps=["provide_order_sn"],
                ),
                "policy_sources": [],
            }
        )
        record_trace(
            "analysis_agent",
            "unverified_diagnosis_held",
            request.session_id,
            result_kind="pending",
            diagnosis_category="needs_order_identifier",
            evidence_status="partial",
            handoff=False,
        )

    answer = _register_diagnosis_handoff_if_needed(
        request=request,
        diagnosis=agent_result.diagnosis,
        authorization=context.authorization,
        answer=agent_result.answer,
    )
    if agent_result.pending_tool_call is not None:
        task_runtime.record_waiting_diagnosis(
            session_id=request.session_id,
            authorization=context.authorization,
            member_id=context.member_id,
            pending_tool_call=agent_result.pending_tool_call,
            answer=answer,
        )
    else:
        task_runtime.complete_active_task(
            session_id=request.session_id,
            authorization=context.authorization,
            member_id=context.member_id,
        )
    return agent_result, answer


def _is_unverified_order_diagnosis(agent_result) -> bool:
    """Detect only an internally inconsistent result from the selected flow.

    This predicate does not examine customer text or infer an intent.  It is
    reached solely after the task-aware P0 selected the read-only
    ``order_diagnosis`` route.
    """

    diagnosis = agent_result.diagnosis
    return (
        agent_result.pending_tool_call is None
        and not agent_result.verified_facts
        and diagnosis is not None
        and diagnosis.category
        in {"needs_order_identifier", "facts_incomplete", "policy_insufficient"}
    )


def _execute_tool_call(
    request: CustomerServiceRequest,
    plan,
    tool_context: ToolExecutionContext,
) -> CustomerServiceResponse:
    intent = plan.to_intent_response()
    if not intent.tool_call:
        return _reply(request, intent, "当前问题缺少要调用的工具。")

    try:
        skill_id = select_customer_skill(plan=plan)
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
    diagnosis: DiagnosisResult | None = None,
) -> CustomerServiceResponse:
    task_state = get_task_orchestration_service().current_public_state(request.session_id)
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
        diagnosis=diagnosis,
        task=task_state if task_state.task_status != "none" else None,
    )
    record_assistant_message(request.session_id, response.answer)
    return response
