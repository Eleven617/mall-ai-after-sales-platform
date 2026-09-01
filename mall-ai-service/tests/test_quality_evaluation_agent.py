import json
from unittest.mock import patch

from app.schemas.quality import QualityFailureAnalysis
from app.services.llm_service import LLMResponse
from app.services.quality_evaluation_agent import (
    DEFAULT_SUITE_PATH,
    LIVE_MODEL_SYNTHETIC_SUITE_PATH,
    QualityRunReplayError,
    load_quality_suite,
    replay_quality_evaluation,
    run_quality_evaluation,
)
from app.services.evaluation_profile_service import get_evaluation_profile
from app.services.operations_agent import OperationsAnalysisError
from app.services.trace_service import InMemoryTraceSink, set_trace_sink_for_tests


def test_committed_quality_suite_is_repeatable_offline_and_does_not_emit_trace():
    sink = InMemoryTraceSink()
    set_trace_sink_for_tests(sink)
    try:
        report = run_quality_evaluation()
    finally:
        set_trace_sink_for_tests(None)

    assert report.suite_version == "quality-agent.v2"
    assert (report.total, report.passed, report.failed) == (17, 17, 0)
    assert report.execution_mode == "contract_mock"
    assert report.environment_blocked is False
    assert sink.events == []
    encoded = report.model_dump_json()
    assert "synthetic raw input" not in encoded
    assert "synthetic-order-value" not in encoded
    assert "synthetic-only-value" not in encoded
    assert "synthetic-tool-only" not in encoded


def test_fact_threshold_and_expected_rejection_contracts_are_covered():
    report = run_quality_evaluation()
    cases = {case.case_id: case for case in report.cases}

    facts_incomplete = cases["customer-order-only-never-policy-insufficient"]
    assert facts_incomplete.status == "PASSED"
    assert "facts_incomplete" in facts_incomplete.actual
    assert "policy_insufficient" not in facts_incomplete.actual

    sensitive = cases["customer-sensitive-handoff-is-rejected"]
    assert sensitive.status == "PASSED"
    assert sensitive.expected_rejection_detected is True
    assert "sensitive_field_leak" in sensitive.violations
    assert "order_sn" not in sensitive.actual

    write_claim = cases["operations-write-claim-is-rejected"]
    assert write_claim.status == "PASSED"
    assert write_claim.expected_rejection_detected is True
    assert write_claim.violations == ["operations_write_claim"]

    blocked_tool = cases["customer-unapproved-tool-is-blocked"]
    assert blocked_tool.status == "PASSED"
    assert blocked_tool.expected_rejection_detected is True
    assert blocked_tool.trajectory is not None
    assert blocked_tool.trajectory.tool_sequence == []
    assert "tool_blocked" in blocked_tool.trajectory.terminal_events

    timeout = cases["customer-time-budget-stops-safely"]
    assert timeout.status == "PASSED"
    assert timeout.trajectory is not None
    assert timeout.trajectory.tool_sequence == []
    assert "timeout" in timeout.trajectory.terminal_events


