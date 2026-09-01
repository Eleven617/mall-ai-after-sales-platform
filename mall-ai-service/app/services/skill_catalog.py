"""Server-owned business Skill catalog and role/tool guard.

This is intentionally a fixed catalog, not a model-discoverable plugin system.
The structured intent route and deterministic workflow state choose a Skill;
an LLM never receives authority to invent another one.
"""
from __future__ import annotations

from app.schemas.agent_harness import AgentRole, CapabilityProfile, SkillDefinition


SKILL_CATALOG_VERSION = "mall-business-skills.v1"


class SkillPolicyError(RuntimeError):
    pass


_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        skill_id="policy_question_answering",
        semantic_version="v1",
        owner_role="unified_after_sales",
        input_contract="PolicyQuestionInput/v1",
        output_contract="GroundedPolicyAnswer/v1",
        allowed_tool_ids=("rag_search",),
        allowed_state_transitions=("policy_evidence_ready", "safe_failure"),
        required_evidence_kinds=("policy_evidence",),
        max_model_calls=2,
        max_tool_calls=1,
        timeout_seconds=30,
        guard_profile_version="guardrails-v1",
        prompt_fragment_version="policy-rag-v1",
        eval_suite_refs=("rag2-golden.v1", "rag-grounding.v1"),
    ),
    SkillDefinition(
        skill_id="order_exception_diagnosis",
        semantic_version="v1",
        owner_role="unified_after_sales",
        input_contract="OrderExceptionInput/v1",
        output_contract="VerifiedDiagnosis/v1",
        allowed_tool_ids=("order_service", "logistics_service", "rag_search"),
        allowed_state_transitions=("needs_identifier", "diagnosis_ready", "clarification_required", "safe_failure"),
        required_evidence_kinds=("order_fact", "logistics_fact"),
        max_model_calls=7,
        max_tool_calls=7,
        timeout_seconds=30,
        guard_profile_version="guardrails-v1",
        prompt_fragment_version="diagnosis-agent-v1",
        eval_suite_refs=("quality-agent.v2", "live-model-synthetic.v1"),
    ),
    SkillDefinition(
        skill_id="after_sales_proposal",
        semantic_version="v1",
        owner_role="unified_after_sales",
        input_contract="VerifiedAfterSalesFacts/v1",
        output_contract="AfterSalesProposal/v1",
        allowed_tool_ids=("order_service", "logistics_service", "rag_search"),
        allowed_state_transitions=("proposal_draft_ready", "awaiting_customer_confirmation", "invalidated", "safe_failure"),
        required_evidence_kinds=("order_fact", "eligibility_fact", "policy_evidence"),
        max_model_calls=2,
        max_tool_calls=4,
        timeout_seconds=30,
        guard_profile_version="proposal-guard-v1",
        prompt_fragment_version="after-sales-extraction-v1",
        eval_suite_refs=("after-sales-contract.v1",),
    ),
    SkillDefinition(
        skill_id="case_handoff",
        semantic_version="v1",
        owner_role="unified_after_sales",
        input_contract="SafeDiagnosisProjection/v1",
        output_contract="MinimalCaseHandoff/v1",
        allowed_tool_ids=(),
        allowed_state_transitions=("handoff_created", "safe_failure"),
        required_evidence_kinds=("verified_fact_reference",),
        max_model_calls=0,
        max_tool_calls=0,
        timeout_seconds=15,
        guard_profile_version="handoff-redaction-v1",
        prompt_fragment_version="none-v1",
        eval_suite_refs=("quality-agent.v2",),
    ),
    SkillDefinition(
        skill_id="handoff_operations_analysis",
        semantic_version="v1",
        owner_role="operations_analysis",
        input_contract="MinimalCaseHandoffAndMetrics/v1",
        output_contract="OperationsAnalysisDraft/v1",
        allowed_tool_ids=("read_case_handoff", "read_after_sales_metrics"),
        allowed_state_transitions=("analysis_draft_ready", "safe_failure"),
        required_evidence_kinds=("case_handoff", "aggregate_metrics"),
        max_model_calls=1,
        max_tool_calls=2,
        timeout_seconds=30,
        guard_profile_version="operations-readonly-v1",
        prompt_fragment_version="operations-analysis-v1",
        eval_suite_refs=("quality-agent.v2",),
    ),
    SkillDefinition(
        skill_id="quality_contract_evaluation",
        semantic_version="v1",
        owner_role="quality_evaluation",
        input_contract="SyntheticEvalCase/v1",
        output_contract="QualityEvaluationRun/v1",
        allowed_tool_ids=("run_contract_evaluation", "analyze_safe_failure_projection"),
        allowed_state_transitions=("evaluation_completed", "awaiting_human_review", "safe_failure"),
        required_evidence_kinds=("synthetic_fixture",),
        max_model_calls=1,
        max_tool_calls=2,
        timeout_seconds=60,
        guard_profile_version="quality-contract-v1",
        prompt_fragment_version="quality-failure-analysis-v1",
        eval_suite_refs=("quality-agent.v2",),
    ),
)

