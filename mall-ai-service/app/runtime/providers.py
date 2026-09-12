"""Model-role adapters for the v3.0 Runtime.

The default provider is deliberately opt-in: without a configured model key it
raises a categorized error and the task is blocked. Tests and offline evals use
``ScriptedRuntimeProvider`` so they never call a real model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.schemas.agent_task import (
    ContextPack,
    ExecutorDecision,
    ResolutionCritique,
    SkillCall,
)
from app.services.llm_service import LLMServiceError, generate_json
from app.services.structured_output_gateway import (
    StructuredOutputError,
    StructuredOutputMode,
    generate_structured_output_with_correction,
)


class RuntimeModelError(RuntimeError):
    def __init__(self, message: str, *, role: str, category: str = "unavailable") -> None:
        super().__init__(message)
        self.role = role
        self.category = category


RUNTIME_PROMPT_VERSION = "agent_runtime_v3_3"


class RuntimeModelContext(BaseModel):
    """Safe state plus one transient current-turn input sent to an Executor.

    ``transient_input`` is never persisted in AgentTask/Plan/Artifact/Memory,
    Trace or public DTO. It exists only during the current provider call so a
    newly created task can be understood without storing a raw conversation.
    """

    model_config = ConfigDict(extra="forbid")

    task_ref: str
    transient_input: str = Field(default="", max_length=2000)
    goal: str = Field(max_length=240)
    task_status: str
    plan_version: int
    plan_summary: str = Field(max_length=640)
    open_questions: list[str] = Field(default_factory=list, max_length=8)
    artifacts: list[str] = Field(default_factory=list, max_length=12)
    context_pack_version: int | None = Field(default=None, ge=1, le=99)
    context_verified_facts: list[str] = Field(default_factory=list, max_length=12)
    context_unresolved_assumptions: list[str] = Field(default_factory=list, max_length=8)
    memory_hints: list[str] = Field(default_factory=list, max_length=6)
    context_artifact_refs: list[str] = Field(default_factory=list, max_length=16)
    artifact_details: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    limitation_codes: list[str] = Field(default_factory=list, max_length=8)
    available_skills: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    reference_hints: dict[str, str] = Field(default_factory=dict, max_length=6)
    discovery_complete: bool = False
    action_pending: bool = False
    model_calls_remaining: int = Field(ge=0)
    tool_calls_remaining: int = Field(ge=0)


class ContextCuratorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_ref: str
    goal: str
    plan_snapshot: str
    artifact_summaries: list[str] = Field(default_factory=list, max_length=24)
    existing_memory_hints: list[str] = Field(default_factory=list, max_length=8)
    available_skills: list[str] = Field(default_factory=list, max_length=8)
    token_estimate_before: int = Field(ge=0)


class CuratorModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified_facts: list[str] = Field(default_factory=list, max_length=12)
    unresolved_assumptions: list[str] = Field(default_factory=list, max_length=8)
    candidate_actions: list[str] = Field(default_factory=list, max_length=4)
    executed_effects: list[str] = Field(default_factory=list, max_length=8)
    memory_hints: list[str] = Field(default_factory=list, max_length=6)


class RuntimeModelProvider(Protocol):
    def decide(self, context: RuntimeModelContext) -> ExecutorDecision: ...

    def curate(self, context: ContextCuratorInput) -> CuratorModelOutput: ...

    def critique(self, context: dict[str, Any]) -> ResolutionCritique: ...


EXECUTOR_SYSTEM_PROMPT = """
你是 Mall v3.0 的 commerce_executor。你只能在已发现的 Skill 白名单内规划电商商品、订单、物流、库存、政策、售后和人工协同任务。

每次只返回一个严格 JSON 决策：discover_skills、call_skill、spawn_subtask、revise_plan、ask_user、propose_action 或 finish。
不要输出思维链，不要编造事实，不要输出完整订单号/凭证/客户原话，不要自创 Skill。
``call_skill`` 只能列出 actionMode=read 的已发现 Skill；即使列表中同时展示了 draft、async_task 或 commit Skill，
也绝不能把它们放进 call_skill。需要 draft 或 commit 能力时，只能使用 propose_action；
``spawn_subtask`` 是 Runtime 的受控规划决策，完成必要只读事实后可直接选择它，不能把它包装成 propose_action。
由 Runtime 生成受版本、owner、TTL、内容哈希和确认状态约束的 ActionProposal。commit Skill 永远需要客户确认，
不能在 Executor 决策中直接执行。
服务端已经在每轮模型调用前完成一次有界能力发现，并在上下文中提供 discovery_complete。
当 discovery_complete=true 时不要再次返回 discover_skills；直接在白名单内选择下一步。
重复发现能力不会产生新事实，也不能替代读取事实。

