"""Strict contracts for local AgentOps governance.

All data here is either synthetic or a deliberately minimal reference.  These
models never accept raw customer messages, JWTs, order identifiers, RAG text or
production traces.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.quality import EvalCase, QualityEvaluationMode


class StrictAgentOpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


FeedbackReasonCode = Literal[
    "factual_mismatch",
    "policy_not_supported",
    "unclear_explanation",
    "response_too_slow",
    "tool_unavailable",
    "other",
]
FeedbackReviewStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class EvaluationProfile(StrictAgentOpsModel):
    """A versioned offline evaluation configuration, never an online router."""

    profile_id: str = Field(
        validation_alias=AliasChoices("profile_id", "profileId"),
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    version: str = Field(min_length=2, max_length=32, pattern=r"^v[0-9]+(?:\.[0-9]+){0,2}$")
    execution_mode: QualityEvaluationMode = Field(
        validation_alias=AliasChoices("execution_mode", "executionMode")
    )
    model_ref: Literal["none", "configured_deepseek"] = Field(
        validation_alias=AliasChoices("model_ref", "modelRef")
    )
    prompt_version: str = Field(
        validation_alias=AliasChoices("prompt_version", "promptVersion"), min_length=3, max_length=64
    )
    rag_profile_version: str = Field(
        validation_alias=AliasChoices("rag_profile_version", "ragProfileVersion"), min_length=3, max_length=64
    )
    tool_schema_version: str = Field(
        validation_alias=AliasChoices("tool_schema_version", "toolSchemaVersion"), min_length=3, max_length=64
    )
    max_model_calls: int = Field(
        validation_alias=AliasChoices("max_model_calls", "maxModelCalls"), ge=0, le=7
    )
    max_tool_calls: int = Field(
        validation_alias=AliasChoices("max_tool_calls", "maxToolCalls"), ge=0, le=7
    )
    timeout_seconds: int = Field(
        validation_alias=AliasChoices("timeout_seconds", "timeoutSeconds"), ge=1, le=120
    )
    max_attempts: int = Field(
        validation_alias=AliasChoices("max_attempts", "maxAttempts"), ge=1, le=3
    )
    active: bool = True


class CustomerFeedbackRequest(StrictAgentOpsModel):
    response_ref: str = Field(
        validation_alias=AliasChoices("response_ref", "responseRef"),
        min_length=36,
        max_length=36,
        pattern=r"^[a-f0-9-]{36}$",
    )
    helpful: bool
    reason_code: FeedbackReasonCode = Field(
        validation_alias=AliasChoices("reason_code", "reasonCode")
    )
    consent: Literal[True]


class CustomerFeedbackView(StrictAgentOpsModel):
    feedback_id: str = Field(
        validation_alias=AliasChoices("feedback_id", "feedbackId"), min_length=36, max_length=36
    )
    response_ref: str = Field(
        validation_alias=AliasChoices("response_ref", "responseRef"), min_length=36, max_length=36
    )
    helpful: bool
    reason_code: FeedbackReasonCode = Field(
        validation_alias=AliasChoices("reason_code", "reasonCode")
    )
    review_status: FeedbackReviewStatus = Field(
        validation_alias=AliasChoices("review_status", "reviewStatus")
    )
    created_at: datetime = Field(validation_alias=AliasChoices("created_at", "createdAt"))


class FeedbackCandidateCreateRequest(StrictAgentOpsModel):
    """Developer-supplied synthetic abstraction of one consented feedback.

    The submitted EvalCase is later replayed with mocks only.  It must not be a
    copy of a customer conversation or any production fact payload.
    """

    feedback_id: str = Field(
        validation_alias=AliasChoices("feedback_id", "feedbackId"), min_length=36, max_length=36
    )
    sanitized_scenario: str = Field(
        validation_alias=AliasChoices("sanitized_scenario", "sanitizedScenario"),
        min_length=8,
        max_length=600,
    )
    eval_case: EvalCase = Field(validation_alias=AliasChoices("eval_case", "evalCase"))


class FeedbackCandidateView(StrictAgentOpsModel):
    candidate_id: str = Field(
        validation_alias=AliasChoices("candidate_id", "candidateId"), min_length=36, max_length=36
    )
    feedback_id: str = Field(
        validation_alias=AliasChoices("feedback_id", "feedbackId"), min_length=36, max_length=36
    )
    target_agent: Literal["customer_diagnosis", "operations_analysis"] = Field(
        validation_alias=AliasChoices("target_agent", "targetAgent")
    )
    sanitized_scenario: str = Field(
        validation_alias=AliasChoices("sanitized_scenario", "sanitizedScenario"), min_length=8, max_length=600
    )
    review_status: FeedbackReviewStatus = Field(
        validation_alias=AliasChoices("review_status", "reviewStatus")
    )
    eval_case_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("eval_case_id", "evalCaseId"),
        min_length=3,
        max_length=96,
    )
    created_at: datetime = Field(validation_alias=AliasChoices("created_at", "createdAt"))
    reviewed_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("reviewed_at", "reviewedAt"),
    )


class EvaluationProfileExperimentRequest(StrictAgentOpsModel):
    profile_ids: list[str] = Field(
        validation_alias=AliasChoices("profile_ids", "profileIds"), min_length=1, max_length=2
    )
    enable_ai_failure_analysis: bool = Field(
        default=False,
        validation_alias=AliasChoices("enable_ai_failure_analysis", "enableAiFailureAnalysis"),
    )


class EvaluationProfileExperiment(StrictAgentOpsModel):
    experiment_id: str = Field(
        validation_alias=AliasChoices("experiment_id", "experimentId"), min_length=36, max_length=36
    )
    suite_version: str = Field(
        validation_alias=AliasChoices("suite_version", "suiteVersion"), min_length=1, max_length=80
    )
    profile_ids: list[str] = Field(
        validation_alias=AliasChoices("profile_ids", "profileIds"), min_length=1, max_length=2
    )
    run_ids: list[str] = Field(
        validation_alias=AliasChoices("run_ids", "runIds"), min_length=1, max_length=2
    )
    created_at: datetime = Field(validation_alias=AliasChoices("created_at", "createdAt"))


class LocalMetricView(StrictAgentOpsModel):
    name: str = Field(min_length=3, max_length=64)
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    p50_ms: int | None = Field(default=None, validation_alias=AliasChoices("p50_ms", "p50Ms"), ge=0)
    p95_ms: int | None = Field(default=None, validation_alias=AliasChoices("p95_ms", "p95Ms"), ge=0)
