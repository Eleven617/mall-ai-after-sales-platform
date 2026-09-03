"""Strict contracts for the Mall v3.0 E-Commerce Task Runtime.

The models in this module intentionally distinguish internal task records from
the small, safe projection returned to the browser.  A task can refer to
verified Java/RAG results, but it never persists a raw conversation, Token,
complete order number, tool payload, RAG passage, prompt or model reasoning.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgentTaskStatus = Literal[
    "created",
    "planning",
    "executing",
    "replanning",
    "waiting_for_user",
    "waiting_for_async_task",
    "ready_to_commit",
    "committing",
    "completed",
    "failed",
    "blocked",
    "cancelled",
]
PlanNodeStatus = Literal["pending", "running", "completed", "blocked", "skipped"]
ArtifactFactuality = Literal["verified", "derived", "proposal", "unavailable"]
ArtifactVisibility = Literal["owner", "runtime"]
ActionMode = Literal["read", "draft", "commit", "async_task"]
ConfirmationStatus = Literal[
    "not_required",
    "awaiting_confirmation",
    "confirmed",
    "withdrawn",
    "expired",
    "committed",
    "blocked",
    "unknown",
]
ExecutorDecisionName = Literal[
    "discover_skills",
    "call_skill",
    "spawn_subtask",
    "revise_plan",
    "ask_user",
    "propose_action",
    "finish",
]
TaskRole = Literal["commerce_executor", "context_curator", "resolution_critic"]


_SENSITIVE_MARKERS = (
    "bearer ",
    "authorization",
    "password",
    "token=",
    "api_key",
    "traceback",
    "<system>",
    "<prompt>",
)
_LONG_NUMBER = re.compile(r"(?<!\d)\d{6,}(?!\d)")
_OPAQUE_REFERENCE = re.compile(r"^[a-z][a-z0-9_-]{7,79}$")


def ensure_safe_summary(value: str, *, max_length: int = 240) -> str:
    """Validate a user/model-visible summary without retaining raw business data."""

    if not isinstance(value, str):
        raise ValueError("摘要必须是字符串")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("摘要不能为空")
    if len(normalized) > max_length:
        raise ValueError("摘要过长")
    lowered = normalized.lower()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        raise ValueError("摘要包含禁止的敏感内容")
    if _LONG_NUMBER.search(normalized):
        raise ValueError("摘要不能包含完整业务标识")
    return normalized


def opaque_hash(value: str, *, prefix: str) -> str:
    """Create a non-reversible stable reference suitable for a public-safe trace."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


class TaskExecutionBudget(BaseModel):
    """Bounded resources for one task; model output can never raise them."""

    model_config = ConfigDict(extra="forbid")

    max_model_calls: int = Field(default=6, ge=1, le=12)
    max_tool_calls: int = Field(default=8, ge=1, le=16)
    max_parallel_reads: int = Field(default=3, ge=1, le=4)
    max_wall_clock_seconds: int = Field(default=90, ge=10, le=300)
    max_provider_cost: float = Field(default=0.0, ge=0.0, le=50.0)


