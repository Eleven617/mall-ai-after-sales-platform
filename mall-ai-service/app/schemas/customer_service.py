from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agent import VerifiedFactCard
from app.schemas.after_sales_application import (
    AfterSalesActionKind,
    AfterSalesApplicationView,
    AfterSalesDraftView,
    AfterSalesEligibilityView,
    AfterSalesPendingActionView,
    AfterSalesProposalView,
    AfterSalesSelectionView,
)
from app.schemas.diagnosis import (
    DiagnosisCategory,
    DiagnosisEvidenceStatus,
    DiagnosisNextStep,
    DiagnosisResult,
)
from app.schemas.intent import IntentResponse
from app.schemas.rag import RagSource


class CustomerServiceRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, examples=["chat-7f2e"])
    message: str = Field(min_length=1, examples=["帮我查订单 20240617001 的物流"])


class PendingActionView(BaseModel):
    """A client-safe action for a read-only task that awaits one identifier."""

    kind: Literal["awaiting_order_sn", "awaiting_sku_id"]
    label: str
    # Safe UI capability only; it never contains a checkpoint/thread ID or
    # customer data.  The customer can understand that a later reply resumes
    # this read-only task rather than opening a hidden write workflow.
    resumable: bool = False
    cancel_message: Literal["取消查询"] = "取消查询"


class CustomerServiceResponse(BaseModel):
    message: str
    answer: str
    intent: IntentResponse
    tool_result: dict | None = None
    verified_facts: list[VerifiedFactCard] | None = None
    rag_context: list[str] | None = None
    rag_sources: list[RagSource] | None = None
    after_sales_draft: AfterSalesDraftView | None = None
    after_sales_proposal: AfterSalesProposalView | None = None
    after_sales_eligibility: AfterSalesEligibilityView | None = None
    submitted_after_sales_application: AfterSalesApplicationView | None = None
    after_sales_completed_action: AfterSalesActionKind | None = None
    after_sales_pending_action: AfterSalesPendingActionView | None = None
    after_sales_selection: AfterSalesSelectionView | None = None
    after_sales_applications: list[AfterSalesApplicationView] | None = None
    pending_action: PendingActionView | None = None
    diagnosis: DiagnosisResult | None = None


class CustomerDiagnosisHandoff(BaseModel):
    """Customer-safe handoff text with no internal source-type details."""

    summary: str


class CustomerDiagnosisView(BaseModel):
    """Customer diagnosis excludes source labels and embedded graph internals."""

    category: DiagnosisCategory
    evidence_status: DiagnosisEvidenceStatus
    allowed_next_steps: list[DiagnosisNextStep] = Field(default_factory=list)
    handoff: CustomerDiagnosisHandoff | None = None


class CustomerServicePublicResponse(BaseModel):
    """The only customer-facing response serialized by the HTTP router."""

    answer: str
    verified_facts: list[VerifiedFactCard] | None = None
    after_sales_draft: AfterSalesDraftView | None = None
    after_sales_proposal: AfterSalesProposalView | None = None
    after_sales_eligibility: AfterSalesEligibilityView | None = None
    submitted_after_sales_application: AfterSalesApplicationView | None = None
    after_sales_completed_action: AfterSalesActionKind | None = None
    after_sales_pending_action: AfterSalesPendingActionView | None = None
    after_sales_selection: AfterSalesSelectionView | None = None
    after_sales_applications: list[AfterSalesApplicationView] | None = None
    pending_action: PendingActionView | None = None
    diagnosis: CustomerDiagnosisView | None = None
    # Opaque, short-lived browser capability for structured feedback only. It
    # is not a session ID, trace ID, order identifier or business action token.
    response_ref: str | None = None


def to_public_customer_service_response(
    response: CustomerServiceResponse,
) -> CustomerServicePublicResponse:
    """Project the internal orchestration result onto the browser contract."""
    diagnosis = (
        CustomerDiagnosisView(
            category=response.diagnosis.category,
            evidence_status=response.diagnosis.evidence_status,
            allowed_next_steps=response.diagnosis.allowed_next_steps,
            handoff=(
                CustomerDiagnosisHandoff(summary=response.diagnosis.handoff.summary)
                if response.diagnosis.handoff
                else None
            ),
        )
        if response.diagnosis
        else None
    )
    return CustomerServicePublicResponse(
        answer=response.answer,
        verified_facts=response.verified_facts,
        after_sales_draft=response.after_sales_draft,
        after_sales_proposal=response.after_sales_proposal,
        after_sales_eligibility=response.after_sales_eligibility,
        submitted_after_sales_application=response.submitted_after_sales_application,
        after_sales_completed_action=response.after_sales_completed_action,
        after_sales_pending_action=response.after_sales_pending_action,
        after_sales_selection=response.after_sales_selection,
        after_sales_applications=response.after_sales_applications,
        pending_action=response.pending_action,
        diagnosis=diagnosis,
    )
