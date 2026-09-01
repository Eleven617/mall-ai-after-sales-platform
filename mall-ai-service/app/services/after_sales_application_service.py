"""One semantic, stateful flow for the supported after-sales application types.

The LLM may identify the customer's goal and grounded text spans. It never
chooses an internal item ID, decides factual eligibility, or writes business
data. Java owns all of those decisions; RAG is used only to explain policy
evidence before a proposal is shown.
"""
import hashlib
import time
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.after_sales_application import (
    AfterSalesApplicationView,
    AfterSalesApplicationType,
    AfterSalesDraftField,
    AfterSalesEligibilityView,
    AfterSalesFlowResult,
    AfterSalesPendingActionView,
    AfterSalesProductOption,
    AfterSalesRequestCandidateExtraction,
    AfterSalesRequestExtraction,
    PendingAfterSalesAction,
    PendingAfterSalesDraft,
    PendingAfterSalesModificationDraft,
    PendingAfterSalesProposal,
)
from app.services.after_sales_application_state import (
    AfterSalesPendingStateError,
    PENDING_AFTER_SALES_DRAFT_TTL_SECONDS,
    PENDING_AFTER_SALES_ACTION_TTL_SECONDS,
    PENDING_AFTER_SALES_PROPOSAL_TTL_SECONDS,
    application_type_label,
    cancel_pending_after_sales_proposal,
    clear_pending_after_sales_draft,
    complete_pending_after_sales_proposal,
    complete_pending_after_sales_action,
    complete_pending_after_sales_modification_draft,
    get_pending_after_sales_action,
    get_pending_after_sales_draft,
    get_pending_after_sales_modification_draft,
    get_pending_after_sales_proposal,
    mark_pending_after_sales_action_retryable,
    mark_pending_after_sales_action_unknown,
    mark_pending_after_sales_submission_retryable,
    mark_pending_after_sales_submission_unknown,
    owner_fingerprint,
    save_pending_after_sales_draft,
    save_pending_after_sales_action,
    save_active_after_sales_application,
    save_pending_after_sales_modification_draft,
    save_pending_after_sales_proposal,
    session_fingerprint,
    to_after_sales_draft_view,
    to_after_sales_pending_action_view,
    to_after_sales_proposal_view,
)
from app.services.conversation_state import remember_conversation_facts
from app.services.identifier_extraction import IdentifierResolution, extract_order_sn
from app.services.llm_service import LLMServiceError, generate_json
from app.services.mall_client import (
    MallAfterSalesSubmissionUnknownError,
    MallAfterSalesActionUnknownError,
    MallApiClientError,
    check_after_sales_eligibility,
    create_after_sales_application,
    execute_after_sales_action,
    get_after_sales_action_status,
    get_after_sales_submission_status,
    get_order_snapshot,
)
from app.services.rag_service import answer_after_sales_question
from app.services.structured_output_gateway import (
    StructuredOutputError,
    StructuredOutputMode,
    generate_structured_output_with_correction,
)
from app.services.trace_service import record_trace


AFTER_SALES_EXTRACTION_SYSTEM_PROMPT = """
You extract one ecommerce after-sales task from exactly one customer message.
Return one JSON object only. Every field must be null or an object with both
`value` and `evidence_span`; `evidence_span` must be an exact contiguous quote
from the customer message. Never invent a quote or an internal identifier.

Schema:
{
  "goal": {"value": "eligibility | apply", "evidence_span": "quoted user text"} | null,
  "application_type": {"value": "cancel_refund | return_refund | exchange | repair", "evidence_span": "quoted user text"} | null,
  "order_sn": {"value": "customer-visible order number", "evidence_span": "quoted user text"} | null,
  "product_hint": {"value": "short product name, color, or specification", "evidence_span": "quoted user text"} | null,
  "reason": {"value": "short customer reason", "evidence_span": "quoted user text"} | null,
  "description": {"value": "short issue detail", "evidence_span": "quoted user text"} | null
}

Interpretation rules:
- Questions such as 能不能、是否符合、可以吗 are goal=eligibility.
- Direct execution wording such as 申请、提交、帮我办理 is goal=apply.
- 未发货取消、取消订单退款 map to cancel_refund.
- 退货退款、退款退货 map to return_refund.
- 换货、换一个、发错货需要替换 map to exchange.
- 维修、质保、保修、故障送修 map to repair.
- Do not choose an application_type when the message only says 售后 and no
  supported type is clear.
- Never output user ID, order-item ID, price, policy conclusion, or order status.
""".strip()

