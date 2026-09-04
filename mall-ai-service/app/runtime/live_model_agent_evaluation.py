"""Explicit live-model evaluation for the bounded v3 Task Runtime.

This runner is deliberately separate from the customer API and from the
deterministic release manifest.  It replays versioned synthetic goals through
the real :class:`TaskRuntime`, real model provider, Skill discovery and a
fixture-backed read-only gateway.  The gateway never calls Java, Redis,
MongoDB, RAG or a business write endpoint.

The report contains only case identifiers, hashes, status and operational
metadata.  It never includes a goal, tool argument, model response, prompt,
credential, order identifier or raw fixture payload.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from app.config import settings
from app.runtime.providers import DeepSeekRuntimeProvider, RuntimeModelError
from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
from app.runtime.task_store import InMemoryTaskStore
from app.schemas.agent_task import TaskExecutionBudget
from app.services.llm_observability import TokenPricing, capture_llm_metrics, summarize_llm_metrics
from app.skills.catalog import SKILL_CATALOG_VERSION
from app.skills.commerce_gateway import SkillObservation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE_PATH = PROJECT_ROOT / "evals" / "live_model_agent_runtime_cases.v1.json"
SUITE_VERSION = "live-model-agent-runtime.v1"
SYNTHETIC_AUTHORIZATION = "Bearer synthetic-agent-evaluation"
SYNTHETIC_MEMBER_ID = 7001
_CASE_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,79}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_MODEL_FAILURE_CODES = {
    "model_missing_configuration",
    "model_network",
    "model_timeout",
    "model_rate_limited",
    "model_provider_unavailable",
    "model_provider_http",
    "model_circuit_open",
}


class LiveAgentEvaluationError(ValueError):
    """Raised when a reviewed live-agent fixture is malformed."""


@dataclass(frozen=True)
class CaseRunResult:
    case_id: str
    run_index: int
    status: str
    execution_kind: str
    terminal_status: str | None
    failure_categories: tuple[str, ...]
    invoked_skills: tuple[str, ...]
    successful_skills: tuple[str, ...]
    model_calls: int
    tool_calls: int
    context_model_calls: int
    critic_calls: int
    proposal_present: bool
    commit_calls: int
    task_success: bool
    clarification_correct: bool
    required_skill_or_fact_coverage: bool
    proposal_or_resume_success: bool
    irrelevant_calls: int
    forbidden_side_effects: int
    elapsed_ms: int
    post_checks: dict[str, bool]


class SyntheticReadOnlyGateway:
    """Fixture-backed gateway that cannot reach a real business service."""

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self._fixture = fixture
        self.invocations: list[str] = []
        self._invocation_statuses: list[tuple[str, str]] = []
        self.commits: list[str] = []

    def invoke(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        del arguments, authorization, member_id, task_ref
        self.invocations.append(skill_id)
        raw = self._fixture.get("observations", {}).get(skill_id)
        if not isinstance(raw, Mapping):
            observation = SkillObservation(
                status="blocked",
                artifact_kind="action_result",
                summary="合成 Skill 未提供该能力的安全结果。",
                reference=_reference("synthetic", f"missing:{skill_id}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "fixture_missing"},
            )
        else:
            status = raw.get("status", "succeeded")
            kind = raw.get("artifact_kind", _default_artifact_kind(skill_id))
            factuality = raw.get("factuality", "verified" if status == "succeeded" else "unavailable")
            summary = raw.get("summary", "已取得合成且脱敏的 Skill 结果摘要。")
            safe_facts = raw.get("safe_facts", {})
            if not isinstance(safe_facts, Mapping):
                safe_facts = {}
            safe_facts = {str(key): str(value) for key, value in list(safe_facts.items())[:8]}
            if isinstance(raw.get("failure_code"), str):
                safe_facts.setdefault("failure_code", raw["failure_code"])
            observation = SkillObservation(
                status=str(status),
                artifact_kind=str(kind),
                summary=str(summary),
                reference=str(raw.get("reference") or _reference("synthetic", skill_id)),
                source_version=str(raw.get("source_version") or "v1"),
                factuality=str(factuality),
                safe_facts=safe_facts,
            )
        self._invocation_statuses.append((skill_id, observation.status))
        return observation

    def commit(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        del arguments, authorization, member_id, task_ref
        self.commits.append(skill_id)
        raw = self._fixture.get("commit_observation")
        if isinstance(raw, Mapping):
            return SkillObservation(
                status=str(raw.get("status", "blocked")),
                artifact_kind="action_result",
                summary=str(raw.get("summary", "合成提交结果；不触碰真实业务系统。")),
                reference=str(raw.get("reference") or _reference("synthetic", f"commit:{skill_id}")),
                source_version=str(raw.get("source_version") or "v1"),
                factuality=str(raw.get("factuality", "unavailable")),
                safe_facts={"failure_code": str(raw.get("failure_code", "synthetic_commit"))},
            )
        return SkillObservation(
            status="blocked",
            artifact_kind="action_result",
            summary="合成评测网关不执行真实业务写入。",
            reference=_reference("synthetic", f"commit-blocked:{skill_id}"),
            source_version="v1",
            factuality="unavailable",
            safe_facts={"failure_code": "synthetic_gateway_write_blocked"},
        )


class FaultInjectedProvider:
    """Intentional provider fault used only by the safety-stop cases."""

    def __init__(self, category: str) -> None:
        self.category = category

    def decide(self, _context):
        raise RuntimeModelError("synthetic provider fault", role="commerce_executor", category=self.category)

    def curate(self, _context):
        raise RuntimeModelError("synthetic provider fault", role="context_curator", category=self.category)

    def critique(self, _context):
        raise RuntimeModelError("synthetic provider fault", role="resolution_critic", category=self.category)


def load_live_agent_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveAgentEvaluationError("live agent suite 无法加载。") from exc
    if not isinstance(payload, dict) or payload.get("suiteVersion") != SUITE_VERSION:
        raise LiveAgentEvaluationError("live agent suite 版本不匹配。")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) < 24:
        raise LiveAgentEvaluationError("live agent suite 至少需要 24 个独立案例。")
    seen: set[str] = set()
    for case in cases:
        _validate_case(case, seen)
    return payload


def run_live_model_agent_evaluation(
    *,
    suite_path: Path = DEFAULT_SUITE_PATH,
    max_total_seconds: float = 1200.0,
    timeout_seconds: float = 25.0,
    max_attempts: int = 1,
    pricing: TokenPricing | None = None,
    provider_factory: Callable[[Mapping[str, Any]], Any] | None = None,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run every selected fixture three times through the bounded Runtime."""

    if max_total_seconds <= 0 or timeout_seconds <= 0 or max_attempts < 1:
        raise ValueError("evaluation budgets must be positive")
    suite = load_live_agent_suite(suite_path)
    cases = [case for case in suite["cases"] if case_ids is None or case["caseId"] in case_ids]
    if not cases:
        raise LiveAgentEvaluationError("没有匹配的 live agent case。")
    started = time.monotonic()
    results: list[CaseRunResult] = []
    required_runs = 3
    with capture_llm_metrics(timeout_seconds=timeout_seconds, max_attempts=max_attempts) as metric_sink:
        for case in cases:
            for run_index in range(1, required_runs + 1):
                if time.monotonic() - started >= max_total_seconds:
                    results.append(
                        CaseRunResult(
                            case_id=case["caseId"],
                            run_index=run_index,
                            status="environment_blocked",
                            execution_kind="not_run_budget",
                            terminal_status=None,
                            failure_categories=("evaluation_budget_exhausted",),
                            invoked_skills=(),
                            successful_skills=(),
                            model_calls=0,
                            tool_calls=0,
                            context_model_calls=0,
                            critic_calls=0,
                            proposal_present=False,
                            commit_calls=0,
                            task_success=False,
                            clarification_correct=False,
                            required_skill_or_fact_coverage=False,
                            proposal_or_resume_success=False,
                            irrelevant_calls=0,
                            forbidden_side_effects=0,
                            elapsed_ms=0,
                            post_checks={},
                        )
                    )
                    continue
                metric_start = len(metric_sink.events)
                result = _run_case(
                    case,
                    run_index=run_index,
                    provider_factory=provider_factory,
                )
                # Keep per-case LLM metrics out of the public case row while
                # retaining aggregate usage for the evidence document.
                del metric_start
                results.append(result)

    return _build_report(suite, cases, results, metric_sink.events, pricing, started)


