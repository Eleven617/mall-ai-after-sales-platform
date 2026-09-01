"""Contracts for the isolated AI quality-evaluation Agent.

These models deliberately describe only synthetic cases and safe output
projections.  They are never populated from customer requests, production
traces, live handoffs, or business tables.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StrictQualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


QualityTargetAgent = Literal["customer_diagnosis", "operations_analysis"]
QualityCaseStatus = Literal["PASSED", "FAILED"]
QualityReviewStatus = Literal["PENDING", "APPROVED", "REJECTED"]
QualityEvaluationMode = Literal["contract_mock", "live_model_synthetic"]
ReadOnlyEvalToolName = Literal[
    "order_service",
    "logistics_service",
    "inventory_service",
    "rag_search",
]
EvalToolName = Literal[
    "order_service",
    "logistics_service",
    "inventory_service",
    "rag_search",
    "synthetic_unapproved_tool",
]
EvalModelBehavior = Literal[
    "tool_plan",
    "malformed_structure",
    "unavailable",
    "timeout",
]
EvalTerminalEvent = Literal[
    "tool_failed",
    "tool_blocked",
    "tool_invalid_arguments",
    "llm_unavailable",
    "timeout",
    "repeated_tool_call",
    "order_not_accessible",
    "handoff_prepared",
    "diagnosis_completed",
    "run_finished",
    "read_only_investigation_finished",
    "unrecognized_terminal_event",
]


class DeveloperLoginRequest(StrictQualityModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)


class DeveloperProfile(StrictQualityModel):
    username: str = Field(min_length=1, max_length=64)
    capabilities: list[Literal["quality_evaluation"]] = Field(
        default_factory=list, max_length=2
    )


class DeveloperLoginResponse(StrictQualityModel):
    authorization: str = Field(min_length=8)
    developer: DeveloperProfile


class EvalToolPlanStep(StrictQualityModel):
    name: EvalToolName
    arguments: dict[str, str] = Field(default_factory=dict)


class EvalMockToolResult(StrictQualityModel):
    tool_name: ReadOnlyEvalToolName = Field(
        validation_alias=AliasChoices("tool_name", "toolName", "tool")
    )
    result: dict[str, Any] = Field(default_factory=dict)


class EvalTrajectoryContract(StrictQualityModel):
    """Deterministic trajectory rules for a synthetic, read-only execution."""

    expected_tool_sequence: list[EvalToolName] = Field(
        default_factory=list,
        validation_alias=AliasChoices("expected_tool_sequence", "expectedToolSequence"),
        max_length=7,
    )
    max_steps: int = Field(
        default=7,
        validation_alias=AliasChoices("max_steps", "maxSteps"),
        ge=1,
        le=7,
    )
    no_repeated_tool_calls: bool = Field(
        default=True,
        validation_alias=AliasChoices("no_repeated_tool_calls", "noRepeatedToolCalls"),
    )
    must_stop_after_tool_error: bool = Field(
        default=False,
        validation_alias=AliasChoices("must_stop_after_tool_error", "mustStopAfterToolError"),
    )
    must_stop_after_no_evidence: bool = Field(
        default=False,
        validation_alias=AliasChoices("must_stop_after_no_evidence", "mustStopAfterNoEvidence"),
    )
    required_terminal_events: list[EvalTerminalEvent] = Field(
        default_factory=list,
        validation_alias=AliasChoices("required_terminal_events", "requiredTerminalEvents"),
        max_length=6,
    )


class QualityTrajectoryView(StrictQualityModel):
    """A safe projection of synthetic trace metadata for developer review."""

    tool_sequence: list[EvalToolName] = Field(default_factory=list, max_length=7)
    node_sequence: list[str] = Field(default_factory=list, max_length=20)
    step_count: int = Field(ge=0, le=7)
    terminal_events: list[EvalTerminalEvent] = Field(default_factory=list, max_length=8)


class EvalExpectedContract(StrictQualityModel):
    allowed_categories: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("allowed_categories", "allowedCategories"),
        max_length=8,
    )
    forbidden_categories: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("forbidden_categories", "forbiddenCategories"),
        max_length=8,
    )
    case_handoff_allowed: bool = Field(
        validation_alias=AliasChoices("case_handoff_allowed", "caseHandoffAllowed")
    )
    business_write_allowed: bool = Field(
        validation_alias=AliasChoices("business_write_allowed", "businessWriteAllowed")
    )
    forbidden_fields: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("forbidden_fields", "forbiddenFields"),
        max_length=16,
    )
    # A synthetic adversarial fixture may intentionally contain an unsafe
    # payload.  The evaluator passes only when the deterministic boundary
    # rejects it; this keeps the committed suite green while proving that the
    # comparator can fail closed.
    expected_rejection: bool = Field(
        default=False,
        validation_alias=AliasChoices("expected_rejection", "expectedRejection"),
    )
    # Expected detections are not regressions.  For example, a deliberately
    # unsafe synthetic handoff should surface ``sensitive_field_leak`` while
    # the overall case passes because the deterministic boundary rejected it.
    expected_rejection_codes: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "expected_rejection_codes", "expectedRejectionCodes"
        ),
        max_length=12,
    )


class EvalCase(StrictQualityModel):
    case_id: str = Field(
        validation_alias=AliasChoices("case_id", "caseId"), min_length=3, max_length=96
    )
    target_agent: QualityTargetAgent = Field(
        validation_alias=AliasChoices("target_agent", "targetAgent")
    )
    synthetic_input: str = Field(
        validation_alias=AliasChoices("synthetic_input", "syntheticInput"),
        min_length=1,
        max_length=600,
    )
    scripted_tool_plan: list[EvalToolPlanStep] = Field(
        default_factory=list,
        validation_alias=AliasChoices("scripted_tool_plan", "scriptedToolPlan"),
        max_length=4,
    )
    model_behavior: EvalModelBehavior = Field(
        default="tool_plan",
        validation_alias=AliasChoices("model_behavior", "modelBehavior"),
    )
    mock_tool_results: list[EvalMockToolResult] = Field(
        default_factory=list,
        validation_alias=AliasChoices("mock_tool_results", "mockToolResults"),
        max_length=4,
    )
    mock_metrics: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("mock_metrics", "mockMetrics"),
    )
    mock_case_handoff: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("mock_case_handoff", "mockCaseHandoff"),
    )
    mock_draft: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("mock_draft", "mockDraft"),
    )
    expected_contract: EvalExpectedContract = Field(
        validation_alias=AliasChoices("expected_contract", "expectedContract")
    )
    expected_trajectory: EvalTrajectoryContract = Field(
        default_factory=EvalTrajectoryContract,
        validation_alias=AliasChoices("expected_trajectory", "expectedTrajectory"),
    )
    schema_version: Literal["1"] = Field(
        validation_alias=AliasChoices("schema_version", "schemaVersion")
    )


class QualityFailureAnalysis(StrictQualityModel):
    failure_type: str = Field(
        validation_alias=AliasChoices("failure_type", "failureType"),
        min_length=1,
        max_length=80,
    )
    explanation: str = Field(min_length=1, max_length=360)
    candidate_regression_case: str = Field(
        validation_alias=AliasChoices(
            "candidate_regression_case", "candidateRegressionCase"
        ),
        min_length=1,
        max_length=360,
    )
    recommended_fix_area: str = Field(
        validation_alias=AliasChoices("recommended_fix_area", "recommendedFixArea"),
        min_length=1,
        max_length=180,
    )
    requires_human_approval: Literal[True] = Field(
        validation_alias=AliasChoices(
            "requires_human_approval", "requiresHumanApproval"
        )
    )


class QualityCaseResult(StrictQualityModel):
    case_id: str = Field(
        validation_alias=AliasChoices("case_id", "caseId"), min_length=3, max_length=96
    )
    target_agent: QualityTargetAgent = Field(
        validation_alias=AliasChoices("target_agent", "targetAgent")
    )
    status: QualityCaseStatus
    expected: str = Field(min_length=1, max_length=600)
    actual: str = Field(min_length=1, max_length=600)
    violations: list[str] = Field(default_factory=list, max_length=16)
    trajectory: QualityTrajectoryView | None = None
    failure_analysis: QualityFailureAnalysis | None = Field(
        default=None,
        validation_alias=AliasChoices("failure_analysis", "failureAnalysis"),
    )
    review_status: QualityReviewStatus = Field(
        default="PENDING",
        validation_alias=AliasChoices("review_status", "reviewStatus"),
    )
    expected_rejection_detected: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "expected_rejection_detected", "expectedRejectionDetected"
        ),
    )
    environment_blocked: bool = Field(
        default=False,
        validation_alias=AliasChoices("environment_blocked", "environmentBlocked"),
    )
    duration_ms: int | None = Field(
        default=None,
        validation_alias=AliasChoices("duration_ms", "durationMs"),
        ge=0,
        le=3_600_000,
    )
    provider_total_tokens: int | None = Field(
        default=None,
        validation_alias=AliasChoices("provider_total_tokens", "providerTotalTokens"),
        ge=0,
    )


class RunManifest(StrictQualityModel):
    """Safe, reproducible metadata for a synthetic quality execution.

    It intentionally holds hashes and version labels only.  Customer messages,
    orders, tokens, prompts, RAG passages and raw tool payloads have no field
    here and therefore cannot become replay input by accident.
    """

    manifest_version: Literal["1"] = Field(
        default="1",
        validation_alias=AliasChoices("manifest_version", "manifestVersion"),
    )
    correlation_ref: str = Field(
        validation_alias=AliasChoices("correlation_ref", "correlationRef"),
        min_length=8,
        max_length=64,
        pattern=r"^[a-f0-9]+$",
    )
    role: Literal["quality_evaluation"] = "quality_evaluation"
    skill_catalog_version: str = Field(
        validation_alias=AliasChoices("skill_catalog_version", "skillCatalogVersion"),
        min_length=3,
        max_length=64,
    )
    profile_id: str = Field(
        validation_alias=AliasChoices("profile_id", "profileId"),
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    profile_version: str = Field(
        validation_alias=AliasChoices("profile_version", "profileVersion"),
        min_length=2,
        max_length=32,
        pattern=r"^v[0-9]+(?:\.[0-9]+){0,2}$",
    )
    prompt_version: str = Field(
        validation_alias=AliasChoices("prompt_version", "promptVersion"),
        min_length=3,
        max_length=64,
    )
    rag_profile_version: str = Field(
        validation_alias=AliasChoices("rag_profile_version", "ragProfileVersion"),
        min_length=3,
        max_length=64,
    )
    tool_schema_version: str = Field(
        validation_alias=AliasChoices("tool_schema_version", "toolSchemaVersion"),
        min_length=3,
        max_length=64,
    )
    fixture_hash: str = Field(
        validation_alias=AliasChoices("fixture_hash", "fixtureHash"),
        min_length=16,
        max_length=64,
        pattern=r"^[a-f0-9]+$",
    )
    execution_mode: QualityEvaluationMode = Field(
        validation_alias=AliasChoices("execution_mode", "executionMode"),
    )
    duration_ms: int = Field(
        validation_alias=AliasChoices("duration_ms", "durationMs"), ge=0, le=3_600_000
    )
    provider_total_tokens: int | None = Field(
        default=None,
        validation_alias=AliasChoices("provider_total_tokens", "providerTotalTokens"),
        ge=0,
    )
    result_kind: Literal["passed", "failed", "environment_blocked"] = Field(
        validation_alias=AliasChoices("result_kind", "resultKind"),
    )
    error_category: str | None = Field(
        default=None,
        validation_alias=AliasChoices("error_category", "errorCategory"),
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    replay_of_ref: str | None = Field(
        default=None,
        validation_alias=AliasChoices("replay_of_ref", "replayOfRef"),
        min_length=16,
        max_length=64,
        pattern=r"^[a-f0-9]+$",
    )
    replayable: bool = True
    replay_reason_code: Literal[
        "synthetic_contract_fixture_retained",
        "live_model_requires_explicit_evaluation",
        "runtime_fixture_not_retained",
        "profile_not_available",
        "fixture_version_mismatch",
    ] = Field(
        default="synthetic_contract_fixture_retained",
        validation_alias=AliasChoices("replay_reason_code", "replayReasonCode"),
    )


class QualityEvaluationRun(StrictQualityModel):
    run_id: str = Field(
        validation_alias=AliasChoices("run_id", "runId"), min_length=36, max_length=36
    )
    suite_version: str = Field(
        validation_alias=AliasChoices("suite_version", "suiteVersion"),
        min_length=1,
        max_length=64,
    )
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    execution_mode: QualityEvaluationMode = Field(
        default="contract_mock",
        validation_alias=AliasChoices("execution_mode", "executionMode"),
    )
    cases: list[QualityCaseResult] = Field(default_factory=list, max_length=100)
    ran_at: datetime = Field(
        validation_alias=AliasChoices("ran_at", "ranAt")
    )
    ai_failure_analysis_requested: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ai_failure_analysis_requested", "aiFailureAnalysisRequested"
        ),
    )
    environment_blocked: bool = Field(
        default=False,
        validation_alias=AliasChoices("environment_blocked", "environmentBlocked"),
    )
    profile_id: str = Field(
        default="contract_mock",
        validation_alias=AliasChoices("profile_id", "profileId"),
        min_length=3,
        max_length=64,
    )
    profile_version: str = Field(
        default="v1",
        validation_alias=AliasChoices("profile_version", "profileVersion"),
        min_length=2,
        max_length=32,
    )
    run_manifest: RunManifest | None = Field(
        default=None,
        validation_alias=AliasChoices("run_manifest", "runManifest"),
    )


class QualityRunReplayStatus(StrictQualityModel):
    """Safe replay eligibility only; it never carries a fixture or runtime input."""

    run_id: str = Field(
        validation_alias=AliasChoices("run_id", "runId"), min_length=36, max_length=36
    )
    replayable: bool
    reason_code: Literal[
        "synthetic_contract_fixture_retained",
        "live_model_requires_explicit_evaluation",
        "runtime_fixture_not_retained",
        "profile_not_available",
        "fixture_version_mismatch",
    ] = Field(validation_alias=AliasChoices("reason_code", "reasonCode"))


class QualityEvaluationRunRequest(StrictQualityModel):
    execution_mode: QualityEvaluationMode = Field(
        default="contract_mock",
        validation_alias=AliasChoices("execution_mode", "executionMode"),
    )
    enable_ai_failure_analysis: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "enable_ai_failure_analysis", "enableAiFailureAnalysis"
        ),
    )
    profile_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("profile_id", "profileId"),
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )


class QualityReviewRequest(StrictQualityModel):
    review_status: Literal["APPROVED", "REJECTED"] = Field(
        validation_alias=AliasChoices("review_status", "reviewStatus")
    )
