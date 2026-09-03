"""Internal contracts for task-aware customer conversation orchestration.

The model sees only :class:`TaskSnapshot` summaries.  Mutable workflow data
(proposal material, identifiers, selected records, and tool arguments) stays in
the server-side conversation state and is never part of this contract.
"""
from __future__ import annotations

import time
import re
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.intent import ChatScope, IntentName, IntentResponse, IntentRoute, IntentToolCall


TaskKind = Literal[
    "order_diagnosis",
    "after_sales_draft",
    "after_sales_modification",
]
TaskStatus = Literal["active", "paused", "waiting_input"]
TaskRelation = Literal[
    "continue_active",
    "temporary_detour",
    "resume_paused",
    "start_new_task",
    "standalone_answer",
    "discard_active",
    "discard_paused",
    "resolve_task_conflict",
]
ConfirmationIntent = Literal["confirm", "cancel", "modify", "none"]
TaskRationaleCode = Literal[
    "active_task_match",
    "temporary_detour",
    "paused_task_match",
    "new_long_running_goal",
    "standalone_question",
    "explicit_task_abandonment",
    "task_conflict",
]
TransactionGateKind = Literal["proposal", "after_sales_action"]
TransactionGateStatus = Literal["awaiting_confirmation", "result_unknown"]


_FORBIDDEN_SNAPSHOT_TOKENS = {
    "token",
    "authorization",
    "bearer",
    "password",
    "phone",
    "address",
    "trace",
    "rag_context",
    "tool_result",
    "order_sn",
    "application_id",
}
_SAFE_KNOWN_SLOT_KEYS = {
    "awaiting_input",
    "tool_kind",
    "order_reference_present",
    "product_selected",
    "application_target_selected",
}
_LONG_IDENTIFIER_PATTERN = re.compile(r"(?<!\d)\d{6,}(?!\d)")


def _validate_model_visible_task_text(value: str | None) -> str | None:
    """Reject values that would turn a task summary into a data payload.

    Task snapshots are the only cross-turn context available to the P0 model.
    They are deliberately useful enough to describe *what* can be resumed, but
    must never carry a customer identifier, credential, original wording, or
    retrieved evidence into a later model call.
    """

    if value is None:
        return None
    normalized = value.strip()
    lowered = normalized.lower()
    if any(token in lowered for token in ("bearer ", "authorization", "password", "token=")):
        raise ValueError("任务摘要不能包含凭证")
    if _LONG_IDENTIFIER_PATTERN.search(normalized):
        raise ValueError("任务摘要不能包含完整业务标识")
    return normalized


