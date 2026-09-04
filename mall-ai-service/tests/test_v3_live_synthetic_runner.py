"""Contract tests for the manual v3 live-synthetic runner.

These tests replace the real model with declared TurnPlans.  They prove that
every registered manifest case is executed exactly its declared number of
times and that the runner refuses to turn unavailable-model results into
passes; real model calls stay explicit manual validation.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_v3_live_synthetic.py"
    spec = importlib.util.spec_from_file_location("v3_live_synthetic_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_maps_each_registered_case_to_a_safe_versioned_template(monkeypatch) -> None:
    runner = _runner_module()
    templates = runner.load_template_cases()
    expected_by_message = {
        item["syntheticInput"]: item["expectedPlan"]
        for item in templates.values()
    }
    seen_contexts: list[str] = []

    def fake_detect_intent(message: str, _context: str):
        seen_contexts.append(_context)
        expected = expected_by_message[message]
        return SimpleNamespace(
            business_intent=expected.get("businessIntent", "unknown"),
            task_relation=expected.get(
                "taskRelation",
                expected.get("taskRelationAnyOf", ["standalone_answer"])[0],
            ),
            route=expected.get("route", "after_sales_flow"),
            task_kind=expected.get("taskKind"),
            confirmation_intent=expected.get("confirmationIntent", "none"),
        )

    monkeypatch.setattr(runner, "detect_intent", fake_detect_intent)
    results, summary = runner.run_manifest_live_synthetic(max_total_seconds=60)

    assert summary["manifestLiveCases"] == 36
    assert summary["executedRuns"] == 108
    assert summary["passed"] == 108
    assert summary["failed"] == 0
    assert summary["environmentBlocked"] == 0
    assert {result.template_id for result in results} == set(runner.SCENARIO_TEMPLATE_IDS.values())
    assert seen_contexts
    assert all("synthetic_evaluation_case" not in context for context in seen_contexts)
    assert all("synthetic_evaluation_variation" not in context for context in seen_contexts)


def test_runner_keeps_model_unavailability_visible(monkeypatch) -> None:
    runner = _runner_module()

    def unavailable(_message: str, _context: str):
        raise runner.IntentServiceError("synthetic unavailable")

    monkeypatch.setattr(runner, "detect_intent", unavailable)
    results, summary = runner.run_manifest_live_synthetic(max_total_seconds=60)

    assert summary["passed"] == 0
    assert summary["environmentBlocked"] == 108
    assert all(result.status == "ENVIRONMENT_BLOCKED" for result in results)
    assert all(result.violations == ("p0_unavailable_or_contract_error",) for result in results)
