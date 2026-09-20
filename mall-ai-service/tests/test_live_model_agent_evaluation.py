"""Contract tests for the explicit open-task Agent evaluation runner."""
from __future__ import annotations

import json

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


def test_holdout_v3_allows_required_resolution_read_without_mutating_v2() -> None:
    from app.runtime.contract_replay_evaluation import HOLDOUT_SUITE_PATH

    suite = load_live_agent_suite(HOLDOUT_SUITE_PATH)
    by_id = {case["caseId"]: case for case in suite["cases"]}
    assert suite["suiteVersion"] == "live-model-agent-runtime-holdout.v3"
    assert "build_service_resolution" in by_id["holdout-open-011"]["expect"]["allowed_skills"]
    assert "build_service_resolution" in by_id["holdout-open-012"]["expect"]["allowed_skills"]
    original = json.loads(
        (HOLDOUT_SUITE_PATH.parent / "live_model_agent_holdout_cases.v2.json").read_text(encoding="utf-8")
    )
    original_by_id = {case["caseId"]: case for case in original["cases"]}
    assert "build_service_resolution" not in original_by_id["holdout-open-011"]["expect"]["allowed_skills"]


def test_unlisted_skill_remains_an_irrelevant_call_failure() -> None:
    from app.runtime.live_model_agent_evaluation import _contract_failures

    class View:
        status = "completed"
        action = None

    class Gateway:
        invocations = ["read_order", "unreviewed_read"]
        commits = []

    case = {"expect": {"allowed_skills": ["read_order"], "proposal": "forbidden"}}
    assert _contract_failures(case, View(), Gateway(), proposal_present=False) == ["irrelevant_skill_call"]


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
    assert report["model"]["model"] == "deepseek-flash"
    assert report["model"]["thinkingMode"] == "enabled"
    assert report["model"]["reasoningEffort"] == "high"
    assert len(report["model"]["runtimeCommit"]) == 40


def test_replay_proposal_uses_server_confirmation_executor_mapping() -> None:
    from app.runtime.contract_replay_evaluation import _provider_factory

    report = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        case_ids={"agent-open-020"},
        required_runs=1,
        max_total_seconds=30,
        provider_factory=_provider_factory,
    )
    row = report["cases"][0]
    assert row["status"] == "passed"
    assert row["proposalSkill"] == "create_after_sales_draft"
    assert row["confirmationExecutorSkill"] == "commit_after_sales_action"
    assert row["businessWriteCount"] == 0
