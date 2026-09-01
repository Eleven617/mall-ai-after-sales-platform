"""Publicly safe results for the evidence-driven order diagnosis graph."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.facts import VerifiedFactCard


DiagnosisCategory = Literal[
    "delivery_in_transit",
    "delivery_exception",
    "order_state_review",
    "facts_incomplete",
    "policy_consultation",
    "policy_insufficient",
    "tool_failure",
    "needs_order_identifier",
]
DiagnosisEvidenceStatus = Literal["complete", "partial", "insufficient", "unavailable"]
DiagnosisNextStep = Literal[
    "continue_after_sales",
    "contact_human",
    "retry_diagnosis",
    "provide_order_sn",
]
DiagnosisHandoffReason = Literal[
    "tool_failure",
    "insufficient_evidence",
    "manual_review",
]


class DiagnosisPolicySource(BaseModel):
    """A source label safe to expose to a customer or support agent."""

    document_name: str
    section_path: str


class DiagnosisHandoff(BaseModel):
    """A short, privacy-safe handoff summary without raw tool payloads."""

    reason: DiagnosisHandoffReason
    summary: str
    verified_source_types: list[str] = Field(default_factory=list)


class DiagnosisResult(BaseModel):
    """Structured diagnosis output produced after the graph reaches a stop node."""

    category: DiagnosisCategory
    evidence_status: DiagnosisEvidenceStatus
    verified_facts: list[VerifiedFactCard] = Field(default_factory=list)
    policy_sources: list[DiagnosisPolicySource] = Field(default_factory=list)
    allowed_next_steps: list[DiagnosisNextStep] = Field(default_factory=list)
    handoff: DiagnosisHandoff | None = None
