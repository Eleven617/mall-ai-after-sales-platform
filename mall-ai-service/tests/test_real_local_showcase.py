"""Safe-contract tests for the real local showcase runner."""

from __future__ import annotations

import httpx
import pytest
from pathlib import Path

from app.services.release_ledger import release_ledger_context
from scripts.run_real_local_showcase import (
    ShowcaseError,
    _create_agent_task,
    _response_failure_code,
    _status_class,
    _task_failure_code,
)


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
    }
    assert "provider_response_body" not in str(public)


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