先理解目标和当前已核验 Artifact，再作一个最小、直接的下一步：
- 目标需要商城事实而当前没有对应 Artifact 时，调用一个最直接相关的只读 Skill；不要先 finish，也不要并发调用无关 Skill。
- 读取结果后，如果目标仍依赖另一项事实，继续读取或形成受控的事实组合；如果只是只读咨询且证据足够，才 finish。
- 目标涉及创建、修改、提交、人工协同或其他业务效果时，不能直接 finish。先取得必要的核验事实，再用 propose_action 形成待确认 ActionProposal；客户确认之前绝不提交。
- 如果目标明确要求先准备售后草案/提案，且已经有 verified 的 order_fact，但申请类型尚未明确，不要猜测四种申请类型；可以用 create_after_sales_draft 仅引用 orderFactRef 形成未提交草案，再在待确认阶段澄清类型。不得把草案当成最终写入，也不得直接选择 commit_after_sales_action。
- list_service_applications 只用于用户明确要查看已有售后申请/进度的目标；它不能替代订单事实，也不是新售后动作的默认第一步。
- 如果售后申请摘要已经读取但目标还涉及资格判断，且当前没有 verified 的 order_fact，必须继续读取订单事实后再完成；申请列表不能替代订单事实。
- 新的售后处理目标应优先读取相关订单/政策事实，必要时调用 build_service_resolution，再形成 propose_action；不要为了“申请”这个词泛化调用列表查询。
- Skill 返回 blocked、unavailable 或证据不足时，使用 ask_user 或安全停止，不能用模型常识补写事实、继续推进或宣称成功。
- 目标不清楚或缺少 opaque reference 时，使用 ask_user；不要猜订单、SKU、申请、账号或政策版本。
- ``artifact_details`` 是服务端投影的权威事实摘要，其中 ``reference`` 是可用于行动提案的 opaque handle；它为空时不要 finish。若服务端已提供与当前只读 Skill 匹配的 reference_hints，先读取该 Skill，再决定是否需要澄清。
- 如果 ``limitation_codes`` 非空，表示至少一个依赖失败或证据不可用；不要重复相同只读调用，也不要 finish，只能安全停止或向用户说明缺口。
- 只读方案比较在 ``artifact_details`` 已包含 ``resolution_candidate`` 且没有 limitation_codes 时可直接 finish；不要为了只读比较额外创建子任务。
- 商品候选的“比较”必须有比较事实；只有 ``catalog_fact`` 只能说明候选已找到，不能直接 finish。若当前目标要求比较，继续调用已注册的比较 Skill，或在事实不足时安全澄清。

当事实冲突、预算不足、Skill 不可用或目标不清楚时，使用 ask_user、revise_plan 或安全停止，并在 reasonSummary 中给出简短用户可见说明。

[Skill 输入契约]
模型只能使用下列已审计的参数键；值必须是服务端提供的 opaque reference 或短摘要，不能自行创造标识：
- search_catalog: query, category；compare_skus: sku_refs, criteria
- read_order, read_logistics: orderRef（缺少时使用 ask_user，不要传空值）
- read_inventory: skuRef；retrieve_policy: query, policy_version
- list_service_applications: 不需要参数；build_service_resolution: factRefs
- search_task_memory: query；spawn_subtask: goalCode, requiredSkills
- 需要行动提案时，commit_after_sales_action 只允许 orderFactRef, applicationType, proposalRef, actionRef；
  create_after_sales_draft 只允许 orderFactRef, applicationType, proposalRef；其他 draft/async 能力只允许其目录声明的引用键。
  行动提案中的 orderFactRef、proposalRef、actionRef 必须逐字复制已核验 ``artifact_details`` 的 opaque reference；
  不得把 reference_hints、用户输入的订单号/SKU 或任何原始业务标识直接放进行动参数。
  Runtime 会拒绝任何额外键，且由服务端生成幂等键。  

[停止与重试边界]
- 已经取得足以回答只读目标的已核验事实后，使用 finish；不要为了“再确认一次”重复调用同一 Skill。
- 同一 Skill 只有在参数确实不同且目标仍缺少必要事实时才可再次调用；不要先用空参数试探。
- 如果服务端明确说明已拒绝相同参数的重复只读调用，下一步只能使用现有事实 finish，
  或 ask_user 说明缺口；严禁再次 call_skill。
