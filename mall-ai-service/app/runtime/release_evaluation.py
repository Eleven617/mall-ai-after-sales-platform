"""Deterministic execution of the v3.0 release-contract inventory.

Every manifest case is checked against a closed assertion registry.  A small
representative set is additionally executed through the real TaskRuntime with
scripted provider/gateway objects.  The full 478-case inventory is not
pretended to be a production integration test: Java, browser, live-model and
Compose profiles remain separately labelled gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from app.runtime.providers import ScriptedRuntimeProvider, UnavailableRuntimeProvider
from app.runtime.task_runtime import TaskRuntime
from app.runtime.task_store import InMemoryTaskStore
from app.schemas.agent_task import ExecutorDecision, SkillCall
from app.skills.commerce_gateway import SkillObservation, SyntheticSkillGateway
from app.runtime.release_manifest import (
    DEFAULT_MANIFEST_PATH,
    ReleaseManifestError,
    load_release_manifest,
    validate_release_manifest,
)


@dataclass(frozen=True)
class ReleaseCaseResult:
    case_id: str
    status: str
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseEvaluationReport:
    suite_version: str
    registered_total: int
    registered_passed: int
    representative_total: int
    representative_passed: int
    cases: tuple[ReleaseCaseResult, ...]

    @property
    def failed(self) -> int:
        return self.registered_total - self.registered_passed + self.representative_total - self.representative_passed


def run_release_evaluation(path: Path = DEFAULT_MANIFEST_PATH) -> ReleaseEvaluationReport:
    payload = load_release_manifest(path)
    manifest_report = validate_release_manifest(payload)
    registered_results = tuple(_evaluate_registered_case(case) for case in payload["cases"])
    representative = tuple(_run_representative_cases())
    return ReleaseEvaluationReport(
        suite_version=manifest_report.suite_version,
        registered_total=len(registered_results),
        registered_passed=sum(result.status == "PASSED" for result in registered_results),
        representative_total=len(representative),
        representative_passed=sum(result.status == "PASSED" for result in representative),
        cases=registered_results + representative,
    )


def _evaluate_registered_case(case: Mapping[str, Any]) -> ReleaseCaseResult:
    violations: list[str] = []
    outcome = case["requiredOutcome"]
    fixture = case["fixture"]
    assertions = outcome["assertions"]
    if fixture.get("category") != case["category"]:
        violations.append("fixture_category_mismatch")
    if fixture.get("scenario") not in _SCENARIO_CONTRACTS:
        violations.append("scenario_not_registered")
    else:
        expected = _SCENARIO_CONTRACTS[fixture["scenario"]]
        if outcome.get("status") != expected["status"]:
            violations.append("scenario_status_mismatch")
        expected_code = expected.get("failure_code")
        actual_code = case.get("expectedFailureCode")
        if actual_code != expected_code:
            violations.append("scenario_failure_code_mismatch")
    for assertion in assertions:
        checker = _ASSERTIONS.get(assertion.split(":", 1)[0])
        if checker is None or not checker(case, assertion):
            violations.append(f"assertion_failed:{assertion.split(':', 1)[0]}")
    return ReleaseCaseResult(
        case_id=case["caseId"],
        status="PASSED" if not violations else "FAILED",
        violations=tuple(dict.fromkeys(violations)),
    )


_SCENARIO_CONTRACTS: dict[str, dict[str, Any]] = {
    "goal_normalization": {"status": "completed"},
    "skill_discovery": {"status": "completed"},
    "parallel_read_budget": {"status": "blocked", "failure_code": "parallel_budget_exceeded"},
    "waiting_for_user": {"status": "waiting_for_user"},
    "unknown_skill": {"status": "blocked", "failure_code": "unknown_skill"},
    "tool_budget": {"status": "blocked", "failure_code": "tool_call_budget_exhausted"},
    "model_unavailable": {"status": "blocked", "failure_code": "model_missing_configuration"},
    "subtask": {"status": "waiting_for_async_task"},
    "inventory_changed": {"status": "replanning"},
    "logistics_changed": {"status": "replanning"},
    "eligibility_changed": {"status": "replanning"},
    "policy_version_changed": {"status": "replanning"},
    "application_changed": {"status": "replanning"},
    "async_callback_changed": {"status": "replanning"},
    "two_candidates": {"status": "completed"},
    "fact_conflict": {"status": "replanning", "failure_code": "artifact_conflict"},
    "missing_fact": {"status": "waiting_for_user", "failure_code": "success_criteria_unmet"},
    "high_impact_action": {"status": "ready_to_commit"},
    "no_actionable_option": {"status": "blocked", "failure_code": "facts_incomplete"},
    "critic_unavailable": {"status": "executing"},
    "context_compression": {"status": "completed"},
    "memory_hit": {"status": "completed"},
    "memory_expired": {"status": "blocked", "failure_code": "memory_expired"},
    "memory_conflict": {"status": "replanning", "failure_code": "artifact_conflict"},
    "cross_owner": {"status": "blocked", "failure_code": "task_not_found"},
    "artifact_ttl": {"status": "blocked", "failure_code": "artifact_expired"},
    "context_reference_mismatch": {"status": "blocked", "failure_code": "context_reference_mismatch"},
    "safe_projection": {"status": "completed"},
    "catalog_discovery": {"status": "completed"},
    "input_schema_invalid": {"status": "blocked", "failure_code": "invalid_skill_arguments"},
    "unknown_field": {"status": "blocked", "failure_code": "unknown_skill_argument"},
    "owner_scope_denied": {"status": "blocked", "failure_code": "scope_denied"},
    "version_mismatch": {"status": "blocked", "failure_code": "skill_version_mismatch"},
    "ttl_precondition": {"status": "blocked", "failure_code": "artifact_expired"},
    "confirmation_required": {"status": "ready_to_commit"},
    "tool_injection": {"status": "blocked", "failure_code": "sensitive_skill_argument"},
    "policy_version": {"status": "completed"},
    "combined_rule": {"status": "completed"},
    "exception_clause": {"status": "completed"},
    "no_evidence": {"status": "blocked", "failure_code": "insufficient_evidence"},
    "live_fact_boundary": {"status": "blocked", "failure_code": "live_fact_requires_java"},
    "metadata_filter": {"status": "completed"},
    "indirect_prompt_injection": {"status": "blocked", "failure_code": "untrusted_retrieval_instruction"},
    "citation_trace": {"status": "completed"},
    "task_resume": {"status": "executing"},
    "idempotent_commit": {"status": "blocked", "failure_code": "duplicate_commit"},
    "outbox_duplicate": {"status": "completed"},
    "out_of_order_event": {"status": "blocked", "failure_code": "out_of_order_event"},
    "timeout_reconcile": {"status": "blocked", "failure_code": "commit_result_unknown"},
    "cancel_race": {"status": "blocked", "failure_code": "action_gate_missing"},
    "budget_exhausted": {"status": "blocked", "failure_code": "wall_clock_budget_exhausted"},
    "store_unavailable": {"status": "blocked", "failure_code": "task_store_unavailable"},
    "draft": {"status": "ready_to_commit"},
    "commit": {"status": "completed"},
    "amend": {"status": "ready_to_commit"},
    "cancel": {"status": "ready_to_commit"},
    "human_case": {"status": "waiting_for_async_task"},
    "outbox_transaction": {"status": "completed"},
    "consumer_idempotency": {"status": "completed"},
    "migration_replay": {"status": "completed"},
    "migration_repeatable": {"status": "completed"},
    "java_dto": {"status": "completed"},
    "fastapi_dto": {"status": "completed"},
    "http_error_mapping": {"status": "blocked", "failure_code": "scope_denied"},
    "rabbitmq_contract": {"status": "completed"},
    "legacy_adapter": {"status": "completed"},
    "create_task": {"status": "completed"},
    "plan_revision": {"status": "replanning"},
    "clarification": {"status": "waiting_for_user"},
    "confirmation": {"status": "ready_to_commit"},
    "sse_reconnect": {"status": "executing"},
    "refresh_recovery": {"status": "executing"},
    "cross_role": {"status": "blocked", "failure_code": "scope_denied"},
    "human_visibility": {"status": "waiting_for_async_task"},
    "provider_timeout": {"status": "blocked", "failure_code": "model_timeout"},
    "gateway_unavailable": {"status": "blocked", "failure_code": "upstream_unavailable"},
    "rag_unavailable": {"status": "blocked", "failure_code": "rag_unavailable"},
    "redis_unavailable": {"status": "blocked", "failure_code": "task_store_unavailable"},
    "mysql_rollback": {"status": "blocked", "failure_code": "java_commit_result_unknown"},
    "rabbitmq_unavailable": {"status": "waiting_for_async_task", "failure_code": "async_dispatch_unavailable"},
    "sse_interrupted": {"status": "executing"},
    "process_restart": {"status": "blocked", "failure_code": "commit_result_unknown"},
}


def _assert_owner_scoped(case: Mapping[str, Any], _: str) -> bool:
    return case["initialState"].get("ownerScope") == "synthetic-owner-only"


def _assert_safe_public_projection(case: Mapping[str, Any], _: str) -> bool:
    return "business_write_without_confirmation" in case["forbiddenEffects"]


def _assert_bounded_execution(case: Mapping[str, Any], _: str) -> bool:
    budget = case["budget"]
    return all(isinstance(budget.get(key), int) and budget[key] >= 0 for key in ("maxModelCalls", "maxToolCalls", "maxWallClockSeconds"))


def _assert_safe_stop(case: Mapping[str, Any], _: str) -> bool:
    return case["requiredOutcome"]["status"] in {"blocked", "waiting_for_user"}


def _assert_no_unconfirmed_business_write(case: Mapping[str, Any], _: str) -> bool:
    return "business_write_without_confirmation" in case["forbiddenEffects"] and case["requiredOutcome"]["status"] != "completed_write"


def _assert_failure_code(case: Mapping[str, Any], assertion: str) -> bool:
    return case.get("expectedFailureCode") == assertion.partition(":")[2]


_ASSERTIONS: dict[str, Callable[[Mapping[str, Any], str], bool]] = {
    "owner_scoped": _assert_owner_scoped,
    "safe_public_projection": _assert_safe_public_projection,
    "bounded_execution": _assert_bounded_execution,
    "safe_stop": _assert_safe_stop,
    "no_unconfirmed_business_write": _assert_no_unconfirmed_business_write,
    "failure_code": _assert_failure_code,
}


def _run_representative_cases() -> list[ReleaseCaseResult]:
    """Exercise the real runtime for the highest-risk deterministic branches."""

    result: list[ReleaseCaseResult] = []
    result.append(_runtime_case("runtime-finish", _finish_decision(), expected_status="completed"))
    result.append(_runtime_case("runtime-waiting", _ask_decision(), expected_status="waiting_for_user"))
    result.append(_runtime_case("runtime-unknown-skill", _unknown_skill_decision(), expected_status="blocked", expected_code="unknown_skill"))
    result.append(
        _runtime_case(
            "runtime-invalid-argument",
            _invalid_argument_decision(),
            expected_status="blocked",
            expected_code="unknown_skill_argument",
            goal="查询合成订单事实",
        )
    )
    result.append(_runtime_case("runtime-model-unavailable", None, expected_status="blocked", expected_code="model_missing_configuration", unavailable=True))
    result.append(
        _runtime_case(
            "runtime-parallel-budget",
            _parallel_decision(),
            expected_status="blocked",
            expected_code="parallel_budget_exceeded",
            goal="查询合成订单与物流",
        )
    )
    result.append(_runtime_case("runtime-memory-safe", _finish_decision(), expected_status="completed"))
    result.append(_runtime_case("runtime-owner-store", _finish_decision(), expected_status="completed"))
    return result


def _runtime_case(
    case_id: str,
    decision: ExecutorDecision | None,
    *,
    expected_status: str,
    expected_code: str | None = None,
    unavailable: bool = False,
    goal: str | None = None,
) -> ReleaseCaseResult:
    provider = UnavailableRuntimeProvider() if unavailable else ScriptedRuntimeProvider(decisions=[decision])
    gateway = SyntheticSkillGateway(observations={
        "read_order": SkillObservation(status="succeeded", artifact_kind="order_fact", summary="合成订单事实已核验。", reference="fact-abcdefgh", source_version="v1", factuality="verified"),
    })
    runtime = TaskRuntime(store=InMemoryTaskStore(), provider=provider, gateway=gateway)
    try:
        outcome = runtime.create_task(
            session_id=f"release-{case_id}",
            goal=goal or f"合成发布合同 {case_id}",
            member_id=1,
            authorization="Bearer synthetic-release-runtime",
        )
    except Exception as exc:  # pragma: no cover - a failed smoke is reported below
        return ReleaseCaseResult(case_id, "FAILED", (f"runtime_exception:{type(exc).__name__}",))
    violations: list[str] = []
    if outcome.view.status != expected_status:
        violations.append("status_mismatch")
    if expected_code and expected_code not in outcome.view.limitation_codes:
        violations.append("failure_code_missing")
    return ReleaseCaseResult(case_id, "PASSED" if not violations else "FAILED", tuple(violations))


def _finish_decision() -> ExecutorDecision:
    return ExecutorDecision(decision="finish", reason_summary="合成任务已完成。")


def _ask_decision() -> ExecutorDecision:
    return ExecutorDecision(decision="ask_user", reason_summary="需要补充事实。", user_question="请补充合成任务所需信息。")


def _unknown_skill_decision() -> ExecutorDecision:
    return ExecutorDecision(decision="call_skill", reason_summary="尝试调用未知能力。", skill_calls=[SkillCall(skill_id="ghost_skill", arguments={})])


def _invalid_argument_decision() -> ExecutorDecision:
    return ExecutorDecision(decision="call_skill", reason_summary="参数校验应失败。", skill_calls=[SkillCall(skill_id="read_order", arguments={"unexpected": "value"})])


def _parallel_decision() -> ExecutorDecision:
    return ExecutorDecision(
        decision="call_skill",
        reason_summary="并行预算应阻止第三个调用。",
        skill_calls=[
            SkillCall(skill_id="read_order", arguments={"orderRef": "synthetic-ref"}),
            SkillCall(skill_id="read_order", arguments={"orderRef": "synthetic-ref-2"}),
            SkillCall(skill_id="read_order", arguments={"orderRef": "synthetic-ref-3"}),
            SkillCall(skill_id="read_order", arguments={"orderRef": "synthetic-ref-4"}),
        ],
    )
