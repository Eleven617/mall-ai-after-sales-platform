"""Contract tests for the explicit open-task Agent evaluation runner."""
from __future__ import annotations

from app.runtime.live_model_agent_evaluation import (
    DEFAULT_SUITE_PATH,
    load_live_agent_suite,
    run_live_model_agent_evaluation,
)
from app.runtime.providers import ScriptedRuntimeProvider
from app.runtime.task_runtime import TaskRuntime
from app.schemas.agent_task import ExecutorDecision


def test_open_task_suite_has_unique_hashed_cases() -> None:
    suite = load_live_agent_suite(DEFAULT_SUITE_PATH)
    cases = suite["cases"]
    assert len(cases) >= 24
    assert len({case["caseId"] for case in cases}) == len(cases)
    assert all(len(case["fixtureHash"]) == 64 for case in cases)


def test_fault_injected_model_case_proves_safe_stop_without_environment_claim() -> None:
    report = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        case_ids={"agent-open-019"},
        max_total_seconds=30,
    )

    assert report["uniqueCases"] == 1
    assert report["executedRuns"] == 3
    assert report["passed"] == 3
    assert report["failed"] == 0
    assert report["environmentBlocked"] == 0
    assert report["forbiddenSideEffects"] == 0


def test_runner_can_replay_a_contract_case_without_calling_a_provider() -> None:
    def provider_factory(_case):
        return ScriptedRuntimeProvider(
            decisions=[
                ExecutorDecision(
                    decision="ask_user",
                    reason_summary="需要补充合成订单标识。",
                    user_question="请补充合成订单标识后继续。",
                )
            ]
        )

    report = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        case_ids={"agent-open-001"},
        max_total_seconds=30,
        provider_factory=provider_factory,
    )

    assert report["executedRuns"] == 3
    assert report["passed"] == 3
    assert report["environmentBlocked"] == 0
    assert report["llm"]["total_calls"] == 0