- 如果没有可用的 opaque reference，使用 ask_user 请求必要信息；不要猜订单、SKU、申请或政策版本。
- 如果上下文提供了 reference_hints，只能原样使用其中与当前 Skill 输入匹配的 opaque reference；不要改写、拼接或回显其原始业务值。
- 当 reference_hints 包含当前只读 Skill 所需的引用时，应直接使用该服务端引用读取事实，不要再次追问同一个已提供的引用。
- 目标要求商品候选比较时，先取得候选事实再调用 compare_skus；目标要求复用上次任务时，优先使用 search_task_memory；不能用 finish 替代这些必要的事实步骤。

[少量对比示例]
- 首轮需要订单或物流事实：call_skill（只读）→观察结果→必要时继续读取→finish。
- 首轮需要售后处理：call_skill（订单/资格/政策等只读）→必要时形成候选→propose_action；不要在没有证据时 finish。
- 首轮缺少标识或问题存在两个合理解释：ask_user；不要把猜测当作事实。
""".strip()

CURATOR_SYSTEM_PROMPT = """
你是 context_curator。只根据已核验 Artifact 的安全摘要压缩 Context Pack。
保留关键事实引用、未解决假设、候选行动和记忆提示；不要补写业务事实，不要读取或复述客户原话、订单号、Token、RAG 原文或完整工具载荷。
只返回 JSON，不输出解释。
""".strip()

CRITIC_SYSTEM_PROMPT = """
你是 resolution_critic。只检查候选方案是否覆盖目标、是否存在事实冲突或未解决假设。
只能返回 missingFacts、conflictingArtifacts、unmetSuccessCriteria、recommendedNextExperiment、candidateRankingRationale；不能提交行动、改写事实或改变权限。
""".strip()


class DeepSeekRuntimeProvider:
    """Provider-neutral role adapter using the existing structured gateway."""

    def decide(self, context: RuntimeModelContext) -> ExecutorDecision:
        return self._structured(
            role="commerce_executor",
            message=json.dumps(context.model_dump(), ensure_ascii=False),
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            response_model=ExecutorDecision,
            validate_result=lambda decision: _validate_executor_decision(decision, context),
            correction_context={
                "schema_version": RUNTIME_PROMPT_VERSION,
                "available_skill_ids": [
                    str(skill.get("skillId"))
                    for skill in context.available_skills
                    if isinstance(skill.get("skillId"), str)
                ],
                "available_read_skill_ids": [
                    str(skill.get("skillId"))
                    for skill in context.available_skills
                    if skill.get("actionMode") == "read" and isinstance(skill.get("skillId"), str)
                ],
                "reference_hint_keys": list(context.reference_hints),
                "reference_hint_values": dict(context.reference_hints),
                "artifact_count": len(context.artifact_details),
                "limitation_codes": list(context.limitation_codes),
            },
            mode=StructuredOutputMode.JSON_OBJECT,
        )

    def curate(self, context: ContextCuratorInput) -> CuratorModelOutput:
        return self._structured(
            role="context_curator",
            message=json.dumps(context.model_dump(), ensure_ascii=False),
            system_prompt=CURATOR_SYSTEM_PROMPT,
            response_model=CuratorModelOutput,
        )

    def critique(self, context: dict[str, Any]) -> ResolutionCritique:
        try:
            raw = generate_json(
                message=json.dumps(context, ensure_ascii=False),
                system_prompt=CRITIC_SYSTEM_PROMPT,
                temperature=0,
            )
            return ResolutionCritique.model_validate(raw, strict=True)
        except (LLMServiceError, StructuredOutputError, ValueError, TypeError) as exc:
            category = getattr(exc, "category", "invalid_response")
            raise RuntimeModelError(
                "方案评审模型暂时不可用。",
                role="resolution_critic",
                category=category,
            ) from exc

    def _structured(
        self,
        *,
        role: str,
        message: str,
        system_prompt: str,
        response_model,
        validate_result=None,
        correction_context: dict[str, Any] | None = None,
        mode: StructuredOutputMode = StructuredOutputMode.PROMPT_JSON,
    ):
        try:
            result = generate_structured_output_with_correction(
                message=message,
                system_prompt=system_prompt,
                response_model=response_model,
                mode=mode,
                temperature=0,
                json_generator=generate_json,
                correction_context=correction_context,
                correction_system_prompt=system_prompt,
                correction_message=(
                    "仅修复已列出的 JSON/运行时契约错误；如果错误要求先读取已提供的事实引用，"
                    "只选择一个最小只读 Skill，不新增业务结论。"
                ),
                validate_result=validate_result,
            )
            return result.value
        except (LLMServiceError, StructuredOutputError, ValueError, TypeError) as exc:
            if role == "commerce_executor" and isinstance(exc, StructuredOutputError):
                repaired = _server_read_repair(
                    correction_context=correction_context,
                    validation_codes=exc.validation_codes,
                )
                if repaired is not None:
                    return repaired
            category = getattr(exc, "category", None)
            if not category and isinstance(exc, StructuredOutputError) and exc.validation_codes:
                category = "contract_" + "_".join(exc.validation_codes[:2])
            category = category or "invalid_response"
            raise RuntimeModelError(
                "任务模型暂时不可用，当前任务已安全暂停。",
                role=role,
                category=category,
            ) from exc


def _server_read_repair(
    *,
    correction_context: dict[str, Any] | None,
    validation_codes: tuple[str, ...],
) -> ExecutorDecision | None:
    """Repair one safe read-only contract violation using server references.

    This is deliberately limited to a server-provided opaque reference and a
    registered read Skill. It is not a natural-language router and cannot
    create a proposal, commit, or business fact.
    """

    context = correction_context or {}
    skills = set(context.get("available_skill_ids") or ())
    read_skills = set(context.get("available_read_skill_ids") or ())
    hint_keys = set(context.get("reference_hint_keys") or ())
    hint_values = context.get("reference_hint_values") or {}
    codes = set(validation_codes)
    if "resolution_candidate_already_available" in codes:
        return ExecutorDecision(
            decision="finish",
            reason_summary="已基于核验事实整理候选方案；当前未创建维修工单或执行其他业务动作。",
        )
    target: str | None = None
    argument_key: str | None = None
    if "orderRef" in hint_keys and "read_order" in skills and codes.intersection(
        {
            "ask_before_server_order_reference_read",
            "finish_without_observation",
            "read_order_reference_missing",
            "read_logistics_requires_order_fact",
            "required_order_fact_before_logistics",
            "after_sales_list_requires_order_fact",
        }
    ):
        target, argument_key = "read_order", "orderRef"
    elif "skuRef" in hint_keys and "read_inventory" in skills and codes.intersection(
        {"ask_before_server_sku_reference_read", "finish_without_observation", "read_inventory_reference_missing"}
    ):
        target, argument_key = "read_inventory", "skuRef"
    elif "required_first_read" in codes and read_skills:
        target = sorted(read_skills)[0]
    if target is None or not isinstance(hint_values, dict):
        if "finish_without_observation" in codes:
            return ExecutorDecision(
                decision="ask_user",
                reason_summary="当前目标还缺少可核验事实。",
                user_question="请补充需要核验的订单、商品或政策范围后继续。",
            )
        if "finish_with_dependency_limitation" in codes:
            return ExecutorDecision(
                decision="ask_user",
                reason_summary="当前事实暂时无法核验。",
                user_question="当前依赖暂时不可用，请补充必要信息或稍后重试。",
            )
        return None
    arguments: dict[str, str] = {}
    if argument_key is not None:
        reference = hint_values.get(argument_key)
        if not isinstance(reference, str) or not reference:
            return None
        arguments[argument_key] = reference
    return ExecutorDecision(
        decision="call_skill",
        reason_summary="先读取服务端已提供的只读事实引用。",
        skill_calls=[SkillCall(skill_id=target, arguments=arguments)],
        expected_next_observation="读取事实后再决定是否需要澄清或结束。",
    )


def _validate_executor_decision(
    decision: ExecutorDecision,
    context: RuntimeModelContext,
) -> tuple[str, ...]:
    """Return bounded semantic errors that are safe to repair once.

    These checks are contract guards, not intent routing: they only compare a
    decision with server-provided references and already persisted artifacts.
    They prevent a model from finishing before any observation or asking the
    customer for a reference that the server has already supplied.
    """

    errors: list[str] = []
    read_skills = {
        str(skill.get("skillId"))
        for skill in context.available_skills
        if skill.get("actionMode") == "read" and isinstance(skill.get("skillId"), str)
    }
    if decision.decision == "finish" and not context.artifact_details:
        errors.append("finish_without_observation")
    if decision.decision == "finish" and context.limitation_codes:
        errors.append("finish_with_dependency_limitation")
    if (
        decision.decision == "finish"
        and any(item.get("kind") == "after_sales_fact" for item in context.artifact_details)
        and not any(item.get("kind") == "order_fact" for item in context.artifact_details)
        and any(skill.get("skillId") == "read_order" for skill in context.available_skills)
        and not context.limitation_codes
    ):
        errors.append("after_sales_list_requires_order_fact")
    if decision.decision == "ask_user" and not context.artifact_details:
        if context.reference_hints.get("orderRef") and any(
            str(skill.get("skillId")) in {"read_order", "read_logistics"}
            for skill in context.available_skills
        ):
            errors.append("ask_before_server_order_reference_read")
        if context.reference_hints.get("skuRef") and any(
            str(skill.get("skillId")) == "read_inventory"
            for skill in context.available_skills
        ):
            errors.append("ask_before_server_sku_reference_read")
        if len(read_skills) == 1 and next(iter(read_skills)) in {
            "retrieve_policy",
            "search_task_memory",
            "list_service_applications",
        }:
            errors.append("required_first_read")
    if decision.decision == "spawn_subtask" and not context.artifact_details and read_skills:
        errors.append("required_first_read")
    if (
        decision.decision == "spawn_subtask"
        and any(item.get("kind") == "resolution_candidate" for item in context.artifact_details)
        and not context.limitation_codes
    ):
        errors.append("resolution_candidate_already_available")
    if decision.decision == "call_skill":
        called_skill_ids = {call.skill_id for call in decision.skill_calls}
        has_order_artifact = any(item.get("kind") == "order_fact" for item in context.artifact_details)
        if (
            "read_logistics" in called_skill_ids
            and "read_order" in read_skills
            and "read_order" not in called_skill_ids
            and not has_order_artifact
        ):
            errors.append("read_logistics_requires_order_fact")
        for call in decision.skill_calls:
            if call.skill_id in {"read_order", "read_logistics"} and context.reference_hints.get("orderRef"):
                if call.arguments.get("orderRef") != context.reference_hints["orderRef"]:
                    errors.append("read_order_reference_missing")
            if call.skill_id == "read_inventory" and context.reference_hints.get("skuRef"):
                if call.arguments.get("skuRef") != context.reference_hints["skuRef"]:
                    errors.append("read_inventory_reference_missing")
    return tuple(dict.fromkeys(errors))


@dataclass
class ScriptedRuntimeProvider:
    """Deterministic provider for contract_mock and unit tests."""

    decisions: list[ExecutorDecision]
    curator_output: CuratorModelOutput | None = None
    critique_output: ResolutionCritique | None = None
    decision_calls: int = 0
    curator_calls: int = 0
    critic_calls: int = 0

    def decide(self, context: RuntimeModelContext) -> ExecutorDecision:
        self.decision_calls += 1
        if not self.decisions:
            raise RuntimeModelError("脚本化 Executor 没有更多决策。", role="commerce_executor", category="fixture_exhausted")
        return self.decisions.pop(0)

    def curate(self, context: ContextCuratorInput) -> CuratorModelOutput:
        self.curator_calls += 1
        if self.curator_output is not None:
            return self.curator_output
        return CuratorModelOutput(
            verified_facts=list(context.artifact_summaries[:8]),
            unresolved_assumptions=[],
            candidate_actions=[],
            executed_effects=[],
            memory_hints=list(context.existing_memory_hints[:4]),
        )

    def critique(self, context: dict[str, Any]) -> ResolutionCritique:
        self.critic_calls += 1
        return self.critique_output or ResolutionCritique()


@dataclass
class UnavailableRuntimeProvider:
    """Explicit safe-stop provider for environments without a model key."""

    def decide(self, context: RuntimeModelContext) -> ExecutorDecision:
        raise RuntimeModelError("EXECUTOR_MODEL 未配置。", role="commerce_executor", category="missing_configuration")

    def curate(self, context: ContextCuratorInput) -> CuratorModelOutput:
        raise RuntimeModelError("CONTEXT_MODEL 未配置。", role="context_curator", category="missing_configuration")

    def critique(self, context: dict[str, Any]) -> ResolutionCritique:
        raise RuntimeModelError("CRITIC_MODEL 未配置。", role="resolution_critic", category="missing_configuration")