def _run_case(
    case: Mapping[str, Any],
    *,
    run_index: int,
    provider_factory: Callable[[Mapping[str, Any]], Any] | None,
) -> CaseRunResult:
    started = time.monotonic()
    case_id = str(case["caseId"])
    fixture = case["fixture"]
    provider_kind = str(fixture.get("execution_kind", "live_model"))
    if provider_factory is not None:
        provider = provider_factory(case)
    elif isinstance(fixture.get("provider_fault"), str):
        provider = FaultInjectedProvider(str(fixture["provider_fault"]))
        provider_kind = "fault_injected"
    else:
        provider = DeepSeekRuntimeProvider()
    gateway = SyntheticReadOnlyGateway(fixture)
    store = InMemoryTaskStore()
    runtime = TaskRuntime(
        store=store,
        provider=provider,
        gateway=gateway,
    )
    terminal_status: str | None = None
    proposal_present = False
    task_success = False
    clarification_correct = False
    required_coverage = False
    proposal_resume_success = False
    post_checks: dict[str, bool] = {}
    failure_categories: list[str] = []
    task_ref: str | None = None
    outcome = None
    try:
        outcome = runtime.create_task(
            session_id=f"live-agent-{case_id}-{run_index}",
            goal=str(case["goal"]),
            member_id=SYNTHETIC_MEMBER_ID,
            authorization=SYNTHETIC_AUTHORIZATION,
            execution_budget=TaskExecutionBudget(
                max_model_calls=int(case["expect"].get("max_model_calls", 6)),
                max_tool_calls=int(case["expect"].get("max_tool_calls", 8)),
                max_wall_clock_seconds=int(case["expect"].get("max_wall_clock_seconds", 45)),
            ),
        )
        terminal_status = outcome.view.status
        task_ref = outcome.view.task_ref
        # Runtime turns provider faults into a safe blocked projection. Keep
        # only model-originated codes here so they can be classified as an
        # environment block; expected Skill/RAG failures are checked by the
        # case's safe-stop contract instead of being mistaken for transport
        # outages.
        failure_categories.extend(
            code for code in outcome.view.limitation_codes if code in _MODEL_FAILURE_CODES
        )
        proposal_present = outcome.view.action is not None and outcome.view.action.confirmation_status == "awaiting_confirmation"
        task_success = terminal_status in set(case["expect"].get("terminal_statuses", []))
        clarification_correct = _check_clarification(case, outcome.view)
        required_coverage = _check_required_coverage(case, gateway)
        proposal_resume_success = _check_proposal_expectation(case, proposal_present)
        failure_categories.extend(_contract_failures(case, outcome.view, gateway, proposal_present))
        if not task_success:
            failure_categories.append("terminal_status_mismatch")
        if not clarification_correct:
            failure_categories.append("clarification_mismatch")
        if not required_coverage:
            failure_categories.append("required_skill_or_fact_missing")
        if not proposal_resume_success:
            failure_categories.append("proposal_or_resume_missing")
        post_checks = _run_post_checks(case, runtime, store, task_ref, gateway, outcome)
        failure_categories.extend(name for name, passed in post_checks.items() if not passed)
    except TaskRuntimeError as exc:
        failure_categories.append(exc.code)
    except Exception as exc:  # pragma: no cover - defensive report boundary
        failure_categories.append(f"runtime_exception_{type(exc).__name__.lower()}")

    # An intentionally injected provider fault is a safety case, not an
    # external environment outage.  Real provider/network faults remain
    # ``environment_blocked`` and are never converted into a quality pass.
    environment_blocked = provider_kind != "fault_injected" and any(
        code in _MODEL_FAILURE_CODES for code in failure_categories
    )
    if provider_kind == "fault_injected":
        failure_categories = [
            code for code in failure_categories if code not in _MODEL_FAILURE_CODES
        ]
    # The synthetic gateway has no implementation of a business write. A
    # commit call is retained as an observable *attempt* for idempotency
    # checks, while actual business side effects remain zero by construction.
    forbidden_side_effects = 0
    if task_ref is not None:
        try:
            persisted = store._items[task_ref].model_dump(mode="json")  # noqa: SLF001 - evidence-only inspection
            serialized = json.dumps(persisted, ensure_ascii=False, sort_keys=True)
            # Epoch timestamps and generated task/hash identifiers naturally
            # contain digits.  Check the actual sensitive inputs instead of a
            # broad digit regex that would produce false positives.
            raw_goal = str(case.get("goal", ""))
            sensitive_goal_fragments = re.findall(r"(?<!\d)\d{6,}(?!\d)", raw_goal)
            sensitive_goal_fragments.extend(
                fragment
                for fragment in ("Bearer ", "token=", "password", "api_key")
                if fragment.lower() in raw_goal.lower()
            )
            leaked_raw_goal = any(fragment in serialized for fragment in sensitive_goal_fragments)
            leaked_auth = SYNTHETIC_AUTHORIZATION in serialized
            if leaked_auth or leaked_raw_goal:
                forbidden_side_effects += 1
                failure_categories.append("unsafe_data_persisted")
        except Exception:
            failure_categories.append("persisted_projection_unreadable")

    status = "environment_blocked" if environment_blocked else "passed" if not failure_categories else "failed"
    return CaseRunResult(
        case_id=case_id,
        run_index=run_index,
        status=status,
        execution_kind=provider_kind,
        terminal_status=terminal_status,
        failure_categories=tuple(dict.fromkeys(failure_categories)),
        invoked_skills=tuple(gateway.invocations),
        successful_skills=tuple(
            skill for skill, status_value in gateway._invocation_statuses if status_value == "succeeded"
        ),
        model_calls=_model_calls(store, task_ref),
        tool_calls=_tool_calls(store, task_ref),
        context_model_calls=_context_calls(store, task_ref),
        critic_calls=_critic_calls(store, task_ref),
        proposal_present=proposal_present,
        commit_calls=len(gateway.commits),
        task_success=task_success,
        clarification_correct=clarification_correct,
        required_skill_or_fact_coverage=required_coverage,
        proposal_or_resume_success=proposal_resume_success,
        irrelevant_calls=_irrelevant_calls(case, gateway),
        forbidden_side_effects=forbidden_side_effects,
        elapsed_ms=max(0, round((time.monotonic() - started) * 1000)),
        post_checks=post_checks,
    )


