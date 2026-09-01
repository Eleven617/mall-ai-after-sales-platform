import time
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.after_sales_application import (
    ActiveAfterSalesApplicationTarget,
    PendingAfterSalesDraft,
    PendingAfterSalesAction,
    PendingAfterSalesProposal,
    PendingAfterSalesSelection,
    PendingAfterSalesModificationDraft,
)
from app.schemas.tool import ToolCall


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
    updated_at: float = Field(default_factory=time.time)
    expires_at: float = 0.0


class ConversationModelContext(BaseModel):
    """Only the safe, useful subset of session state sent to a model."""

    summary: str = ""
    facts: dict[str, str] = Field(default_factory=dict)
    active_task: str | None = None
    recent_messages: list[ConversationMessage] = Field(default_factory=list)