class TaskSnapshot(BaseModel):
    """A minimal, model-readable summary of one incomplete task.

    It deliberately contains no raw customer message, credentials, full order
    identifier, RAG passage, tool payload, or browser-visible identifier.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=32, max_length=64)
    # Server-only ownership binding.  ConversationModelContext projects a
    # separate reference that excludes both fingerprints and task_id.
    owner_fingerprint: str = Field(min_length=32, max_length=128)
    session_fingerprint: str = Field(min_length=32, max_length=128)
    kind: TaskKind
    status: TaskStatus
    goal_summary: str = Field(min_length=1, max_length=240)
    known_slots: dict[str, str] = Field(default_factory=dict, max_length=8)
    pending_question: str | None = Field(default=None, max_length=240)
    completed_steps: list[str] = Field(default_factory=list, max_length=8)
    next_agent_hint: str | None = Field(default=None, max_length=240)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    expires_at: float

    @field_validator("goal_summary", "pending_question", "next_agent_hint")
    @classmethod
    def reject_sensitive_snapshot_text(cls, value: str | None) -> str | None:
        return _validate_model_visible_task_text(value)

    @field_validator("completed_steps")
    @classmethod
    def reject_sensitive_completed_steps(cls, values: list[str]) -> list[str]:
        return [_validate_model_visible_task_text(value) or "" for value in values]

    @model_validator(mode="after")
    def ensure_snapshot_is_safe(self) -> "TaskSnapshot":
        for key, value in self.known_slots.items():
            normalized = key.lower()
            if normalized in _FORBIDDEN_SNAPSHOT_TOKENS or normalized not in _SAFE_KNOWN_SLOT_KEYS:
                raise ValueError("任务摘要包含禁止字段")
            _validate_model_visible_task_text(value)
        return self


class TransactionGate(BaseModel):
    """An opaque pending business confirmation that never owns chat routing."""

    model_config = ConfigDict(extra="forbid")

    kind: TransactionGateKind
    status: TransactionGateStatus
    label: str = Field(min_length=1, max_length=120)
    expires_at: float
    updated_at: float = Field(default_factory=time.time)


class TaskModelReference(BaseModel):
    """The task subset P0 may use for semantic turn planning."""

    model_config = ConfigDict(extra="forbid")

    kind: TaskKind
    status: TaskStatus
    goal_summary: str
    known_slots: dict[str, str] = Field(default_factory=dict)
    pending_question: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    next_agent_hint: str | None = None

    @field_validator("goal_summary", "pending_question", "next_agent_hint")
    @classmethod
    def reject_sensitive_reference_text(cls, value: str | None) -> str | None:
        return _validate_model_visible_task_text(value)

    @field_validator("completed_steps")
    @classmethod
    def reject_sensitive_reference_steps(cls, values: list[str]) -> list[str]:
        return [_validate_model_visible_task_text(value) or "" for value in values]

    @model_validator(mode="after")
    def ensure_reference_slots_are_safe(self) -> "TaskModelReference":
        for key, value in self.known_slots.items():
            normalized = key.lower()
            if normalized in _FORBIDDEN_SNAPSHOT_TOKENS or normalized not in _SAFE_KNOWN_SLOT_KEYS:
                raise ValueError("任务引用包含禁止字段")
            _validate_model_visible_task_text(value)
        return self


class TurnPlan(BaseModel):
    """The bounded P0 decision for one customer message.

    ``rationale_code`` is a compact audit category, not chain-of-thought.  The
    plan can select a route but cannot carry a business write command.
    """

    model_config = ConfigDict(extra="forbid")

    business_intent: IntentName = Field(
        validation_alias=AliasChoices("business_intent", "intent")
    )
    # These four fields are deliberately required instead of inheriting a
    # plausible default.  A missing task relation is not safe to interpret as
    # "continue" or "start": the P0 model must make the turn decision
    # explicitly so the gateway can reject stale pre-upgrade JSON.
    task_relation: TaskRelation
    route: IntentRoute
    task_kind: TaskKind | None
    confirmation_intent: ConfirmationIntent
    rationale_code: TaskRationaleCode
    need_tool: bool
    tool_call: IntentToolCall | None
    reply: str | None
    chat_scope: ChatScope | None
    source: str = "llm"

    @property
    def intent(self) -> IntentName:
        """Backward-compatible view for existing route/render callers."""
        return self.business_intent

    @property
    def task_relation_code(self) -> TaskRelation:
        return self.task_relation

    @model_validator(mode="after")
    def validate_closed_contract(self) -> "TurnPlan":
        # Reuse the pre-existing route and tool allow-list contract instead of
        # making task orchestration a second authority.
        IntentResponse(
            intent=self.business_intent,
            route=self.route,
            need_tool=self.need_tool,
            tool_call=self.tool_call,
            reply=self.reply,
            chat_scope=self.chat_scope,
            source=self.source,
        )
        persistent_relations = {"continue_active", "resume_paused", "start_new_task"}
        one_turn_relations = {
            "temporary_detour",
            "standalone_answer",
            "discard_active",
            "discard_paused",
            "resolve_task_conflict",
        }
        if self.task_relation in persistent_relations:
            if self.task_kind is None:
                raise ValueError("多轮任务关系必须携带任务类型")
            if self.route not in {"agent", "ask_missing_info", "after_sales_flow"}:
                raise ValueError("多轮任务只能进入受控 Agent 或统一售后流程")
        if self.task_relation in one_turn_relations and self.task_kind is not None:
            raise ValueError("单轮任务关系不能携带持久任务类型")
        if self.route in {"agent", "ask_missing_info"} and self.task_kind not in {
            None,
            "order_diagnosis",
        }:
            raise ValueError("只读订单诊断路由只能使用订单诊断任务类型")
        if self.confirmation_intent != "none" and self.route != "after_sales_flow":
            raise ValueError("确认意图只能进入受控售后流程")
        if self.confirmation_intent != "none" and (
            self.task_relation != "standalone_answer" or self.task_kind is not None
        ):
            # A Proposal/action confirmation is a transaction-gate decision,
            # never a request to resume or create a conversational task.  This
            # makes a model's stale task label fail closed before it reaches
            # the Java write boundary.
            raise ValueError("确认意图不能伪装为继续或新建会话任务")
        return self

    def to_intent_response(self) -> IntentResponse:
        """Adapt the P0 plan to the existing internal response plumbing."""
        return IntentResponse(
            intent=self.business_intent,
            route=self.route,
            need_tool=self.need_tool,
            tool_call=self.tool_call,
            reply=self.reply,
            chat_scope=self.chat_scope,
            source=self.source,
        )


class TaskPublicState(BaseModel):
    """The small task indicator that may be serialized to the customer UI."""

    model_config = ConfigDict(extra="forbid")

    task_status: Literal["active", "paused", "none"] = "none"
    task_label: str | None = Field(default=None, max_length=80)
    task_hint: str | None = Field(default=None, max_length=240)
