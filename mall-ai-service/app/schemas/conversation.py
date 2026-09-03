import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.after_sales_application import (
    ActiveAfterSalesApplicationTarget,
    PendingAfterSalesDraft,
    PendingAfterSalesAction,
    PendingAfterSalesProposal,
    PendingAfterSalesSelection,
    PendingAfterSalesModificationDraft,
)
from app.schemas.tool import ToolCall
from app.schemas.task_orchestration import TaskModelReference, TaskSnapshot, TransactionGate


class TaskRuntimePayload(BaseModel):
    """Server-only task payload kept out of P0 model context and public DTOs.

    This allows one active and one paused task to keep their independently
    owner-bound workflow payloads without exposing an identifier, proposal key,
    original chat text, or tool result to the browser or the routing model.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=32, max_length=64)
    pending_tool_call: ToolCall | None = None
    pending_after_sales_draft: PendingAfterSalesDraft | None = None
    pending_after_sales_selection: PendingAfterSalesSelection | None = None
    pending_after_sales_modification_draft: PendingAfterSalesModificationDraft | None = None
    expires_at: float


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)
    created_at: float = Field(default_factory=time.time)


class ConversationState(BaseModel):
    """Durable state for one customer-service session.

    Business facts and workflow state are structured fields. They are never kept
    only inside an LLM-generated summary.
    """

    session_id: str
    summary: str = ""
    recent_messages: list[ConversationMessage] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)
    pending_tool_call: ToolCall | None = None
    pending_after_sales_draft: PendingAfterSalesDraft | None = None
    pending_after_sales_proposal: PendingAfterSalesProposal | None = None
    pending_after_sales_action: PendingAfterSalesAction | None = None
    pending_after_sales_selection: PendingAfterSalesSelection | None = None
    pending_after_sales_modification_draft: PendingAfterSalesModificationDraft | None = None
    active_after_sales_application: ActiveAfterSalesApplicationTarget | None = None
    # v1 payloads are server-owned only.  The legacy pending_* fields remain as
    # a short-lived execution adapter while a task is actively resumed.
    active_task: TaskSnapshot | None = None
    paused_task: TaskSnapshot | None = None
    task_payloads: dict[str, TaskRuntimePayload] = Field(default_factory=dict, max_length=2)
    transaction_gate: TransactionGate | None = None
    task_orchestration_version: str = "task_orchestration_v1"
    updated_at: float = Field(default_factory=time.time)
    expires_at: float = 0.0


class ConversationModelContext(BaseModel):
    """Only the safe, useful subset of session state sent to a model."""

    summary: str = ""
    facts: dict[str, str] = Field(default_factory=dict)
    active_task: TaskModelReference | None = None
    paused_task: TaskModelReference | None = None
    transaction_gate: TransactionGate | None = None
    recent_messages: list[ConversationMessage] = Field(default_factory=list)