CONFIRM_MESSAGES = {"确认", "确认提交", "确认申请", "提交申请", "确认办理"}
CANCEL_MESSAGES = {"取消", "取消申请", "不申请了", "暂不办理"}


class AfterSalesApplicationError(RuntimeError):
    pass


def extract_after_sales_request(message: str) -> AfterSalesRequestExtraction:
    """Accept only semantic values supported by the exact customer message."""
    try:
        result = generate_structured_output_with_correction(
            message=message,
            system_prompt=AFTER_SALES_EXTRACTION_SYSTEM_PROMPT,
            response_model=AfterSalesRequestCandidateExtraction,
            mode=StructuredOutputMode.PROMPT_JSON,
            temperature=0,
            json_generator=generate_json,
            validate_result=_validate_extraction_contract,
            correction_message=(
                "重新提取同一条消息中的售后字段；每个非空字段必须带原话中的连续 evidence_span，"
                "不确定时返回 null。"
            ),
            correction_context={
                "output_fields": [
                    "goal",
                    "application_type",
                    "order_sn",
                    "product_hint",
                    "reason",
                    "description",
                ],
                "schema_version": "v1",
            },
        )
        candidates = result.value
    except (LLMServiceError, StructuredOutputError, ValidationError, TypeError, ValueError) as exc:
        raise AfterSalesApplicationError("暂时无法识别售后任务，请换一种说法后重试。") from exc

    order_resolution = extract_order_sn(message)
    return AfterSalesRequestExtraction(
        goal=_grounded_enum(candidates.goal, message, {"eligibility", "apply"}),
        application_type=_grounded_enum(
            candidates.application_type,
            message,
            {"cancel_refund", "return_refund", "exchange", "repair"},
        ),
        order_sn=order_resolution.value,
        product_hint=_grounded_span(candidates.product_hint, message, 200),
        reason=_grounded_span(candidates.reason, message, 100),
        description=_grounded_span(candidates.description, message, 500),
    )


def start_after_sales_flow(
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None = None,
) -> AfterSalesFlowResult:
    """Start a generic draft. Existing work is always resumed first."""
    pending = handle_pending_after_sales_draft(session_id, message, authorization, member_id)
    if pending is not None:
        return pending
    try:
        fingerprint = owner_fingerprint(authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))

    resolution = extract_order_sn(message)
    extraction = _safe_extract(message)
    draft = PendingAfterSalesDraft(
        draft_id=uuid4().hex,
        owner_fingerprint=fingerprint,
        order_sn=resolution.value,
        expires_at=time.time() + PENDING_AFTER_SALES_DRAFT_TTL_SECONDS,
    )
    _merge_message_into_draft(draft, message, resolution.value, extraction)
    save_pending_after_sales_draft(session_id, draft)
    record_trace(
        "after_sales_workflow",
        "draft_started",
        session_id,
        goal=draft.goal,
        application_type=draft.application_type,
        has_order=bool(draft.order_sn),
    )
    if resolution.ambiguous:
        return _draft_result(
            draft,
            "检测到多个可能的订单编号，请明确回复“订单号：xxxxxxxx”。",
        )
    return _advance_draft(session_id, draft, message, authorization, member_id)


