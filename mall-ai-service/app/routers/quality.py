"""Developer-only API for isolated AI quality evaluation and governance."""

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Header, HTTPException, Path

from app.schemas.quality import (
    DeveloperLoginRequest,
    DeveloperLoginResponse,
    DeveloperProfile,
    EvalCase,
    QualityEvaluationRun,
    QualityEvaluationRunRequest,
    QualityReviewRequest,
    QualityRunReplayStatus,
)
from app.schemas.agent_ops import (
    EvaluationProfile,
    EvaluationProfileExperiment,
    EvaluationProfileExperimentRequest,
    FeedbackCandidateCreateRequest,
    FeedbackCandidateView,
    LocalMetricView,
)
from app.services.quality_developer_client import (
    QualityDeveloperApiError,
    get_current_quality_developer,
    login_quality_developer,
)
from app.services.quality_evaluation_agent import (
    DEFAULT_SUITE_PATH,
    LIVE_MODEL_SYNTHETIC_SUITE_PATH,
    QualityRunReplayError,
    fixture_hash_for_cases,
    load_quality_suite,
    replay_quality_evaluation,
    run_quality_evaluation,
)
from app.services.quality_run_store import quality_run_store
from app.services.evaluation_profile_service import (
    EvaluationProfileError,
    get_evaluation_profile,
    list_evaluation_profiles,
)
from app.services.feedback_governance_service import (
    FeedbackGovernanceError,
    feedback_governance_store,
)
from app.services.reliability_service import (
    ConcurrentOperationError,
    RateLimitExceeded,
    ReliabilityBackendUnavailable,
    reliability_governor,
)


router = APIRouter(prefix="/quality", tags=["quality-evaluation"])


@router.post("/auth/login", response_model=DeveloperLoginResponse)
def quality_login(request: DeveloperLoginRequest) -> DeveloperLoginResponse:
    try:
        return login_quality_developer(request.username, request.password)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/me", response_model=DeveloperProfile)
def quality_me(authorization: str | None = Header(default=None)) -> DeveloperProfile:
    try:
        return get_current_quality_developer(authorization)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/evaluations/run", response_model=QualityEvaluationRun)
def run_evaluation(
    request: QualityEvaluationRunRequest = Body(default_factory=QualityEvaluationRunRequest),
    authorization: str | None = Header(default=None),
) -> QualityEvaluationRun:
    started_at = time.monotonic()
    try:
        developer = get_current_quality_developer(authorization)
        profile = get_evaluation_profile(
            request.profile_id
            or (
                "live_model_synthetic"
                if request.execution_mode == "live_model_synthetic"
                else "contract_mock"
            )
        )
        # Default is deterministic and fully offline.  The checkbox-controlled
        # advisory analysis only sees failing safe projections.
        reliability_governor.check_rate_limit(
            actor_scope=f"quality:{developer.username}",
            role="quality_evaluation",
            action="quality_evaluation",
            skill_id="quality_contract_evaluation",
        )
        with reliability_governor.lock(
            scope=f"quality:{profile.profile_id}", kind="evaluation", ttl_seconds=90
        ):
            approved_cases = feedback_governance_store.approved_eval_cases()
            result = run_quality_evaluation(
                execution_mode=profile.execution_mode,
                profile=profile,
                additional_cases=approved_cases,
                enable_ai_failure_analysis=request.enable_ai_failure_analysis,
            )
            # Retain the exact synthetic inputs used by this run for an
            # explicit developer replay.  The store never persists customer
            # requests or runtime traces.  Governed additions remain
            # non-replayable until they are part of the versioned suite.
            quality_run_store.save(
                result,
                fixtures=_fixture_cases_for_profile(profile, approved_cases),
            )
        reliability_governor.record_request(
            "quality_evaluation", succeeded=True, duration_ms=_elapsed_ms(started_at)
        )
        return result
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except EvaluationProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ConcurrentOperationError as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReliabilityBackendUnavailable as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=503, detail="质量评测保护暂时不可用，请稍后重试。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="AI 质量评测套件暂不可用。") from exc


@router.get("/evaluations/latest", response_model=QualityEvaluationRun)
def latest_evaluation(authorization: str | None = Header(default=None)) -> QualityEvaluationRun:
    try:
        get_current_quality_developer(authorization)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    latest = quality_run_store.latest()
    if latest is None:
        raise HTTPException(status_code=404, detail="当前进程尚未运行 AI 质量评测。")
    return latest