class TaskPlanNode(BaseModel):
    """One user-explainable plan node, never a hidden chain-of-thought step."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(pattern=r"^node-[a-z0-9]{8,32}$")
    goal: str = Field(min_length=1, max_length=240)
    assigned_role: TaskRole = "commerce_executor"
    required_skills: list[str] = Field(default_factory=list, max_length=8)
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    status: PlanNodeStatus = "pending"
    expected_artifacts: list[str] = Field(default_factory=list, max_length=8)
    candidate_actions: list[str] = Field(default_factory=list, max_length=4)
    retry_budget: int = Field(default=1, ge=0, le=2)

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, value: str) -> str:
        return ensure_safe_summary(value)

    @field_validator("required_skills", "expected_artifacts", "candidate_actions")
    @classmethod
    def validate_closed_names(cls, values: list[str]) -> list[str]:
        for value in values:
            if not isinstance(value, str) or not _OPAQUE_REFERENCE.fullmatch(value):
                raise ValueError("计划引用格式不合法")
        return values


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(pattern=r"^plan-[a-z0-9]{8,32}$")
    task_id: str = Field(pattern=r"^task-[a-z0-9]{8,32}$")
    version: int = Field(ge=1, le=99)
    objective: str = Field(min_length=1, max_length=240)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    open_questions: list[str] = Field(default_factory=list, max_length=8)
    nodes: list[TaskPlanNode] = Field(default_factory=list, min_length=1, max_length=12)
    revision_reason: str | None = Field(default=None, max_length=240)
    created_by: TaskRole = "commerce_executor"
    created_at: float = Field(default_factory=time.time)

    @field_validator("objective", "revision_reason")
    @classmethod
    def validate_summary_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_safe_summary(value)

    @field_validator("assumptions", "open_questions")
    @classmethod
    def validate_summary_list(cls, values: list[str]) -> list[str]:
        return [ensure_safe_summary(value) for value in values]


class TaskArtifact(BaseModel):
    """A safe, owner-scoped projection of a Skill observation."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(pattern=r"^artifact-[a-z0-9]{8,32}$")
    task_id: str = Field(pattern=r"^task-[a-z0-9]{8,32}$")
    kind: Literal[
        "catalog_fact",
        "sku_comparison",
        "order_fact",
        "logistics_fact",
        "inventory_fact",
        "policy_evidence",
        "after_sales_fact",
        "resolution_candidate",
        "action_result",
        "async_task",
        "memory_hint",
    ]
    source_skill: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    source_version: str = Field(pattern=r"^v[0-9]+(?:\.[0-9]+){0,2}$")
    factuality: ArtifactFactuality
    summary: str = Field(min_length=1, max_length=320)
    reference: str = Field(pattern=r"^[a-z][a-z0-9_-]{7,79}$")
    expires_at: float
    visibility_scope: ArtifactVisibility = "owner"
    hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

    @field_validator("summary")
    @classmethod
    def validate_artifact_summary(cls, value: str) -> str:
        return ensure_safe_summary(value, max_length=320)


class ActionProposal(BaseModel):
    """A transaction gate. Its parameters stay behind a server-only reference."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(pattern=r"^proposal-[a-z0-9]{8,32}$")
    task_id: str = Field(pattern=r"^task-[a-z0-9]{8,32}$")
    action_skill: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    arguments_ref: str = Field(pattern=r"^args-[a-z0-9]{8,64}$")
    expected_effect: str = Field(min_length=1, max_length=240)
    evidence_refs: list[str] = Field(default_factory=list, max_length=8)
    alternatives: list[str] = Field(default_factory=list, max_length=4)
    user_explanation: str = Field(min_length=1, max_length=320)
    confirmation_status: ConfirmationStatus = "awaiting_confirmation"
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    expires_at: float

    @field_validator("expected_effect", "user_explanation")
    @classmethod
    def validate_action_text(cls, value: str) -> str:
        return ensure_safe_summary(value, max_length=320)

    @field_validator("alternatives")
    @classmethod
    def validate_alternatives(cls, values: list[str]) -> list[str]:
        return [ensure_safe_summary(value) for value in values]


class ContextPack(BaseModel):
    """Versioned, permitted context passed to the next Executor turn."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str = Field(pattern=r"^context-[a-z0-9]{8,32}$")
    task_id: str = Field(pattern=r"^task-[a-z0-9]{8,32}$")
    version: int = Field(ge=1, le=99)
    goal: str = Field(min_length=1, max_length=240)
    plan_snapshot: str = Field(min_length=1, max_length=640)
    verified_facts: list[str] = Field(default_factory=list, max_length=12)
    unresolved_assumptions: list[str] = Field(default_factory=list, max_length=8)
    candidate_actions: list[str] = Field(default_factory=list, max_length=4)
    executed_effects: list[str] = Field(default_factory=list, max_length=8)
    memory_hints: list[str] = Field(default_factory=list, max_length=6)
    available_skills: list[str] = Field(default_factory=list, max_length=8)
    token_estimate_before: int = Field(ge=0)
    token_estimate_after: int = Field(ge=0)
    fact_reference_retention: float = Field(ge=0.0, le=1.0)
    source_artifact_refs: list[str] = Field(default_factory=list, max_length=16)
    expires_at: float

    @field_validator(
        "goal",
        "plan_snapshot",
    )
    @classmethod
    def validate_context_text(cls, value: str) -> str:
        return ensure_safe_summary(value, max_length=640)

    @field_validator(
        "verified_facts",
        "unresolved_assumptions",
        "candidate_actions",
        "executed_effects",
        "memory_hints",
    )
    @classmethod
    def validate_context_lists(cls, values: list[str]) -> list[str]:
        return [ensure_safe_summary(value) for value in values]