def test_real_regression_failure_remains_failed_when_not_marked_as_expected_rejection(tmp_path):
    payload = json.loads(DEFAULT_SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"][-1]["expectedContract"]["expectedRejection"] = False
    suite_path = tmp_path / "quality_cases.json"
    suite_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = run_quality_evaluation(suite_path=suite_path)

    assert report.failed == 1
    failed = next(case for case in report.cases if case.status == "FAILED")
    assert "unsupported_operations_metric_number" in failed.violations


def test_ai_failure_analysis_is_not_requested_for_expected_red_team_rejections():
    called_case_ids: list[str] = []

    def fake_analysis(case, _expected, _actual, _violations):
        called_case_ids.append(case.case_id)
        return QualityFailureAnalysis(
            failure_type="contract_regression",
            explanation="仅供人工检查。",
            candidate_regression_case="补充同类合成案例。",
            recommended_fix_area="质量评测边界",
            requires_human_approval=True,
        )

    report = run_quality_evaluation(
        enable_ai_failure_analysis=True,
        failure_analysis_fn=fake_analysis,
    )

    assert called_case_ids == []
    assert all(
        case.failure_analysis is None or case.failure_analysis.requires_human_approval
        for case in report.cases
    )


def test_ai_failure_analysis_is_requested_only_after_a_real_failed_contract(tmp_path):
    called_case_ids: list[str] = []
    payload = json.loads(DEFAULT_SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"][-1]["expectedContract"]["expectedRejection"] = False
    suite_path = tmp_path / "quality_cases.json"
    suite_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def fake_analysis(case, _expected, _actual, _violations):
        called_case_ids.append(case.case_id)
        return QualityFailureAnalysis(
            failure_type="contract_regression",
            explanation="仅供人工检查。",
            candidate_regression_case="补充同类合成案例。",
            recommended_fix_area="质量评测边界",
            requires_human_approval=True,
        )

    report = run_quality_evaluation(
        suite_path=suite_path,
        enable_ai_failure_analysis=True,
        failure_analysis_fn=fake_analysis,
    )

    assert report.failed == 1
    assert called_case_ids == ["operations-unsupported-number-is-rejected"]
    failed = next(case for case in report.cases if case.status == "FAILED")
    assert failed.failure_analysis is not None
    assert failed.failure_analysis.requires_human_approval is True


def test_unavailable_ai_failure_analysis_does_not_change_deterministic_result():
    def unavailable_analysis(*_args):
        raise RuntimeError("synthetic provider outage")

    report = run_quality_evaluation(
        enable_ai_failure_analysis=True,
        failure_analysis_fn=unavailable_analysis,
    )

    assert (report.total, report.passed, report.failed) == (17, 17, 0)
    assert all(case.failure_analysis is None for case in report.cases)


def test_suite_has_only_versioned_synthetic_inputs():
    suite = load_quality_suite()
    assert all(case.schema_version == "1" for case in suite.cases)
    assert all("2026" not in case.synthetic_input for case in suite.cases)


def test_live_model_suite_is_versioned_and_contains_only_real_model_cases():
    suite = load_quality_suite(LIVE_MODEL_SYNTHETIC_SUITE_PATH)

    assert suite.version == "live-model-synthetic.v1"
    assert len(suite.cases) == 3
    assert all(case.model_behavior == "tool_plan" for case in suite.cases)


def test_contract_mock_never_touches_pending_customer_state():
    with (
        patch(
            "app.services.unified_after_sales_graph.handle_pending_after_sales_action_confirmation"
        ) as pending_action,
        patch(
            "app.services.unified_after_sales_graph.handle_pending_after_sales_modification_draft"
        ) as pending_modification,
        patch(
            "app.services.unified_after_sales_graph.handle_pending_after_sales_confirmation"
        ) as pending_confirmation,
        patch(
            "app.services.unified_after_sales_graph.handle_pending_after_sales_draft"
        ) as pending_draft,
    ):
        report = run_quality_evaluation()

    assert report.failed == 0
    pending_action.assert_not_called()
    pending_modification.assert_not_called()
    pending_confirmation.assert_not_called()
    pending_draft.assert_not_called()


def test_live_model_environment_failure_is_reported_without_becoming_a_false_pass(tmp_path):
    payload = json.loads(LIVE_MODEL_SYNTHETIC_SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"] = [payload["cases"][-1]]
    suite_path = tmp_path / "live_operations_only.json"
    suite_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with patch(
        "app.services.quality_evaluation_agent.analyze_case",
        side_effect=OperationsAnalysisError("provider unavailable", category="environment"),
    ):
        report = run_quality_evaluation(
            suite_path=suite_path,
            execution_mode="live_model_synthetic",
        )

    assert (report.total, report.passed, report.failed) == (1, 0, 1)
    assert report.environment_blocked is True
    assert report.cases[0].environment_blocked is True


def test_live_model_synthetic_uses_zero_temperature_without_real_tool_access(tmp_path):
    payload = json.loads(LIVE_MODEL_SYNTHETIC_SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"] = [payload["cases"][0]]
    suite_path = tmp_path / "live_customer_only.json"
    suite_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    responses = [
        LLMResponse(tool_calls=[{"name": "order_service", "arguments": {"order_sn": "synthetic-order-reference"}}]),
        LLMResponse(tool_calls=[{"name": "logistics_service", "arguments": {"order_sn": "synthetic-order-reference"}}]),
        LLMResponse(tool_calls=[{"name": "rag_search", "arguments": {"query": "合成售后政策"}}]),
    ]

    with patch(
        "app.services.quality_evaluation_agent.generate_with_tools",
        side_effect=responses,
    ) as generate_with_tools:
        report = run_quality_evaluation(
            suite_path=suite_path,
            execution_mode="live_model_synthetic",
        )

    assert report.failed == 0
    assert generate_with_tools.call_count == 3
    assert all(call.kwargs["temperature"] == 0 for call in generate_with_tools.call_args_list)


def test_replay_rejects_fixture_hash_mismatch_before_any_agent_execution():
    source = run_quality_evaluation()
    suite = load_quality_suite()
    assert source.run_manifest is not None
    corrupted_manifest = source.run_manifest.model_copy(update={"fixture_hash": "0" * 64})
    corrupted_source = source.model_copy(update={"run_manifest": corrupted_manifest})

    with patch("app.services.quality_evaluation_agent._execute_case") as execute_case:
        try:
            replay_quality_evaluation(
                source_run=corrupted_source,
                profile=get_evaluation_profile("contract_mock"),
                fixtures=tuple(suite.cases),
            )
        except QualityRunReplayError as exc:
            assert "夹具版本不一致" in str(exc)
        else:
            raise AssertionError("fixture mismatch must be rejected before replay")

    execute_case.assert_not_called()