@router.get(
    "/evaluations/{run_id}/replay-status",
    response_model=QualityRunReplayStatus,
)
def quality_replay_status(
    run_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> QualityRunReplayStatus:
    """Report whether a stored deterministic run can be safely replayed."""

    try:
        get_current_quality_developer(authorization)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    run = quality_run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="评测运行不存在。")
    return _replay_status_for_run(run)


@router.post(
    "/evaluations/{run_id}/replay",
    response_model=QualityEvaluationRun,
)
def replay_evaluation(
    run_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> QualityEvaluationRun:
    """Replay one retained contract-mock run with its exact safe fixtures."""

    started_at = time.monotonic()
    try:
        developer = get_current_quality_developer(authorization)
        source = quality_run_store.get(run_id)
        if source is None:
            raise HTTPException(status_code=404, detail="评测运行不存在。")
        status = _replay_status_for_run(source)
        if not status.replayable:
            raise HTTPException(
                status_code=409,
                detail=f"当前评测不可安全重放（{status.reason_code}）。",
            )
        manifest = source.run_manifest
        assert manifest is not None  # guarded by _replay_status_for_run
        profile = get_evaluation_profile(manifest.profile_id)
        fixtures = quality_run_store.fixtures_for(run_id)
        if fixtures is None:
            raise HTTPException(status_code=409, detail="固定评测夹具未保留，不能重放。")
        reliability_governor.check_rate_limit(
            actor_scope=f"quality:{developer.username}",
            role="quality_evaluation",
            action="quality_evaluation",
            skill_id="quality_contract_evaluation",
        )
        with reliability_governor.lock(
            scope=f"quality:replay:{run_id}", kind="evaluation", ttl_seconds=90
        ):
            replayed = replay_quality_evaluation(
                source_run=source,
                profile=profile,
                fixtures=fixtures,
            )
            result = quality_run_store.save(replayed, fixtures=fixtures)
        reliability_governor.record_request(
            "quality_evaluation", succeeded=True, duration_ms=_elapsed_ms(started_at)
        )
        return result
    except HTTPException:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise
    except QualityDeveloperApiError as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except EvaluationProfileError as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=409, detail="评测 Profile 不再可用，不能重放。") from exc
    except QualityRunReplayError as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ConcurrentOperationError as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReliabilityBackendUnavailable as exc:
        reliability_governor.record_request(
            "quality_evaluation", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        raise HTTPException(status_code=503, detail="质量评测保护暂时不可用，请稍后重试。") from exc


@router.post(
    "/evaluations/{run_id}/cases/{case_id}/review",
    response_model=QualityEvaluationRun,
)
def review_evaluation_case(
    request: QualityReviewRequest,
    run_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    case_id: str = Path(min_length=3, max_length=96),
    authorization: str | None = Header(default=None),
) -> QualityEvaluationRun:
    try:
        get_current_quality_developer(authorization)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    result = quality_run_store.set_case_review(
        run_id=run_id,
        case_id=case_id,
        review_status=request.review_status,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="评测运行或案例不存在。")
    return result


@router.get("/profiles", response_model=list[EvaluationProfile])
def quality_profiles(authorization: str | None = Header(default=None)) -> list[EvaluationProfile]:
    try:
        get_current_quality_developer(authorization)
        return list(list_evaluation_profiles())
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/metrics", response_model=list[LocalMetricView])
def quality_metrics(authorization: str | None = Header(default=None)) -> list[LocalMetricView]:
    """Developer-only local measurements; no production SLA claim is implied."""

    try:
        get_current_quality_developer(authorization)
        return [LocalMetricView.model_validate(item.__dict__) for item in reliability_governor.metrics.snapshots()]
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/feedback-candidates", response_model=list[FeedbackCandidateView])
def list_feedback_candidates(
    authorization: str | None = Header(default=None),
) -> list[FeedbackCandidateView]:
    try:
        get_current_quality_developer(authorization)
        return feedback_governance_store.list_candidates()
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/feedback-candidates", response_model=FeedbackCandidateView)
def create_feedback_candidate(
    request: FeedbackCandidateCreateRequest,
    authorization: str | None = Header(default=None),
) -> FeedbackCandidateView:
    try:
        get_current_quality_developer(authorization)
        return feedback_governance_store.create_candidate(request)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FeedbackGovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/feedback-candidates/{candidate_id}/approve",
    response_model=FeedbackCandidateView,
)
def approve_feedback_candidate(
    candidate_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> FeedbackCandidateView:
    try:
        get_current_quality_developer(authorization)
        return feedback_governance_store.approve_candidate(candidate_id)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FeedbackGovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/feedback-candidates/{candidate_id}/reject",
    response_model=FeedbackCandidateView,
)
def reject_feedback_candidate(
    candidate_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> FeedbackCandidateView:
    try:
        get_current_quality_developer(authorization)
        return feedback_governance_store.reject_candidate(candidate_id)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FeedbackGovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/experiments/run", response_model=EvaluationProfileExperiment)
def run_profile_experiment(
    request: EvaluationProfileExperimentRequest,
    authorization: str | None = Header(default=None),
) -> EvaluationProfileExperiment:
    """Compare named profiles against the same synthetic fixture set only."""

    try:
        developer = get_current_quality_developer(authorization)
        if len(set(request.profile_ids)) != len(request.profile_ids):
            raise EvaluationProfileError("同一实验不能重复选择 Profile。")
        profiles = [get_evaluation_profile(profile_id) for profile_id in request.profile_ids]
        reliability_governor.check_rate_limit(
            actor_scope=f"quality:{developer.username}",
            role="quality_evaluation",
            action="quality_evaluation",
            skill_id="quality_contract_evaluation",
        )
        runs = []
        for profile in profiles:
            approved_cases = feedback_governance_store.approved_eval_cases()
            with reliability_governor.lock(
                scope=f"quality:{profile.profile_id}", kind="evaluation", ttl_seconds=90
            ):
                run = run_quality_evaluation(
                    execution_mode=profile.execution_mode,
                    profile=profile,
                    additional_cases=approved_cases,
                    enable_ai_failure_analysis=request.enable_ai_failure_analysis,
                )
                runs.append(
                    quality_run_store.save(
                        run,
                        fixtures=_fixture_cases_for_profile(profile, approved_cases),
                    )
                )
        experiment = EvaluationProfileExperiment(
            experiment_id=str(uuid.uuid4()),
            suite_version=runs[0].suite_version,
            profile_ids=[profile.profile_id for profile in profiles],
            run_ids=[run.run_id for run in runs],
            created_at=datetime.now(timezone.utc),
        )
        return quality_run_store.save_experiment(experiment)
    except QualityDeveloperApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (EvaluationProfileError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ConcurrentOperationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReliabilityBackendUnavailable as exc:
        raise HTTPException(status_code=503, detail="质量评测保护暂时不可用，请稍后重试。") from exc


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


def _fixture_cases_for_profile(
    profile: EvaluationProfile,
    approved_cases: list[EvalCase],
) -> list[EvalCase]:
    """Load only repository-owned suite cases plus approved synthetic additions."""

    suite_path = (
        LIVE_MODEL_SYNTHETIC_SUITE_PATH
        if profile.execution_mode == "live_model_synthetic"
        else DEFAULT_SUITE_PATH
    )
    suite = load_quality_suite(suite_path)
    return [*suite.cases, *approved_cases]


def _replay_status_for_run(run: QualityEvaluationRun) -> QualityRunReplayStatus:
    manifest = run.run_manifest
    if manifest is None:
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code="runtime_fixture_not_retained",
        )
    if manifest.execution_mode == "live_model_synthetic":
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code="live_model_requires_explicit_evaluation",
        )
    if not manifest.replayable:
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code=manifest.replay_reason_code,
        )
    fixtures = quality_run_store.fixtures_for(run.run_id)
    if not fixtures:
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code="runtime_fixture_not_retained",
        )
    try:
        fixture_hash = fixture_hash_for_cases(fixtures)
    except Exception:
        fixture_hash = ""
    if fixture_hash != manifest.fixture_hash:
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code="fixture_version_mismatch",
        )
    try:
        profile = get_evaluation_profile(manifest.profile_id)
    except EvaluationProfileError:
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code="profile_not_available",
        )
    if profile.version != manifest.profile_version or profile.execution_mode != manifest.execution_mode:
        return QualityRunReplayStatus(
            run_id=run.run_id,
            replayable=False,
            reason_code="fixture_version_mismatch",
        )
    return QualityRunReplayStatus(
        run_id=run.run_id,
        replayable=True,
        reason_code="synthetic_contract_fixture_retained",
    )
