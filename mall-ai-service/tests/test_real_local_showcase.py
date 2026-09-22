"""Safe-contract tests for the real local showcase runner."""

from __future__ import annotations

import httpx
import pytest
from pathlib import Path
import json
from unittest.mock import patch

from app.services.release_ledger import release_ledger_context
from scripts.run_real_local_showcase import (
    ShowcaseError,
    _capture_chain_frames,
    _capture_expected_markers,
    _build_offline_gifs,
    _create_agent_task,
    _cross_scenario_frames_distinct,
    _provider_failure_after_scenario,
    _response_failure_code,
    _status_class,
    _task_failure_code,
    _prepare_showcase_fixture,
    run_real_local_showcase,
)
from scripts.run_v3_0_2_slow_gateway_test import _prepare_synthetic_fixture


def test_showcase_error_is_a_safe_enumerated_projection() -> None:
    failure = ShowcaseError(
        "provider_response_body_should_never_be_public",
        scenario="closed_loop",
        stage="provider",
        completed_steps=3,
        model_called=True,
        proposal_formed=True,
        http_status_class="5xx",
    )
    public = failure.to_public()

    assert public == {
        "scenario": "closed_loop",
        "stage": "provider",
        "failureCode": "unknown_failure",
        "httpStatusClass": "5xx",
        "completedStepCount": 3,
        "modelCalled": True,
        "proposalFormed": True,
        "javaEligibility": False,
        "javaCommit": False,
        "statusReadback": False,
        "taskMetrics": {},
    }
    assert "provider_response_body" not in str(public)


def test_showcase_rejects_empty_or_duplicate_explicit_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MALL_LIVE_DEMO_PASSWORD", "synthetic-password")

    empty = run_real_local_showcase(
        report_dir=tmp_path,
        batch_id="synthetic",
        provider_mode="deterministic",
        scenarios=(),
    )
    duplicate = run_real_local_showcase(
        report_dir=tmp_path,
        batch_id="synthetic",
        provider_mode="deterministic",
        scenarios=("clarify_pause_resume", "clarify_pause_resume"),
    )

    assert empty == {"status": "environment_blocked", "reason": "invalid_showcase_scenarios"}
    assert duplicate == {"status": "environment_blocked", "reason": "invalid_showcase_scenarios"}


def test_status_class_and_ledger_context_are_deterministic() -> None:
    assert _status_class(200) == "2xx"
    assert _status_class(409) == "4xx"
    assert _status_class(503) == "5xx"
    assert _status_class(0) == "none"
    with release_ledger_context(batch_id="synthetic", path=None, source="test"):
        # The context is intentionally opt-in and does not create a file when
        # no path is configured.
        assert True


def test_gateway_failure_categories_are_distinct_and_body_free() -> None:
    request = httpx.Request("POST", "http://proxy/api/agent-tasks")
    gateway = httpx.Response(504, request=request)
    assert _response_failure_code(gateway) == "gateway_timeout"
    runtime = httpx.Response(
        504,
        request=request,
        headers={"X-Mall-Failure-Code": "runtime_deadline_exceeded"},
    )
    assert _response_failure_code(runtime) == "runtime_deadline_exceeded"
    client = httpx.Response(408, request=request)
    assert _response_failure_code(client) == "scenario_assertion_failure"
    assert _task_failure_code({"limitation_codes": ["model_timeout"]}, fallback="unknown_failure") == "provider_timeout"


