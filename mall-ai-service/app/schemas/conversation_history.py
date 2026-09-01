"""Customer-visible, member-scoped conversation-history contracts."""
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.customer_service import CustomerServicePublicResponse


class StrictConversationHistoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ConversationHistorySummary(StrictConversationHistoryModel):
    conversation_id: str = Field(
        validation_alias=AliasChoices("conversation_id", "conversationId"),
        min_length=36,
        max_length=36,
    )
    title: str = Field(min_length=1, max_length=64)
    message_count: int = Field(
        default=0,
        validation_alias=AliasChoices("message_count", "messageCount"),
        ge=0,
    )
    created_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("created_at", "createdAt"),
    )
    updated_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )


class ConversationHistoryMessage(StrictConversationHistoryModel):
    message_id: str = Field(
        validation_alias=AliasChoices("message_id", "messageId"),
        min_length=36,
        max_length=36,
    )
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)
    public_response: CustomerServicePublicResponse | None = Field(default=None)
    created_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("created_at", "createdAt"),
    )


class ConversationHistoryDetail(StrictConversationHistoryModel):
    conversation: ConversationHistorySummary
    messages: list[ConversationHistoryMessage] = Field(default_factory=list, max_length=500)
