"""Public and server-only models for one unified after-sales workflow.

The four application types deliberately share the same proposal and
confirmation mechanics. Differences are business data handled by Java, not
four copied Python workflows.
"""
import time
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.schemas.rag import RagSource


AfterSalesApplicationType = Literal[
    "cancel_refund",
    "return_refund",
    "exchange",
    "repair",
]
AfterSalesGoal = Literal["eligibility", "apply"]
AfterSalesActionKind = Literal["create", "cancel", "modify"]
AfterSalesDraftField = Literal["application_type", "order_sn", "product", "reason"]
AfterSalesApplicationStatus = Literal[
    "pending_review",
    "accepted",
    "completed",
    "rejected",
    "cancelled",
    "unknown",
]
AfterSalesFulfillmentStatus = Literal[
    "not_started",
    "processing",
    "succeeded",
    "failed",
    "manual_required",
    "unknown",
]


class AfterSalesFieldCandidate(BaseModel):
    """One untrusted LLM candidate plus a contiguous user-text evidence span."""

    value: str | None = Field(default=None, max_length=500)
    evidence_span: str | None = Field(default=None, max_length=500)

    @field_validator("value", "evidence_span", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("candidate fields must be strings")
        value = value.strip()
        return value or None


class AfterSalesRequestCandidateExtraction(BaseModel):
    goal: AfterSalesFieldCandidate | None = None
    application_type: AfterSalesFieldCandidate | None = None
    order_sn: AfterSalesFieldCandidate | None = None
    product_hint: AfterSalesFieldCandidate | None = None
    reason: AfterSalesFieldCandidate | None = None
    description: AfterSalesFieldCandidate | None = None


class AfterSalesRequestExtraction(BaseModel):
    goal: AfterSalesGoal | None = None
    application_type: AfterSalesApplicationType | None = None
    order_sn: str | None = None
    product_hint: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("order_sn", "product_hint", "reason", "description", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("字段必须是字符串")
        value = value.strip()
        return value or None


class AfterSalesProductOption(BaseModel):
    product_name: str
    product_attr: str | None = None


class PendingAfterSalesDraft(BaseModel):
    """Owner-bound, server-only draft collected before a proposal is made."""

    draft_id: str
    owner_fingerprint: str
    goal: AfterSalesGoal | None = None
    application_type: AfterSalesApplicationType | None = None
    order_sn: str | None = None
    product_hint: str | None = None
    reason: str | None = None
    description: str | None = Field(default=None, max_length=500)
    product_options: list[AfterSalesProductOption] = Field(default_factory=list)
    expires_at: float
    updated_at: float = Field(default_factory=time.time)


class AfterSalesDraftView(BaseModel):
    draft_id: str
    status: Literal["collecting_information"] = "collecting_information"
    missing_fields: list[AfterSalesDraftField]
    goal: AfterSalesGoal | None = None
    application_type: AfterSalesApplicationType | None = None
    application_type_label: str | None = None
    order_sn: str | None = None
    product_options: list[AfterSalesProductOption] = Field(default_factory=list)


class PendingAfterSalesProposal(BaseModel):
    """Server-only confirmed-request material; browser never sees IDs or keys."""

    proposal_id: str
    goal: Literal["apply"] = "apply"
    application_type: AfterSalesApplicationType
    order_sn: str
    order_item_id: int | None = None
    product_name: str
    product_attr: str | None = None
    reason: str
    description: str
    owner_fingerprint: str
    session_fingerprint: str
    content_hash: str = Field(min_length=64, max_length=64)
    expires_at: float
    submission_state: Literal["awaiting_confirmation", "submission_unknown"] = (
        "awaiting_confirmation"
    )


class AfterSalesProposalView(BaseModel):
    application_type: AfterSalesApplicationType
    application_type_label: str
    order_sn: str
    product_name: str
    product_attr: str | None = None
    reason: str
    description: str
    status: Literal["awaiting_confirmation"] = "awaiting_confirmation"


class PendingAfterSalesAction(BaseModel):
    """Server-only cancel/modify intent bound to one user and conversation.

    A browser never sees ``action_id`` or ``content_hash``.  They make a
    confirmation replay-safe while Java independently enforces membership,
    lifecycle and idempotency.
    """

    action_id: str = Field(min_length=32, max_length=64)
    action: Literal["cancel", "modify"]
    application_id: int = Field(gt=0)
    owner_fingerprint: str
    session_fingerprint: str
    content_hash: str = Field(min_length=64, max_length=64)
    reason: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    expires_at: float
    execution_state: Literal["awaiting_confirmation", "execution_unknown"] = (
        "awaiting_confirmation"
    )


class PendingAfterSalesModificationDraft(BaseModel):
    """Server-only target selected before the customer supplies a new narrative.

    It is deliberately not a write proposal.  Once a replacement reason or a
    compliant supplement exists, the service turns it into
    :class:`PendingAfterSalesAction` with a content hash and an explicit
    confirmation card.
    """

    application_id: int = Field(gt=0)
    application_type_label: str = Field(min_length=1, max_length=100)
    owner_fingerprint: str
    session_fingerprint: str
    expires_at: float


class AfterSalesPendingActionView(BaseModel):
    """Customer-safe confirmation card for a non-create write action."""

    action: Literal["cancel", "modify"]
    application_id: int = Field(gt=0)
    application_type_label: str
    status: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    impact_summary: str
    reason: str | None = None
    description: str | None = None


class AfterSalesApplicationCandidateView(BaseModel):
    """Minimal target choice. It never carries internal order or member IDs."""

    application_id: int = Field(gt=0)
    application_type_label: str
    status_label: str
    product_name: str | None = None
    created_at: int | None = None


class PendingAfterSalesSelection(BaseModel):
    """Server-only disambiguation state for a member-owned application."""

    selection_id: str = Field(min_length=32, max_length=64)
    purpose: Literal["status", "cancel", "modify", "follow_up"]
    owner_fingerprint: str
    session_fingerprint: str
    candidates: list[AfterSalesApplicationCandidateView] = Field(min_length=1, max_length=10)
    reason: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    expires_at: float


class ActiveAfterSalesApplicationTarget(BaseModel):
    """A recent, server-verified application target for one member session.

    This is not a browser parameter and is deliberately kept outside the LLM
    context.  It only lets a later status/follow-up request refer to the
    application the customer has already selected in this same protected
    conversation.
    """

    application_id: int = Field(gt=0)
    owner_fingerprint: str
    session_fingerprint: str
    expires_at: float


class AfterSalesSelectionView(BaseModel):
    """Client-safe request to choose one of the shown member-owned records."""

    purpose: Literal["status", "cancel", "modify", "follow_up"]
    candidates: list[AfterSalesApplicationCandidateView] = Field(min_length=1, max_length=10)


class AfterSalesEligibilityView(BaseModel):
    order_sn: str = Field(validation_alias=AliasChoices("order_sn", "orderSn"))
    application_type: AfterSalesApplicationType = Field(
        validation_alias=AliasChoices("application_type", "applicationType")
    )
    application_type_label: str = Field(
        validation_alias=AliasChoices("application_type_label", "applicationTypeLabel")
    )
    order_status: str = Field(validation_alias=AliasChoices("order_status", "orderStatus"))
    eligible: bool
    requires_product_selection: bool = Field(
        validation_alias=AliasChoices(
            "requires_product_selection", "requiresProductSelection"
        )
    )
    decision: Literal["eligible_to_apply", "not_eligible", "needs_product_selection"]
    message: str
    product_name: str | None = Field(
        default=None, validation_alias=AliasChoices("product_name", "productName")
    )
    product_attr: str | None = Field(
        default=None, validation_alias=AliasChoices("product_attr", "productAttr")
    )


class AfterSalesApplicationView(BaseModel):
    application_id: int = Field(
        gt=0, validation_alias=AliasChoices("application_id", "applicationId")
    )
    order_sn: str = Field(
        min_length=1, validation_alias=AliasChoices("order_sn", "orderSn")
    )
    application_type: AfterSalesApplicationType = Field(
        validation_alias=AliasChoices("application_type", "applicationType")
    )
    application_type_label: str = Field(
        min_length=1,
        validation_alias=AliasChoices("application_type_label", "applicationTypeLabel"),
    )
    product_name: str | None = Field(
        default=None, validation_alias=AliasChoices("product_name", "productName")
    )
    product_attr: str | None = Field(
        default=None, validation_alias=AliasChoices("product_attr", "productAttr")
    )
    reason: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    status: AfterSalesApplicationStatus
    status_label: str = Field(
        min_length=1, validation_alias=AliasChoices("status_label", "statusLabel")
    )
    created_at: int | None = Field(
        default=None, validation_alias=AliasChoices("created_at", "createdAt")
    )
    updated_at: int | None = Field(
        default=None, validation_alias=AliasChoices("updated_at", "updatedAt")
    )
    handling_note: str | None = Field(
        default=None, validation_alias=AliasChoices("handling_note", "handlingNote")
    )
    fulfillment_status: AfterSalesFulfillmentStatus = Field(
        default="not_started",
        validation_alias=AliasChoices("fulfillment_status", "fulfillmentStatus"),
    )
    fulfillment_status_label: str = Field(
        default="待履约",
        validation_alias=AliasChoices(
            "fulfillment_status_label", "fulfillmentStatusLabel"
        ),
    )
    fulfillment_note: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fulfillment_note", "fulfillmentNote"),
    )
    can_cancel: bool = Field(
        validation_alias=AliasChoices("can_cancel", "canCancel")
    )
    can_modify: bool = Field(
        validation_alias=AliasChoices("can_modify", "canModify")
    )
    can_supplement: bool = Field(
        default=False,
        validation_alias=AliasChoices("can_supplement", "canSupplement"),
    )

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "未说明"
        return value.strip()

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("售后说明必须是字符串")
        return value.strip()


class AfterSalesApplicationModifyRequest(BaseModel):
    """Customer-safe updates allowed only while Java says an application is pending.

    The browser can never select a new order, product, type, status, or owner.
    It may only adjust the narrative fields that Java revalidates.
    """

    reason: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_optional_reason(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("售后原因必须是字符串")
        value = value.strip()
        return value or None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_optional_description(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("售后说明必须是字符串")
        return value.strip()

    @model_validator(mode="after")
    def require_one_changed_field(self) -> "AfterSalesApplicationModifyRequest":
        if self.reason is None and self.description is None:
            raise ValueError("请至少提供要修改的售后原因或说明")
        return self


class AfterSalesFlowResult(BaseModel):
    answer: str
    draft: AfterSalesDraftView | None = None
    proposal: AfterSalesProposalView | None = None
    eligibility: AfterSalesEligibilityView | None = None
    submitted_application: AfterSalesApplicationView | None = None
    completed_action: AfterSalesActionKind | None = None
    pending_action: AfterSalesPendingActionView | None = None
    selection: AfterSalesSelectionView | None = None
    applications: list[AfterSalesApplicationView] | None = None
    policy_sources: list[RagSource] = Field(default_factory=list)