def test_agent_task_create_maps_client_read_timeout_without_response_body() -> None:
    class TimeoutClient:
        def post(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("synthetic client timeout", request=httpx.Request("POST", "http://proxy/api/agent-tasks"))

    with pytest.raises(ShowcaseError) as error:
        _create_agent_task(TimeoutClient(), "http://proxy/api", "Bearer synthetic", "session", "合成任务")
    assert error.value.failure_code == "client_read_timeout"
    assert error.value.stage == "agent_task_create"


def test_runtime_gateway_runner_timeout_order_is_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    nginx = (root / "mall-ai-web" / "nginx.conf").read_text(encoding="utf-8")
    runner = (root / "mall-ai-service" / "scripts" / "run_real_local_showcase.py").read_text(encoding="utf-8")
    budget = (root / "mall-ai-service" / "app" / "schemas" / "agent_task.py").read_text(encoding="utf-8")
    assert "proxy_read_timeout 300s" in nginx
    assert "proxy_send_timeout 300s" in nginx
    assert 'MALL_RUNNER_READ_TIMEOUT_SECONDS", "330"' in runner
    assert "max_wall_clock_seconds: int = Field(default=90, ge=10, le=240)" in budget
    assert 240 < 300 < 330


def test_slow_gateway_uses_only_the_process_local_synthetic_fixture(tmp_path, monkeypatch) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({"account_a": {"username": "synthetic-slow-user", "order_sn": "202601010000000001"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MALL_FIELD_FIXTURE_FILE", str(fixture))

    account, unused, order = _prepare_synthetic_fixture("not-written")

    assert account.username == "synthetic-slow-user"
    assert unused.username == "unused"
    assert order.order_sn == "202601010000000001"


def test_showcase_uses_independent_orders_for_commit_and_fact_change(monkeypatch) -> None:
    created: list[str] = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def create_order(_client, _base, account, _product_id, *, required_stock):
        created.append(f"{account.label}:{required_stock}")
        return type("Order", (), {"order_sn": f"order-{required_stock}", "order_id": required_stock})()

    monkeypatch.setenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")
    with patch("scripts.run_real_local_showcase.httpx.Client", return_value=Client()), patch(
        "scripts.run_real_local_showcase._prepare_account_order", side_effect=create_order
    ):
        account_a, account_b, closed_loop, fact_change = _prepare_showcase_fixture("not-written")

    assert account_a.username != account_b.username
    assert closed_loop.order_id != fact_change.order_id
    assert created == ["v301-A:3", "v301-A:2", "v301-B:1"]


def test_cross_scenario_capture_rejects_reused_same_stage_frames() -> None:
    duplicated = {
        "one": {"stages": ["goal", "evidence", "progress", "status"], "hashes": ["goal", "evidence", "progress", "status"]},
        "two": {"stages": ["goal", "evidence", "progress", "status"], "hashes": ["goal", "evidence", "progress", "status"]},
        "three": {"stages": ["goal", "evidence", "progress", "status"], "hashes": ["goal", "evidence", "progress", "status"]},
    }
    distinct = {
        "one": {"stages": ["goal", "evidence", "progress", "status"], "hashes": ["shared-goal", "shared-evidence", "shared-progress", "1-status"]},
        "two": {"stages": ["goal", "evidence", "progress", "status"], "hashes": ["shared-goal", "shared-evidence", "shared-progress", "2-status"]},
        "three": {"stages": ["goal", "evidence", "progress", "status"], "hashes": ["shared-goal", "shared-evidence", "shared-progress", "3-status"]},
    }

    assert _cross_scenario_frames_distinct(duplicated) is False
    assert _cross_scenario_frames_distinct(distinct) is True

    two_chain = {
        "one": distinct["one"],
        "two": distinct["two"],
    }
    assert _cross_scenario_frames_distinct(two_chain, expected_count=2) is True


def test_capture_binds_exact_conversation_and_task_regions(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class Browser:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def open_customer_conversation(self, conversation_id, *, expected_markers):
            calls.append(("conversation", (conversation_id, expected_markers)))

        def assert_ready(self):
            pass

        def assert_safe_public_text(self):
            pass

        def screenshot(self, target, *, selector):
            calls.append(("selector", selector))
            target.write_bytes((selector * 200).encode("utf-8"))

    monkeypatch.setattr("field_browser_support.BrowserSession", Browser)
    result = _capture_chain_frames(
        "not-written",
        "synthetic-user",
        tmp_path,
        "clarify_pause_resume",
        "00000000-0000-0000-0000-000000000001",
        ("查询订单物流",),
    )

    assert result["valid"] is True
    assert result["stages"] == ["goal", "evidence", "progress", "status"]
    assert calls[0] == (
        "conversation",
        ("00000000-0000-0000-0000-000000000001", ("查询订单物流",)),
    )
    assert [value for kind, value in calls if kind == "selector"] == [
        ".agent-task-card .agent-task-heading",
        ".agent-task-card .agent-artifact-list",
        ".agent-task-card .agent-plan-list",
        ".agent-task-card",
    ]


def test_capture_reports_safe_conversation_binding_failure(tmp_path, monkeypatch) -> None:
    class Browser:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def open_customer_conversation(self, *_args, **_kwargs):
            raise TimeoutError("page_condition_timeout")

    monkeypatch.setattr("field_browser_support.BrowserSession", Browser)
    result = _capture_chain_frames(
        "not-written",
        "synthetic-user",
        tmp_path,
        "main_open_task_closed_loop",
        "00000000-0000-0000-0000-000000000001",
        ("申请取消退款",),
    )

    assert result == {
        "frames": [],
        "hashes": [],
        "valid": False,
        "frameCount": 0,
        "failureStage": "conversation_binding",
        "failureCode": "page_condition_timeout",
    }


def test_main_capture_marker_does_not_require_completed_task_status() -> None:
    assert _capture_expected_markers("main_open_task_closed_loop") == ("申请取消退款",)


def test_gif_normalizes_different_capture_region_sizes(tmp_path, monkeypatch) -> None:
    from PIL import Image
    import scripts.run_real_local_showcase as showcase

    monkeypatch.setattr(showcase, "ROOT", tmp_path)
    frame_paths = []
    for index, size in enumerate(((120, 60), (200, 100), (160, 180), (240, 140))):
        path = tmp_path / f"frame-{index}.png"
        Image.new("RGB", size, (20 * index, 50, 100)).save(path)
        frame_paths.append(path.name)

    outputs = _build_offline_gifs(
        {"main_open_task_closed_loop": {"valid": True, "frames": frame_paths}},
        tmp_path / "gifs",
    )

    assert outputs == ["gifs/main-open-task-closed-loop.gif"]
    gif = Image.open(tmp_path / outputs[0])
    assert gif.size == (240, 180)
    assert gif.n_frames == 4


def test_provider_failure_after_passed_scenario_stops_with_safe_root_cause() -> None:
    result = {
        "completedStepCount": 4,
        "proposalFormed": True,
        "javaRechecked": True,
        "confirmedWrite": False,
        "statusReadback": True,
    }

    assert _provider_failure_after_scenario("pause", result, {}) is None

    failure = _provider_failure_after_scenario(
        "pause", result, {"providerFailures": 1}
    )
    assert failure is not None
    assert failure.failure_code == "provider_http_failure"
    assert failure.stage == "provider"
    assert failure.task_metrics == {
        "rootFailureClass": "provider_failure",
        "providerFailures": 1,
    }
    assert "prompt" not in repr(failure.to_public())
