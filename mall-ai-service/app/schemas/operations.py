"""Strict contracts for the separately authorized operations role."""

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StrictOperationsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OperatorLoginRequest(StrictOperationsModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)


class OperatorProfile(StrictOperationsModel):
    username: str = Field(min_length=1, max_length=64)
    capabilities: list[Literal["operations_analysis", "case_review"]] = Field(
        default_factory=list, max_length=4
    )


class OperatorLoginResponse(StrictOperationsModel):
    authorization: str = Field(min_length=8)
    operator: OperatorProfile


class CaseHandoffView(StrictOperationsModel):
    """Only the non-sensitive projection returned by mall-admin."""

    case_id: str = Field(
        validation_alias=AliasChoices("case_id", "caseId"),
        min_length=36,
        max_length=36,
    )
    source_flow: Literal["customer_diagnosis"] = Field(
        validation_alias=AliasChoices("source_flow", "sourceFlow")
    )
    diagnosis_category: Literal[
        "delivery_in_transit",
        "delivery_exception",
        "order_state_review",
        "facts_incomplete",
        "policy_consultation",
        "policy_insufficient",
        "tool_failure",
        "needs_order_identifier",
    ] = Field(validation_alias=AliasChoices("diagnosis_category", "diagnosisCategory"))
    evidence_status: Literal["complete", "partial", "insufficient", "unavailable"] = Field(
        validation_alias=AliasChoices("evidence_status", "evidenceStatus")
    )
    handoff_reason: Literal["tool_failure", "insufficient_evidence", "manual_review"] = Field(
        validation_alias=AliasChoices("handoff_reason", "handoffReason")
    )
    requires_human_review: Literal[True] = Field(
        validation_alias=AliasChoices("requires_human_review", "requiresHumanReview")
    )
    case_status: Literal["OPEN", "CLOSED"] = Field(
        validation_alias=AliasChoices("case_status", "caseStatus")
    )
    schema_version: Literal["1"] = Field(
        validation_alias=AliasChoices("schema_version", "schemaVersion")
    )
    created_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("created_at", "createdAt"),
    )
    updated_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )


class HandoffCategorySummary(StrictOperationsModel):
    """Java-calculated count and percentage for one formal diagnosis category."""

    category: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=0)
    percentage: float = Field(ge=0, le=100)


class HandoffOverview(StrictOperationsModel):
    """Deduplicated human-handoff aggregate, never a model-estimated number."""

    window_days: Literal[7, 30] = Field(
        validation_alias=AliasChoices("window_days", "windowDays")
    )
    window_start: str = Field(
        validation_alias=AliasChoices("window_start", "windowStart"), min_length=10, max_length=40
    )
    window_end: str = Field(
        validation_alias=AliasChoices("window_end", "windowEnd"), min_length=10, max_length=40
    )
    total_unique_handoffs: int = Field(
        validation_alias=AliasChoices("total_unique_handoffs", "totalUniqueHandoffs"), ge=0
    )
    categories: list[HandoffCategorySummary] = Field(default_factory=list, max_length=16)


class OperationsMetrics(StrictOperationsModel):
    window_days: Literal[7, 30] = Field(
        validation_alias=AliasChoices("window_days", "windowDays")
    )
    after_sales_by_status: dict[str, int] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("after_sales_by_status", "afterSalesByStatus"),
    )
    reason_counts: dict[str, int] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("reason_counts", "reasonCounts"),
    )
    outbox_by_status: dict[str, int] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("outbox_by_status", "outboxByStatus"),
    )
    delivery_by_status: dict[str, int] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("delivery_by_status", "deliveryByStatus"),
    )
    handoff_overview: HandoffOverview | None = Field(
        default=None,
        validation_alias=AliasChoices("handoff_overview", "handoffOverview"),
    )


RiskCode = Literal[
    "pending_review_pressure",
    "delivery_backlog",
    "outbox_backlog",
    "data_insufficient",
    "none",
]
RiskSeverity = Literal["low", "medium", "high"]


class OperationsRiskFlag(StrictOperationsModel):
    code: RiskCode
    severity: RiskSeverity
    rationale: str = Field(min_length=1, max_length=180)


class OperationsAnalysisDraft(StrictOperationsModel):
    summary: str = Field(min_length=1, max_length=300)
    risk_flags: list[OperationsRiskFlag] = Field(default_factory=list, max_length=3)
    recommended_human_attention: list[str] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list, max_length=3)


class OperationsAnalysisResponse(StrictOperationsModel):
    case: CaseHandoffView
    metrics: OperationsMetrics
    draft: OperationsAnalysisDraft