def handle_pending_after_sales_draft(
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None = None,
) -> AfterSalesFlowResult | None:
    try:
        draft = get_pending_after_sales_draft(session_id, authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    if draft is None:
        return None

    normalized = _normalize_message(message)
    if normalized in CANCEL_MESSAGES:
        clear_pending_after_sales_draft(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "draft_cancelled", session_id)
        return AfterSalesFlowResult(answer="已取消本次售后信息收集，尚未提交任何申请。")

    resolution = extract_order_sn(message)
    extraction = _safe_extract(message)
    if not _is_draft_follow_up(draft, message, resolution, extraction):
        record_trace("after_sales_workflow", "draft_paused_for_unrelated_message", session_id)
        return None
    if resolution.ambiguous:
        return _draft_result(
            draft,
            "检测到多个可能的订单编号，请明确回复“订单号：xxxxxxxx”。",
        )

    old_order = draft.order_sn
    _merge_message_into_draft(draft, message, resolution.value, extraction)
    if resolution.value and resolution.value != old_order:
        draft.product_hint = extraction.product_hint
        draft.product_options = []
    draft.updated_at = time.time()
    save_pending_after_sales_draft(session_id, draft)
    record_trace(
        "after_sales_workflow",
        "draft_updated",
        session_id,
        goal=draft.goal,
        application_type=draft.application_type,
        has_order=bool(draft.order_sn),
    )
    return _advance_draft(session_id, draft, message, authorization, member_id)


def handle_pending_after_sales_confirmation(
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None = None,
) -> AfterSalesFlowResult | None:
    try:
        proposal = get_pending_after_sales_proposal(session_id, authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    if proposal is None:
        return None

    normalized = _normalize_message(message)
    if proposal.submission_state == "submission_unknown":
        if normalized not in CONFIRM_MESSAGES:
            return AfterSalesFlowResult(
                answer="上一次售后提交结果仍待核实，请回复“确认”继续查询。",
                proposal=to_after_sales_proposal_view(proposal),
            )
        return _recover_submission(session_id, proposal, authorization, member_id)

    if normalized not in CONFIRM_MESSAGES | CANCEL_MESSAGES:
        return AfterSalesFlowResult(
            answer="当前已有待确认的售后方案，请回复“确认”提交，或回复“取消”放弃。",
            proposal=to_after_sales_proposal_view(proposal),
        )
    if normalized in CANCEL_MESSAGES:
        cancel_pending_after_sales_proposal(session_id, authorization, member_id)
        return AfterSalesFlowResult(answer="已取消本次售后申请，尚未提交任何记录。")

    try:
        submitted = create_after_sales_application(
            order_sn=proposal.order_sn,
            application_type=proposal.application_type,
            order_item_id=proposal.order_item_id,
            reason=proposal.reason,
            description=proposal.description,
            idempotency_key=proposal.proposal_id,
            authorization=authorization,
        )
    except MallAfterSalesSubmissionUnknownError:
        unknown = mark_pending_after_sales_submission_unknown(
            session_id, authorization, member_id
        )
        record_trace("after_sales_workflow", "java_write_result_unknown", session_id)
        if unknown is None:
            return AfterSalesFlowResult(answer="售后方案已过期，请重新发起申请。")
        return _recover_submission(session_id, unknown, authorization, member_id)
    except MallApiClientError as exc:
        complete_pending_after_sales_proposal(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "java_write_failed", session_id)
        return AfterSalesFlowResult(answer=f"售后申请未完成：{exc}。请重新发起申请。")

    complete_pending_after_sales_proposal(session_id, authorization, member_id)
    try:
        save_active_after_sales_application(
            session_id, authorization, member_id, submitted.application_id
        )
    except AfterSalesPendingStateError:
        # The Java write has already succeeded.  Losing a local convenience
        # reference must not misreport that durable business result.
        pass
    record_trace("after_sales_workflow", "application_submitted", session_id)
    return _submitted_result(submitted)


def _recover_submission(
    session_id: str,
    proposal: PendingAfterSalesProposal,
    authorization: str | None,
    member_id: int | None,
) -> AfterSalesFlowResult:
    try:
        status, submitted = get_after_sales_submission_status(
            proposal.proposal_id, authorization
        )
    except MallApiClientError:
        return AfterSalesFlowResult(
            answer="售后申请的提交结果暂时无法确认，请稍后回复“确认”继续核实。",
            proposal=to_after_sales_proposal_view(proposal),
        )
    if status == "created" and submitted is not None:
        complete_pending_after_sales_proposal(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "submission_recovered", session_id)
        return _submitted_result(submitted)
    retryable = mark_pending_after_sales_submission_retryable(
        session_id, authorization, member_id
    ) or proposal
    return AfterSalesFlowResult(
        answer="尚未确认到提交结果，原售后方案已保留。请回复“确认”安全重试。",
        proposal=to_after_sales_proposal_view(retryable),
    )


def _advance_draft(
    session_id: str,
    draft: PendingAfterSalesDraft,
    message: str,
    authorization: str | None,
    member_id: int | None,
) -> AfterSalesFlowResult:
    if draft.goal is None:
        return _draft_result(
            draft,
            "请说明你是想先核验售后资格，还是准备提交售后申请。",
        )
    if draft.application_type is None:
        return _draft_result(
            draft,
            "请说明要办理哪类售后：取消退款、退货退款、换货或维修/质保。",
        )
    if not draft.order_sn:
        return _draft_result(draft, "请提供订单号，我会先核验当前账号下的真实订单状态。")

    type_requires_product = _product_required(draft.application_type)
    snapshot: dict | None = None
    selected_item: dict | None = None
    if type_requires_product:
        try:
            snapshot = get_order_snapshot(draft.order_sn, authorization)
        except MallApiClientError as exc:
            return _draft_result(
                draft,
                f"{exc} 请核对后回复“订单号：xxxxxxxx”。",
                explicit_missing=["order_sn"],
            )
        selected_item = _select_order_item(snapshot.get("order_items", []), draft.product_hint)
        if selected_item is None:
            options = _to_product_options(snapshot.get("order_items", []))
            if not options:
                clear_pending_after_sales_draft(session_id, authorization, member_id)
                return AfterSalesFlowResult(
                    answer="该订单没有可用于售后申请的商品信息，请联系人工客服。"
                )
            draft.product_options = options
            save_pending_after_sales_draft(session_id, draft)
            return _draft_result(
                draft,
                f"该订单有多个商品，请说明要处理哪一个：{'、'.join(_format_option(x) for x in options)}。",
                explicit_missing=["product"],
            )
        draft.product_options = []

    if draft.goal == "apply" and not draft.reason:
        save_pending_after_sales_draft(session_id, draft)
        return _draft_result(
            draft,
            "请说明售后原因，例如商品损坏、错发、与描述不符或不想要了。",
            explicit_missing=["reason"],
        )

    item_id = _item_id(selected_item)
    try:
        eligibility = check_after_sales_eligibility(
            draft.order_sn,
            draft.application_type,
            authorization,
            order_item_id=item_id,
        )
    except MallApiClientError as exc:
        return _draft_result(draft, f"{exc} 请稍后重试。")

    if eligibility.requires_product_selection:
        # Java is authoritative; if the order changed between snapshot and
        # eligibility it safely asks the user to start the product choice again.
        draft.product_hint = None
        draft.product_options = _to_product_options((snapshot or {}).get("order_items", []))
        save_pending_after_sales_draft(session_id, draft)
        return _draft_result(draft, eligibility.message, explicit_missing=["product"])
    if not eligibility.eligible:
        clear_pending_after_sales_draft(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "eligibility_blocked", session_id)
        return AfterSalesFlowResult(answer=eligibility.message, eligibility=eligibility)

    policy = answer_after_sales_question(_build_policy_query(draft, selected_item))
    if policy.retrieval_unavailable:
        return _draft_result(
            draft,
            "已核验订单状态，但售后政策检索服务暂时不可用，未生成任何售后方案。请稍后重试。",
        )
    if policy.evidence_verification_unavailable or policy.answer_generation_unavailable:
        return _draft_result(
            draft,
            "已核验订单状态，但政策证据暂时无法完成核验，未生成任何售后方案。请稍后重试。",
        )
    if policy.no_evidence or not policy.sources:
        clear_pending_after_sales_draft(session_id, authorization, member_id)
        return AfterSalesFlowResult(
            answer="已核验订单状态，但知识库没有足够政策依据确认该售后方案，建议联系人工客服。",
            eligibility=eligibility,
            policy_sources=policy.sources,
        )

    if draft.goal == "eligibility":
        clear_pending_after_sales_draft(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "eligibility_explained", session_id)
        return AfterSalesFlowResult(
            answer=f"{eligibility.message}\n政策说明：{policy.answer}",
            eligibility=eligibility,
            policy_sources=policy.sources,
        )

    product_name = (
        str(selected_item.get("product_name") or "商品")
        if selected_item is not None
        else "整笔订单"
    )
    # Both fields below originate from a grounded extraction. When the model
    # provided only a reason, reuse that already-grounded text as the short
    # description instead of silently turning a later unrelated message into
    # mutable application content.
    proposal = PendingAfterSalesProposal(
        proposal_id=uuid4().hex,
        application_type=draft.application_type,
        order_sn=eligibility.order_sn,
        order_item_id=item_id,
        product_name=product_name,
        product_attr=_optional_text(selected_item.get("product_attr")) if selected_item else None,
        reason=draft.reason.strip()[:100],
        description=(draft.description or draft.reason).strip()[:500],
        owner_fingerprint=draft.owner_fingerprint,
        session_fingerprint=session_fingerprint(session_id),
        content_hash=_create_proposal_hash(
            order_sn=eligibility.order_sn,
            application_type=draft.application_type,
            order_item_id=item_id,
            reason=draft.reason.strip()[:100],
            description=(draft.description or draft.reason).strip()[:500],
        ),
        expires_at=time.time() + PENDING_AFTER_SALES_PROPOSAL_TTL_SECONDS,
    )
    save_pending_after_sales_proposal(session_id, proposal)
    remember_conversation_facts(
        session_id,
        order_sn=proposal.order_sn,
        product_hint=proposal.product_name,
        after_sales_type=proposal.application_type,
    )
    record_trace(
        "after_sales_workflow",
        "proposal_created",
        session_id,
        application_type=proposal.application_type,
        policy_source_count=len(policy.sources),
    )
    return AfterSalesFlowResult(
        answer=(
            f"{eligibility.message}\n政策说明：{policy.answer}\n"
            f"已生成“{application_type_label(proposal.application_type)}”方案，"
            "请回复“确认”提交，或回复“取消”放弃。"
        ),
        proposal=to_after_sales_proposal_view(proposal),
        eligibility=eligibility,
        policy_sources=policy.sources,
    )


def _submitted_result(application) -> AfterSalesFlowResult:
    return AfterSalesFlowResult(
        answer=(
            f"{application.application_type_label}申请已提交，当前状态为“{application.status_label}”。"
            "这表示申请已进入商城业务系统；退款、换货、维修等后续结果仍以审核和实际履约为准。"
        ),
        submitted_application=application,
        completed_action="create",
    )


def prepare_after_sales_action(
    *,
    session_id: str,
    authorization: str | None,
    member_id: int | None,
    application: AfterSalesApplicationView,
    action: str,
    reason: str | None = None,
    description: str | None = None,
) -> AfterSalesFlowResult:
    """Create an owner/session-bound confirmation for one non-create write.

    ``application`` must be a server-derived, current-member projection.  The
    caller never accepts an arbitrary browser-supplied application object.
    Java repeats every lifecycle and ownership check when the confirmation is
    actually executed.
    """
    if action not in {"cancel", "modify"}:
        raise AfterSalesApplicationError("不支持的售后操作。")
    if action == "cancel" and not application.can_cancel:
        return AfterSalesFlowResult(answer="当前售后申请已无法取消。", applications=[application])
    if action == "modify" and not (application.can_modify or application.can_supplement):
        return AfterSalesFlowResult(answer="当前售后申请暂不支持修改或补充说明。", applications=[application])
    if action == "modify" and reason is None and description is None:
        return AfterSalesFlowResult(
            answer="请说明要更新的售后原因或补充内容；确认后才会写入系统。",
            applications=[application],
        )
    try:
        fingerprint = owner_fingerprint(authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    normalized_reason = _optional_text(reason)
    normalized_description = _optional_text(description)
    pending = PendingAfterSalesAction(
        action_id=uuid4().hex,
        action=action,
        application_id=application.application_id,
        owner_fingerprint=fingerprint,
        session_fingerprint=session_fingerprint(session_id),
        content_hash=_action_content_hash(
            action=action,
            application_id=application.application_id,
            reason=normalized_reason,
            description=normalized_description,
        ),
        reason=normalized_reason,
        description=normalized_description,
        expires_at=time.time() + PENDING_AFTER_SALES_ACTION_TTL_SECONDS,
    )
    save_pending_after_sales_action(session_id, pending)
    record_trace(
        "after_sales_workflow",
        "action_prepared",
        session_id,
        action=action,
        application_type=application.application_type,
    )
    view = to_after_sales_pending_action_view(
        pending,
        application_type_label=application.application_type_label,
    )
    return AfterSalesFlowResult(
        answer=(
            "已生成取消确认，请回复“确认”执行，或回复“取消”放弃。"
            if action == "cancel"
            else "已生成修改确认，请回复“确认”执行，或回复“取消”放弃。"
        ),
        pending_action=view,
        applications=[application],
    )


def start_after_sales_modification_draft(
    *,
    session_id: str,
    authorization: str | None,
    member_id: int | None,
    application: AfterSalesApplicationView,
) -> AfterSalesFlowResult:
    """Keep a selected target while collecting a new reason/description."""
    if not (application.can_modify or application.can_supplement):
        return AfterSalesFlowResult(answer="当前售后申请暂不支持补充或修改说明。", applications=[application])
    try:
        fingerprint = owner_fingerprint(authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    draft = PendingAfterSalesModificationDraft(
        application_id=application.application_id,
        application_type_label=application.application_type_label,
        owner_fingerprint=fingerprint,
        session_fingerprint=session_fingerprint(session_id),
        expires_at=time.time() + PENDING_AFTER_SALES_ACTION_TTL_SECONDS,
    )
    save_pending_after_sales_modification_draft(session_id, draft)
    return AfterSalesFlowResult(
        answer=(
            f"已选中“{application.application_type_label}”申请。"
            "请说明新的售后原因或需要补充的处理信息；系统会先展示变更并等待确认。"
        ),
        applications=[application],
    )


def handle_pending_after_sales_modification_draft(
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None = None,
) -> AfterSalesFlowResult | None:
    try:
        draft = get_pending_after_sales_modification_draft(session_id, authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    if draft is None:
        return None
    normalized = _normalize_message(message)
    if normalized in CANCEL_MESSAGES:
        complete_pending_after_sales_modification_draft(session_id, authorization, member_id)
        return AfterSalesFlowResult(answer="已取消本次售后修改，原申请没有变化。")
    try:
        extraction = extract_after_sales_request(message)
    except AfterSalesApplicationError:
        # Do not convert model failure into customer-provided business fields.
        # The server-owned modification target remains intact, and no action
        # proposal can be produced until a later grounded extraction succeeds.
        return AfterSalesFlowResult(
            answer=(
                "售后修改内容暂时无法可靠识别，原修改草稿已保留。"
                "请稍后重试，或明确说明新的售后原因或补充信息。"
            )
        )
    reason = extraction.reason
    description = extraction.description
    if not reason and not description:
        if normalized in CONFIRM_MESSAGES:
            return AfterSalesFlowResult(
                answer="请先说明要修改的售后原因或补充内容；系统不会在未展示变更前执行写入。"
            )
        return AfterSalesFlowResult(
            answer=(
                "请明确说明新的售后原因或补充内容；系统只会接受能在你的原话中"
                "核验到依据的变更，并会先展示确认。"
            )
        )
    applications = _safe_list_member_applications(authorization)
    application = next(
        (item for item in applications if item.application_id == draft.application_id),
        None,
    )
    if application is None:
        complete_pending_after_sales_modification_draft(session_id, authorization, member_id)
        return AfterSalesFlowResult(answer="该售后申请已不存在或无法继续修改，请先查询售后记录。")
    complete_pending_after_sales_modification_draft(session_id, authorization, member_id)
    if application.can_supplement and not application.can_modify:
        description = description or reason
        reason = None
    return prepare_after_sales_action(
        session_id=session_id,
        authorization=authorization,
        member_id=member_id,
        application=application,
        action="modify",
        reason=reason,
        description=description,
    )


def handle_pending_after_sales_action_confirmation(
    session_id: str,
    message: str,
    authorization: str | None,
    member_id: int | None = None,
) -> AfterSalesFlowResult | None:
    """Execute only a server-persisted cancel/modify confirmation once."""
    try:
        action = get_pending_after_sales_action(session_id, authorization, member_id)
    except AfterSalesPendingStateError as exc:
        return AfterSalesFlowResult(answer=str(exc))
    if action is None:
        return None
    normalized = _normalize_message(message)
    if action.execution_state == "execution_unknown":
        if normalized not in CONFIRM_MESSAGES:
            return AfterSalesFlowResult(
                answer="上一次售后操作结果仍待核实，请回复“确认”继续查询。",
                pending_action=_pending_action_view_for_recovery(action, authorization),
            )
        return _recover_after_sales_action(session_id, action, authorization, member_id)
    if normalized in CANCEL_MESSAGES:
        complete_pending_after_sales_action(session_id, authorization, member_id)
        return AfterSalesFlowResult(answer="已取消本次售后操作，原申请没有变化。")
    if normalized not in CONFIRM_MESSAGES:
        return AfterSalesFlowResult(
            answer="当前已有待确认的售后操作，请回复“确认”执行，或回复“取消”放弃。",
            pending_action=_pending_action_view_for_recovery(action, authorization),
        )
    try:
        application = execute_after_sales_action(
            action_id=action.action_id,
            action=action.action,
            application_id=action.application_id,
            content_hash=action.content_hash,
            reason=action.reason,
            description=action.description,
            authorization=authorization,
        )
    except MallAfterSalesActionUnknownError:
        unknown = mark_pending_after_sales_action_unknown(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "java_action_result_unknown", session_id, action=action.action)
        if unknown is None:
            return AfterSalesFlowResult(answer="售后操作已过期，请重新发起。")
        return _recover_after_sales_action(session_id, unknown, authorization, member_id)
    except MallApiClientError as exc:
        complete_pending_after_sales_action(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "java_action_failed", session_id, action=action.action)
        return AfterSalesFlowResult(answer=f"售后操作未完成：{exc}。请重新查询后再试。")
    complete_pending_after_sales_action(session_id, authorization, member_id)
    record_trace("after_sales_workflow", "action_completed", session_id, action=action.action)
    return _action_completed_result(action.action, application)


def _recover_after_sales_action(
    session_id: str,
    action: PendingAfterSalesAction,
    authorization: str | None,
    member_id: int | None,
) -> AfterSalesFlowResult:
    try:
        status, application = get_after_sales_action_status(action.action_id, authorization)
    except MallApiClientError:
        return AfterSalesFlowResult(
            answer="售后操作的执行结果暂时无法确认，请稍后回复“确认”继续核实。",
            pending_action=_pending_action_view_for_recovery(action, authorization),
        )
    if status == "completed" and application is not None:
        complete_pending_after_sales_action(session_id, authorization, member_id)
        record_trace("after_sales_workflow", "action_recovered", session_id, action=action.action)
        return _action_completed_result(action.action, application)
    retryable = mark_pending_after_sales_action_retryable(
        session_id, authorization, member_id
    ) or action
    return AfterSalesFlowResult(
        answer="尚未确认到售后操作结果，原确认卡已保留。请回复“确认”安全重试。",
        pending_action=_pending_action_view_for_recovery(retryable, authorization),
    )


def _pending_action_view_for_recovery(
    action: PendingAfterSalesAction,
    authorization: str | None,
) -> AfterSalesPendingActionView:
    # The view contains only the customer-visible application number and a
    # stable label. No action key, hash or owner material reaches the browser.
    application_label = "售后申请"
    try:
        applications = _safe_list_member_applications(authorization)
        matched = next(
            (item for item in applications if item.application_id == action.application_id),
            None,
        )
        if matched is not None:
            application_label = matched.application_type_label
    except MallApiClientError:
        pass
    return to_after_sales_pending_action_view(action, application_type_label=application_label)


def _action_completed_result(
    action: str,
    application: AfterSalesApplicationView,
) -> AfterSalesFlowResult:
    verb = "已取消" if action == "cancel" else "已更新"
    return AfterSalesFlowResult(
        answer=(
            f"售后申请{verb}，当前状态为“{application.status_label}”。"
            f"履约状态为“{application.fulfillment_status_label}”，后续以真实审核和履约进度为准。"
        ),
        submitted_application=application,
        completed_action=action,
        applications=[application],
    )


def _safe_list_member_applications(
    authorization: str | None,
) -> list[AfterSalesApplicationView]:
    from app.services.mall_client import list_my_after_sales_applications

    return list_my_after_sales_applications(authorization)


def _merge_message_into_draft(
    draft: PendingAfterSalesDraft,
    message: str,
    verified_order_sn: str | None,
    extraction: AfterSalesRequestExtraction,
) -> None:
    if verified_order_sn:
        draft.order_sn = verified_order_sn
    if extraction.goal:
        draft.goal = extraction.goal
    if extraction.application_type:
        draft.application_type = extraction.application_type
    if extraction.product_hint:
        draft.product_hint = extraction.product_hint
    elif draft.product_options:
        draft.product_hint = _safe_product_hint(message)
    if extraction.reason:
        draft.reason = extraction.reason
    if extraction.description:
        draft.description = extraction.description


def _safe_extract(message: str) -> AfterSalesRequestExtraction:
    try:
        return extract_after_sales_request(message)
    except AfterSalesApplicationError:
        return AfterSalesRequestExtraction()


def _is_draft_follow_up(
    draft: PendingAfterSalesDraft,
    message: str,
    resolution: IdentifierResolution,
    extraction: AfterSalesRequestExtraction,
) -> bool:
    normalized = _normalize_message(message)
    if normalized in CONFIRM_MESSAGES:
        return True
    if resolution.value or resolution.ambiguous:
        return True
    if extraction.goal or extraction.application_type or extraction.reason:
        return True
    return _matches_product_option(draft.product_options, message, extraction.product_hint)


def _draft_result(
    draft: PendingAfterSalesDraft,
    answer: str,
    explicit_missing: list[AfterSalesDraftField] | None = None,
) -> AfterSalesFlowResult:
    missing = explicit_missing if explicit_missing is not None else _missing_fields(draft)
    return AfterSalesFlowResult(
        answer=answer,
        draft=to_after_sales_draft_view(draft, missing),
    )


def _missing_fields(draft: PendingAfterSalesDraft) -> list[AfterSalesDraftField]:
    missing: list[AfterSalesDraftField] = []
    if draft.goal is None:
        missing.append("application_type")
    if draft.application_type is None:
        if "application_type" not in missing:
            missing.append("application_type")
    if not draft.order_sn:
        missing.append("order_sn")
    if draft.application_type and _product_required(draft.application_type) and not draft.product_hint:
        missing.append("product")
    if draft.goal == "apply" and not draft.reason:
        missing.append("reason")
    return missing


def _grounded_enum(candidate, message: str, allowed: set[str]) -> str | None:
    if candidate is None or not candidate.value or not candidate.evidence_span:
        return None
    if candidate.value not in allowed:
        return None
    evidence = candidate.evidence_span.strip()
    if not evidence or _normalize_for_match(evidence) not in _normalize_for_match(message):
        return None
    return candidate.value


def _validate_extraction_contract(
    candidates: AfterSalesRequestCandidateExtraction,
) -> list[str]:
    """Return only machine-safe failures worth one bounded correction.

    A missing/invalid evidence span is a contract failure, while a merely
    non-contiguous span is safely discarded by ``_grounded_*`` below.  Keeping
    that distinction preserves useful partial extraction without allowing an
    ungrounded value into the draft.
    """

    errors: list[str] = []
    for name in ("goal", "application_type", "product_hint", "reason", "description"):
        candidate = getattr(candidates, name, None)
        if candidate is None or candidate.value is None:
            continue
        if not candidate.evidence_span:
            errors.append("evidence_span_missing")
    if candidates.goal and candidates.goal.value not in {"eligibility", "apply"}:
        errors.append("goal_enum_invalid")
    if candidates.application_type and candidates.application_type.value not in {
        "cancel_refund",
        "return_refund",
        "exchange",
        "repair",
    }:
        errors.append("application_type_enum_invalid")
    return list(dict.fromkeys(errors))


def _grounded_span(candidate, message: str, max_length: int) -> str | None:
    if candidate is None or not candidate.evidence_span:
        return None
    evidence = candidate.evidence_span.strip()
    if not evidence or _normalize_for_match(evidence) not in _normalize_for_match(message):
        return None
    return evidence[:max_length]


def _product_required(application_type: AfterSalesApplicationType) -> bool:
    return application_type != "cancel_refund"


def _select_order_item(order_items: list[dict], product_hint: str | None) -> dict | None:
    items = [item for item in order_items if isinstance(item, dict)]
    if len(items) == 1:
        return items[0]
    if not product_hint:
        return None
    hint = _normalize_for_match(product_hint)
    matches = [
        item
        for item in items
        if hint in _normalize_for_match(_format_product(item))
        or _normalize_for_match(str(item.get("product_name") or "")) in hint
    ]
    return matches[0] if len(matches) == 1 else None


def _to_product_options(order_items: list[dict]) -> list[AfterSalesProductOption]:
    options: list[AfterSalesProductOption] = []
    for item in order_items:
        if not isinstance(item, dict):
            continue
        name = _optional_text(item.get("product_name"))
        if name:
            options.append(
                AfterSalesProductOption(
                    product_name=name,
                    product_attr=_optional_text(item.get("product_attr")),
                )
            )
    return options


def _matches_product_option(
    options: list[AfterSalesProductOption], message: str, hint: str | None
) -> bool:
    text = _normalize_for_match(message)
    normalized_hint = _normalize_for_match(hint or "")
    return any(
        _normalize_for_match(option.product_name) in text
        or (
            normalized_hint
            and normalized_hint in _normalize_for_match(_format_option(option))
        )
        for option in options
    )


def _item_id(item: dict | None) -> int | None:
    if item is None:
        return None
    value = item.get("order_item_id")
    return value if isinstance(value, int) and value > 0 else None


def _build_policy_query(draft: PendingAfterSalesDraft, item: dict | None) -> str:
    product = _optional_text((item or {}).get("product_name")) or "商品"
    type_label = application_type_label(draft.application_type)
    reason = draft.reason or "售后"
    return f"{type_label} {reason} {product} 售后条件、处理规则和费用政策"


def _format_product(item: dict) -> str:
    name = _optional_text(item.get("product_name")) or "商品"
    attr = _optional_text(item.get("product_attr"))
    return f"{name}（{attr}）" if attr else name


def _format_option(option: AfterSalesProductOption) -> str:
    return (
        f"{option.product_name}（{option.product_attr}）"
        if option.product_attr
        else option.product_name
    )


def _safe_product_hint(message: str) -> str | None:
    value = " ".join(message.strip().split())
    return value[:200] if value else None


def _normalize_message(message: str) -> str:
    return "".join(message.strip().split())


def _create_proposal_hash(
    *,
    order_sn: str,
    application_type: AfterSalesApplicationType,
    order_item_id: int | None,
    reason: str,
    description: str,
) -> str:
    """Bind the exact server-side creation material before confirmation."""
    canonical = "\n".join(
        (
            "create",
            order_sn,
            application_type,
            str(order_item_id or ""),
            reason,
            description,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _action_content_hash(
    *,
    action: str,
    application_id: int,
    reason: str | None,
    description: str | None,
) -> str:
    canonical = "\n".join(
        (action, str(application_id), reason or "", description or "")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_for_match(value: str) -> str:
    return "".join(value.lower().split())


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