def _check_clarification(case: Mapping[str, Any], view: Any) -> bool:
    expected = case["expect"].get("clarification")
    if expected is None:
        return True
    actual = view.status == "waiting_for_user" and isinstance(view.open_question, str) and bool(view.open_question.strip())
    return bool(expected) == actual


def _check_required_coverage(case: Mapping[str, Any], gateway: SyntheticReadOnlyGateway) -> bool:
    expect = case["expect"]
    successful = {
        skill
        for skill, status in gateway._invocation_statuses
        if status == "succeeded"
    }
    invoked = set(gateway.invocations)
    coverage_pool = successful | (invoked if expect.get("safe_stop") else set())
    all_skills = expect.get("required_skills_all", [])
    any_groups = expect.get("required_skills_any", [])
    if not all(skill in coverage_pool for skill in all_skills):
        return False
    for group in any_groups:
        if not isinstance(group, list) or not any(skill in coverage_pool for skill in group):
            return False
    if expect.get("no_tool_calls") is True and invoked:
        return False
    return True


def _check_proposal_expectation(case: Mapping[str, Any], proposal_present: bool) -> bool:
    expected = case["expect"].get("proposal", "not_required")
    if expected == "required":
        return proposal_present
    if expected == "forbidden":
        return not proposal_present
    return True


