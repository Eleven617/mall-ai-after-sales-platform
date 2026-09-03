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
    available_skills: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
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
read Skill 只能读取服务端核验事实；draft/async_task 只能生成受控提案或待处理任务；commit Skill 永远需要客户确认，不能在 Executor 决策中直接执行。
当事实冲突、预算不足、Skill 不可用或目标不清楚时，使用 ask_user、revise_plan 或 finish，并在 reasonSummary 中给出简短用户可见说明。
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

    def _structured(self, *, role: str, message: str, system_prompt: str, response_model):
        try:
            result = generate_structured_output_with_correction(
                message=message,
                system_prompt=system_prompt,
                response_model=response_model,
                mode=StructuredOutputMode.PROMPT_JSON,
                temperature=0,
                json_generator=generate_json,
                correction_context={"schema_version": "agent_runtime_v3_0"},
                correction_system_prompt=system_prompt,
                correction_message="仅修复 JSON Schema 结构，不新增业务结论。",
            )
            return result.value
        except (LLMServiceError, StructuredOutputError, ValueError, TypeError) as exc:
            category = getattr(exc, "category", "invalid_response")
            raise RuntimeModelError(
                "任务模型暂时不可用，当前任务已安全暂停。",
                role=role,
                category=category,
            ) from exc


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