_SKILL_BY_ID = {skill.skill_id: skill for skill in _SKILLS}

_CAPABILITY_PROFILES: tuple[CapabilityProfile, ...] = (
    CapabilityProfile(
        role="unified_after_sales",
        allowed_skill_ids=(
            "policy_question_answering",
            "order_exception_diagnosis",
            "after_sales_proposal",
            "case_handoff",
        ),
        allowed_tool_ids=("order_service", "logistics_service", "rag_search"),
        business_writes_allowed=False,
    ),
    CapabilityProfile(
        role="operations_analysis",
        allowed_skill_ids=("handoff_operations_analysis",),
        allowed_tool_ids=("read_case_handoff", "read_after_sales_metrics"),
        business_writes_allowed=False,
    ),
    CapabilityProfile(
        role="quality_evaluation",
        allowed_skill_ids=("quality_contract_evaluation",),
        allowed_tool_ids=("run_contract_evaluation", "analyze_safe_failure_projection"),
        business_writes_allowed=False,
    ),
)

_PROFILE_BY_ROLE = {profile.role: profile for profile in _CAPABILITY_PROFILES}


def list_skill_definitions() -> tuple[SkillDefinition, ...]:
    return _SKILLS


def capability_profile(role: AgentRole) -> CapabilityProfile:
    try:
        return _PROFILE_BY_ROLE[role]
    except KeyError as exc:
        raise SkillPolicyError("未注册的 Agent 角色。") from exc


def get_skill_definition(skill_id: str) -> SkillDefinition:
    try:
        return _SKILL_BY_ID[skill_id]
    except KeyError as exc:
        raise SkillPolicyError("未注册的业务 Skill。") from exc


def assert_skill_selected_by_role(role: AgentRole, skill_id: str) -> SkillDefinition:
    profile = capability_profile(role)
    skill = get_skill_definition(skill_id)
    if skill.owner_role != role or skill_id not in profile.allowed_skill_ids:
        raise SkillPolicyError("当前角色不可选择该业务 Skill。")
    return skill


def assert_tool_allowed_for_skill(role: AgentRole, skill_id: str, tool_name: str) -> SkillDefinition:
    skill = assert_skill_selected_by_role(role, skill_id)
    profile = capability_profile(role)
    if tool_name not in skill.allowed_tool_ids or tool_name not in profile.allowed_tool_ids:
        raise SkillPolicyError("当前业务 Skill 不允许调用该工具。")
    return skill


def select_customer_skill(*, intent_name: str, route: str, tool_name: str | None = None) -> str:
    """Map only already-validated server intent/route values to a closed Skill.

    This is deliberately not a second natural-language classifier and never
    looks at customer text. Unknown routes fail rather than falling back to a
    broad privilege set.
    """

    if route == "rag" or tool_name == "rag_search" or intent_name == "after_sales_policy":
        return "policy_question_answering"
    if route == "agent" or intent_name in {"query_order_status", "query_logistics", "query_inventory"}:
        return "order_exception_diagnosis"
    if route == "after_sales_flow":
        if intent_name == "after_sales_policy":
            return "policy_question_answering"
        return "after_sales_proposal"
    if route == "tool_calling" and tool_name in {"order_service", "logistics_service"}:
        return "order_exception_diagnosis"
    raise SkillPolicyError("当前受控路由没有可用业务 Skill。")