def _contract_failures(
    case: Mapping[str, Any],
    view: Any,
    gateway: SyntheticReadOnlyGateway,
    proposal_present: bool,
) -> list[str]:
    failures: list[str] = []
    allowed = set(case["expect"].get("allowed_skills", []))
    irrelevant = [skill for skill in gateway.invocations if allowed and skill not in allowed]
    if irrelevant:
        failures.append("irrelevant_skill_call")
    forbidden = set(case["expect"].get("forbidden_skills", []))
    if forbidden.intersection(gateway.invocations):
        failures.append("forbidden_skill_call")
    if case["expect"].get("safe_stop"):
        safe_statuses = set(case["expect"].get("safe_stop_statuses", ["blocked", "waiting_for_user"]))
        if view.status not in safe_statuses:
            failures.append("unsafe_no_evidence_or_failure_continuation")
        if proposal_present:
            failures.append("proposal_after_safe_stop")
    return failures


def _run_post_checks(
    case: Mapping[str, Any],
    runtime: TaskRuntime,
    store: InMemoryTaskStore,
    task_ref: str | None,
    gateway: SyntheticReadOnlyGateway,
    outcome: Any,
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    post = case["expect"].get("post", [])
    if not isinstance(post, list) or task_ref is None:
        return checks
    owner_ref = store._items[task_ref].task.owner_ref  # noqa: SLF001
    for operation in post:
        if operation == "cross_account_reject":
            try:
                runtime.get_task(task_ref=task_ref, member_id=SYNTHETIC_MEMBER_ID + 1, authorization=SYNTHETIC_AUTHORIZATION)
            except TaskRuntimeError as exc:
                checks["cross_account_rejected"] = exc.code == "task_not_found"
            else:
                checks["cross_account_rejected"] = False
        elif operation == "restart_projection":
            restarted = TaskRuntime(store=store, provider=FaultInjectedProvider("not_called"), gateway=gateway)
            try:
                restored = restarted.get_task(task_ref=task_ref, member_id=SYNTHETIC_MEMBER_ID, authorization=SYNTHETIC_AUTHORIZATION)
                checks["restart_projection_restored"] = restored.task_ref == task_ref
            except TaskRuntimeError:
                checks["restart_projection_restored"] = False
        elif operation == "expire_proposal":
            bundle = store._items[task_ref]  # noqa: SLF001
            if bundle.action_proposal is None:
                checks["expired_proposal_rejected"] = False
                continue
            bundle.action_proposal.expires_at = 0
            store.save(bundle)
            before = len(gateway.commits)
            try:
                expired = runtime.confirm_action(
                    task_ref=task_ref,
                    confirmation="confirm",
                    member_id=SYNTHETIC_MEMBER_ID,
                    authorization=SYNTHETIC_AUTHORIZATION,
                )
                checks["expired_proposal_rejected"] = (
                    expired.view.status == "blocked" and len(gateway.commits) == before
                )
            except TaskRuntimeError:
                checks["expired_proposal_rejected"] = len(gateway.commits) == before
        elif operation == "duplicate_confirmation":
            before = len(gateway.commits)
            try:
                runtime.confirm_action(
                    task_ref=task_ref,
                    confirmation="confirm",
                    member_id=SYNTHETIC_MEMBER_ID,
                    authorization=SYNTHETIC_AUTHORIZATION,
                )
                first_ok = True
            except TaskRuntimeError:
                first_ok = False
            try:
                runtime.confirm_action(
                    task_ref=task_ref,
                    confirmation="confirm",
                    member_id=SYNTHETIC_MEMBER_ID,
                    authorization=SYNTHETIC_AUTHORIZATION,
                )
            except TaskRuntimeError as exc:
                second_rejected = exc.code == "action_gate_missing"
            else:
                second_rejected = False
            checks["duplicate_confirmation_single_commit"] = first_ok and second_rejected and len(gateway.commits) - before <= 1
        elif operation == "subtask_created":
            checks["subtask_created"] = len(store._items) >= 2  # noqa: SLF001
        elif operation == "no_commit":
            checks["no_unconfirmed_commit"] = len(gateway.commits) == 0
    del owner_ref, outcome
    return checks


def _irrelevant_calls(case: Mapping[str, Any], gateway: SyntheticReadOnlyGateway) -> int:
    allowed = set(case["expect"].get("allowed_skills", []))
    return sum(1 for skill in gateway.invocations if allowed and skill not in allowed)


def _bundle_value(store: InMemoryTaskStore, task_ref: str | None, key: str) -> int:
    if task_ref is None:
        return 0
    bundle = store._items.get(task_ref)  # noqa: SLF001
    if bundle is None:
        return 0
    return int(getattr(bundle.task, key, 0) or 0)


def _model_calls(store: InMemoryTaskStore, task_ref: str | None) -> int:
    return _bundle_value(store, task_ref, "model_calls")


def _tool_calls(store: InMemoryTaskStore, task_ref: str | None) -> int:
    return _bundle_value(store, task_ref, "tool_calls")


def _context_calls(store: InMemoryTaskStore, task_ref: str | None) -> int:
    return _bundle_value(store, task_ref, "context_model_calls")


def _critic_calls(store: InMemoryTaskStore, task_ref: str | None) -> int:
    return _bundle_value(store, task_ref, "critic_calls")


def _build_report(
    suite: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
    results: list[CaseRunResult],
    metrics: list[Any],
    pricing: TokenPricing | None,
    started: float,
) -> dict[str, Any]:
    elapsed_values = [item.elapsed_ms for item in results]
    ordered = sorted(elapsed_values)
    report_cases = [
        {
            "caseId": item.case_id,
            "run": item.run_index,
            "status": item.status,
            "executionKind": item.execution_kind,
            "terminalStatus": item.terminal_status,
            "failureCategories": list(item.failure_categories),
            "invokedSkills": list(item.invoked_skills),
            "successfulSkills": sorted(set(item.successful_skills)),
            "modelCalls": item.model_calls,
            "toolCalls": item.tool_calls,
            "contextModelCalls": item.context_model_calls,
            "criticCalls": item.critic_calls,
            "proposalPresent": item.proposal_present,
            "commitCalls": item.commit_calls,
            "taskSuccess": item.task_success,
            "clarificationCorrect": item.clarification_correct,
            "requiredSkillOrFactCoverage": item.required_skill_or_fact_coverage,
            "proposalOrResumeSuccess": item.proposal_or_resume_success,
            "irrelevantCalls": item.irrelevant_calls,
            "forbiddenSideEffects": item.forbidden_side_effects,
            "elapsedMs": item.elapsed_ms,
            "postChecks": item.post_checks,
        }
        for item in results
    ]
    passed = sum(item.status == "passed" for item in results)
    failed = sum(item.status == "failed" for item in results)
    blocked = sum(item.status == "environment_blocked" for item in results)
    task_success = sum(item.task_success for item in results)
    clarification = sum(item.clarification_correct for item in results)
    coverage = sum(item.required_skill_or_fact_coverage for item in results)
    proposal_resume = sum(item.proposal_or_resume_success for item in results)
    suite_hash = hashlib.sha256(
        json.dumps(suite, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "suiteVersion": suite["suiteVersion"],
        "suiteSha256": suite_hash,
        "mode": "live_model_agent_synthetic",
        "uniqueCases": len(cases),
        "requiredRunsPerCase": 3,
        "executedRuns": len(results),
        "passed": passed,
        "failed": failed,
        "environmentBlocked": blocked,
        "taskSuccess": {"passed": task_success, "total": len(results)},
        "clarificationCorrect": {"passed": clarification, "total": len(results)},
        "requiredSkillOrFactCoverage": {"passed": coverage, "total": len(results)},
        "proposalOrResumeSuccess": {"passed": proposal_resume, "total": len(results)},
        "irrelevantCalls": sum(item.irrelevant_calls for item in results),
        "forbiddenSideEffects": sum(item.forbidden_side_effects for item in results),
        "duplicateFinalBusinessWrites": 0,
        "modelCalls": sum(item.model_calls for item in results),
        "toolCalls": sum(item.tool_calls for item in results),
        "contextModelCalls": sum(item.context_model_calls for item in results),
        "criticCalls": sum(item.critic_calls for item in results),
        "model": {
            "provider": "DeepSeekRuntimeProvider",
            "model": settings.deepseek_model,
            "promptVersion": "agent_runtime_v3_0",
            "skillCatalogVersion": SKILL_CATALOG_VERSION,
            "executionBoundary": "synthetic_read_only_gateway",
        },
        "llm": summarize_llm_metrics(metrics, pricing),
        "costStatus": "estimated_only_when_explicit_pricing_is_supplied",
        "latencyMs": {
            "p50": _percentile(ordered, 0.50),
            "p95": _percentile(ordered, 0.95),
            "max": ordered[-1] if ordered else 0,
        },
        "elapsedMs": max(0, round((time.monotonic() - started) * 1000)),
        "fixtureHashes": {
            str(case["caseId"]): str(case["fixtureHash"]) for case in cases
        },
        "cases": report_cases,
    }


def _validate_case(case: Any, seen: set[str]) -> None:
    if not isinstance(case, Mapping):
        raise LiveAgentEvaluationError("case 必须是对象。")
    case_id = case.get("caseId")
    if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id) or case_id in seen:
        raise LiveAgentEvaluationError("caseId 重复或格式不合法。")
    seen.add(case_id)
    if not isinstance(case.get("goal"), str) or not case["goal"].strip():
        raise LiveAgentEvaluationError(f"{case_id} 缺少合成目标。")
    fixture = case.get("fixture")
    if not isinstance(fixture, Mapping):
        raise LiveAgentEvaluationError(f"{case_id} 缺少 fixture。")
    expected_hash = case.get("fixtureHash")
    actual_hash = fixture_hash(fixture)
    if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash) or expected_hash != actual_hash:
        raise LiveAgentEvaluationError(f"{case_id} fixtureHash 不匹配。")
    expect = case.get("expect")
    if not isinstance(expect, Mapping):
        raise LiveAgentEvaluationError(f"{case_id} 缺少 expect。")


def fixture_hash(fixture: Mapping[str, Any]) -> str:
    canonical = json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _default_artifact_kind(skill_id: str) -> str:
    return {
        "search_catalog": "catalog_fact",
        "compare_skus": "sku_comparison",
        "read_order": "order_fact",
        "read_logistics": "logistics_fact",
        "read_inventory": "inventory_fact",
        "retrieve_policy": "policy_evidence",
        "list_service_applications": "after_sales_fact",
        "build_service_resolution": "resolution_candidate",
        "search_task_memory": "memory_hint",
        "spawn_subtask": "async_task",
    }.get(skill_id, "action_result")


def _reference(prefix: str, value: object) -> str:
    return f"{prefix}-{hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:24]}"


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    index = max(0, int((len(values) * fraction + 0.999999)) - 1)
    return values[index]


__all__ = [
    "DEFAULT_SUITE_PATH",
    "LiveAgentEvaluationError",
    "fixture_hash",
    "load_live_agent_suite",
    "run_live_model_agent_evaluation",
]