class AgentTask(BaseModel):
    """Internal persisted Task Runtime state.

    ``owner_ref`` and ``session_ref`` are one-way references. The original goal
    is represented by a digest plus a safe normalized summary only.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^task-[a-z0-9]{8,32}$")
    task_ref: str = Field(pattern=r"^taskref-[a-z0-9]{8,32}$")
    owner_ref: str = Field(pattern=r"^owner-[a-f0-9]{24}$")
    session_ref: str = Field(pattern=r"^session-[a-f0-9]{24}$")
    parent_task_id: str | None = Field(default=None, pattern=r"^task-[a-z0-9]{8,32}$")
    goal_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    normalized_goal: str = Field(min_length=1, max_length=240)
    success_criteria: list[str] = Field(default_factory=list, max_length=6)
    status: AgentTaskStatus = "created"
    plan_version: int = Field(default=0, ge=0, le=99)
    execution_budget: TaskExecutionBudget = Field(default_factory=TaskExecutionBudget)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    expires_at: float
    context_pack_ref: str | None = None
    working_memory_ref: str | None = None
    artifact_refs: list[str] = Field(default_factory=list, max_length=32)
    pending_action_ref: str | None = None
    waiting_question: str | None = Field(default=None, max_length=240)
    final_outcome: str | None = Field(default=None, max_length=320)
    limitation_codes: list[str] = Field(default_factory=list, max_length=8)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    context_model_calls: int = Field(default=0, ge=0)
    critic_calls: int = Field(default=0, ge=0)
    invalid_decisions: int = Field(default=0, ge=0)
    started_at: float = Field(default_factory=time.time)

    @field_validator("normalized_goal", "waiting_question", "final_outcome")
    @classmethod
    def validate_task_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_safe_summary(value, max_length=320)

    @field_validator("success_criteria")
    @classmethod
    def validate_success_criteria(cls, values: list[str]) -> list[str]:
        return [ensure_safe_summary(value) for value in values]


class SkillCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    arguments: dict[str, Any] = Field(default_factory=dict, max_length=8)


class ExecutorDecision(BaseModel):
    """Strict model decision accepted by the Runtime after validation."""

    model_config = ConfigDict(extra="forbid")

    decision: ExecutorDecisionName
    reason_summary: str = Field(min_length=1, max_length=240)
    target_node_id: str | None = Field(default=None, pattern=r"^node-[a-z0-9]{8,32}$")
    skill_calls: list[SkillCall] = Field(default_factory=list, max_length=4)
    new_plan_nodes: list[TaskPlanNode] = Field(default_factory=list, max_length=4)
    artifact_refs: list[str] = Field(default_factory=list, max_length=12)
    expected_next_observation: str | None = Field(default=None, max_length=240)
    action_skill: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{2,63}$")
    action_arguments: dict[str, Any] = Field(default_factory=dict, max_length=8)
    user_question: str | None = Field(default=None, max_length=240)

    @field_validator("reason_summary", "expected_next_observation", "user_question")
    @classmethod
    def validate_decision_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_safe_summary(value)

    @model_validator(mode="after")
    def validate_shape_for_decision(self) -> "ExecutorDecision":
        if self.decision == "call_skill" and not self.skill_calls:
            raise ValueError("调用 Skill 的决策必须包含调用项")
        if self.decision == "propose_action" and not self.action_skill:
            raise ValueError("行动提案必须指定 action_skill")
        if self.decision == "ask_user" and not self.user_question:
            raise ValueError("澄清决策必须包含用户问题")
        if self.decision == "revise_plan" and not self.new_plan_nodes:
            raise ValueError("重规划必须包含新的计划节点")
        return self


class ResolutionCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_facts: list[str] = Field(default_factory=list, max_length=8)
    conflicting_artifacts: list[str] = Field(default_factory=list, max_length=8)
    unmet_success_criteria: list[str] = Field(default_factory=list, max_length=8)
    recommended_next_experiment: str | None = Field(default=None, max_length=240)
    candidate_ranking_rationale: str | None = Field(default=None, max_length=240)

    @field_validator(
        "missing_facts",
        "conflicting_artifacts",
        "unmet_success_criteria",
    )
    @classmethod
    def validate_critic_lists(cls, values: list[str]) -> list[str]:
        return [ensure_safe_summary(value) for value in values]

    @field_validator("recommended_next_experiment", "candidate_ranking_rationale")
    @classmethod
    def validate_critic_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_safe_summary(value)


class AgentTaskCreateRequest(BaseModel):
    """Incoming goal is transient: the Runtime persists only a safe summary/digest."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=2000)
    success_criteria: list[str] = Field(default_factory=list, max_length=6)


class AgentTaskContinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)


class AgentTaskConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["confirm", "withdraw"]


class AgentTaskPlanNodeView(BaseModel):
    node_label: str
    goal: str
    status: PlanNodeStatus


class AgentTaskArtifactView(BaseModel):
    kind: str
    summary: str
    source_skill: str
    factuality: ArtifactFactuality


class AgentTaskActionView(BaseModel):
    action_skill: str
    expected_effect: str
    user_explanation: str
    confirmation_status: ConfirmationStatus


class AgentTaskContextView(BaseModel):
    """Safe Context Pack metrics shown in the Agent workspace.

    This is intentionally a measurement projection, not the Context Pack
    itself.  It lets a customer/developer see that facts were curated without
    exposing source references, raw tool payloads, retrieved policy text or a
    model prompt.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, le=99)
    token_estimate_before: int = Field(ge=0)
    token_estimate_after: int = Field(ge=0)
    fact_reference_retention: float = Field(ge=0.0, le=1.0)


class AgentTaskPublicView(BaseModel):
    """Customer DTO: no internal IDs, raw facts, messages, prompts or traces."""

    task_ref: str
    goal: str
    status: AgentTaskStatus
    plan_version: int
    plan_nodes: list[AgentTaskPlanNodeView] = Field(default_factory=list)
    artifacts: list[AgentTaskArtifactView] = Field(default_factory=list)
    open_question: str | None = None
    action: AgentTaskActionView | None = None
    outcome: str | None = None
    limitation_codes: list[str] = Field(default_factory=list)
    execution_summary: str | None = None
    context_summary: AgentTaskContextView | None = None


class AgentTaskEvent(BaseModel):
    """Safe event suitable for polling/SSE without internal payload leakage."""

    event_type: Literal[
        "task_created",
        "plan_updated",
        "skill_observed",
        "waiting_for_user",
        "action_proposed",
        "action_committed",
        "task_completed",
        "task_blocked",
        "task_failed",
    ]
    task_ref: str
    occurred_at: float = Field(default_factory=time.time)
    summary: str = Field(min_length=1, max_length=240)

    @field_validator("summary")
    @classmethod
    def validate_event_summary(cls, value: str) -> str:
        return ensure_safe_summary(value)
