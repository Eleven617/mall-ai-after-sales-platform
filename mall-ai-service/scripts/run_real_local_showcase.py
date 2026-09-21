"""Run the three real local v3 showcase chains in one process.

This runner is intentionally separate from the synthetic contract evaluator.
It uses disposable Java-created accounts/orders, the Vue proxy, FastAPI, the
real local Compose dependencies through the public Agent Task Runtime API.
The external model can be selected explicitly as ``deterministic``, ``replay``
or ``live``.  The report is a safe projection: identifiers, credentials, raw
messages and response bodies remain process-local and are never written.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
import argparse
from pathlib import Path
from typing import Any

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SERVICE_ROOT.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
if str(SERVICE_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from bootstrap_live_demo import DemoAccount, _prepare_account_order  # noqa: E402
from app.services.release_ledger import (
    append_release_event,
    read_release_events,
    release_ledger_context,
    summarize_release_events,
)


FORBIDDEN_PUBLIC_FIELDS = {
    "rag_sources",
    "rag_context",
    "retrieved_context",
    "tool_result",
    "tool_results",
    "intent",
    "trace",
    "trace_id",
    "proposal_id",
    "idempotency_key",
    "authorization",
    "token",
}


SAFE_FAILURE_CODES = {
    # Transport/runtime categories are intentionally separate from scenario
    # assertions so a gateway failure can be diagnosed without retaining a
    # response body.
    "gateway_timeout",
    "client_read_timeout",
    "runtime_deadline_exceeded",
    "provider_timeout",
    "provider_http_failure",
    "schema_failure",
    "scenario_assertion_failure",
    "fixture_prepare_failed",
    "login_failed",
    "conversation_create_failed",
    "public_answer_missing",
    "closed_loop_proposal_missing",
    "closed_loop_java_submission_missing",
    "status_readback_missing",
    "pause_waiting_task_missing",
    "pause_resume_task_changed",
    "fact_change_proposal_missing",
    "stale_proposal_was_submitted",
    "browser_capture_failed",
    "agent_task_create_failed",
    "agent_task_waiting_missing",
    "agent_task_resume_failed",
    "clarification_not_resumed",
    "proposal_not_formed_after_clarification",
    "policy_evidence_insufficient",
    "task_terminal_state_unexpected",
    "task_metrics_mismatch",
    "release_infrastructure_failure",
    "java_fact_transition_failed",
    "duplicate_confirmation_not_idempotent",
    "cross_account_scope_failed",
    "public_projection_leak",
    "ai_service_restart_failed",
    "ai_service_readiness_after_restart_failed",
    "unknown_failure",
}


class ShowcaseError(RuntimeError):
    """Safe, enumerable showcase failure; never stores an HTTP body."""

    def __init__(
        self,
        code: str,
        *,
        scenario: str = "unknown",
        stage: str = "unknown",
        completed_steps: int = 0,
        model_called: bool = False,
        proposal_formed: bool = False,
        java_eligibility: bool = False,
        java_commit: bool = False,
        status_readback: bool = False,
        http_status_class: str = "none",
        task_metrics: dict[str, Any] | None = None,
    ) -> None:
        self.failure_code = code if code in SAFE_FAILURE_CODES else "unknown_failure"
        self.scenario = scenario
        self.stage = stage
        self.completed_steps = max(0, int(completed_steps))
        self.model_called = bool(model_called)
        self.proposal_formed = bool(proposal_formed)
        self.java_eligibility = bool(java_eligibility)
        self.java_commit = bool(java_commit)
        self.status_readback = bool(status_readback)
        self.http_status_class = http_status_class if http_status_class in {"2xx", "4xx", "5xx", "none"} else "none"
        self.task_metrics = dict(task_metrics or {})
        super().__init__(self.failure_code)

    def for_scenario(self, scenario: str) -> "ShowcaseError":
        if self.scenario != "unknown":
            return self
        self.scenario = scenario
        return self

    def to_public(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "stage": self.stage,
            "failureCode": self.failure_code,
            "httpStatusClass": self.http_status_class,
            "completedStepCount": self.completed_steps,
            "modelCalled": self.model_called,
            "proposalFormed": self.proposal_formed,
            "javaEligibility": self.java_eligibility,
            "javaCommit": self.java_commit,
            "statusReadback": self.status_readback,
            "taskMetrics": self.task_metrics,
        }


def run_real_local_showcase(
    *,
    report_dir: Path,
    batch_id: str,
    provider_mode: str | None = None,
) -> dict[str, Any]:
    """Run all three chains through the single public Agent Task Runtime."""

    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        return {"status": "environment_blocked", "reason": "missing_process_fixture_password"}
    provider_mode = (provider_mode or os.getenv("MALL_RUNTIME_PROVIDER_MODE", "offline")).strip().lower()
    if provider_mode not in {"deterministic", "replay", "live", "offline"}:
        return {"status": "environment_blocked", "reason": "invalid_provider_mode"}
    report_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    ledger_path = os.getenv("MALL_RELEASE_LEDGER_PATH")
    chain_results: list[dict[str, Any]] = []
    frame_paths: list[str] = []
    frame_groups: dict[str, dict[str, Any]] = {}
    with release_ledger_context(batch_id=batch_id, path=ledger_path, source="showcase-host"):
        try:
            account_a, account_b, closed_loop_order, fact_change_order = _prepare_showcase_fixture(password)
        except (httpx.HTTPError, OSError, ValueError, RuntimeError):
            failure = ShowcaseError("fixture_prepare_failed", scenario="fixture", stage="fixture_prepare")
            append_release_event(
                event_type="scenario", operation="showcase.fixture", outcome="failed",
                failure_class="scenario_failure", scenario="fixture", stage="fixture_prepare",
                failure_code=failure.failure_code,
            )
            return _showcase_failure(batch_id, started, chain_results, frame_paths, failure, frame_groups)
        web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
        api_base = web_base + "/api"
        java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
        admin_base = os.getenv("MALL_ADMIN_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
        runner_timeout = httpx.Timeout(
            float(os.getenv("MALL_RUNNER_READ_TIMEOUT_SECONDS", "330")),
            connect=10.0,
            write=10.0,
            pool=10.0,
        )
        try:
            with httpx.Client(
                timeout=runner_timeout,
                trust_env=False,
                headers={"X-Mall-Release-Batch-Id": batch_id, **_provider_headers()},
            ) as client:
                auth_a = _login(client, api_base, account_a.username, password)
                auth_b = _login(client, api_base, account_b.username, password)
                for scenario, callback in (
                    ("main_open_task_closed_loop", lambda: _agent_closed_loop(client, api_base, auth_a, auth_b, closed_loop_order.order_sn)),
                    ("clarify_pause_resume", lambda: _agent_pause_resume(client, api_base, auth_a, closed_loop_order.order_sn)),
                    ("fact_change_replan", lambda: _agent_fact_change_replan(client, api_base, admin_base, auth_a, fact_change_order.order_id, fact_change_order.order_sn, password)),
                ):
                    client.headers["X-Mall-Release-Scenario"] = scenario
                    try:
                        result = callback()
                    except ShowcaseError as exc:
                        failure = exc.for_scenario(scenario)
                        chain_results.append(failure.to_public())
                        append_release_event(
                            event_type="scenario", operation=f"showcase.{scenario}", outcome="failed",
                            failure_class="scenario_failure", scenario=scenario, stage=failure.stage,
                            failure_code=failure.failure_code, completed_step_count=failure.completed_steps,
                            model_called=failure.model_called, proposal_formed=failure.proposal_formed,
                            java_eligibility=failure.java_eligibility, java_commit=failure.java_commit,
                            status_readback=failure.status_readback,
                        )
                        return _showcase_failure(batch_id, started, chain_results, frame_paths, failure, frame_groups)
                    capture_session_id = result.pop("_captureSessionId", None)
                    if not isinstance(capture_session_id, str):
                        failure = ShowcaseError(
                            "browser_capture_failed",
                            scenario=scenario,
                            stage="capture_context",
                        )
                        return _showcase_failure(
                            batch_id, started, chain_results, frame_paths, failure, frame_groups
                        )
                    chain_results.append(result)
                    provider_usage = _provider_usage(batch_id)
                    failure = _provider_failure_after_scenario(
                        scenario, result, provider_usage
                    )
                    if failure is not None:
                        append_release_event(
                            event_type="scenario",
                            operation=f"showcase.{scenario}",
                            outcome="failed",
                            failure_class="scenario_failure",
                            scenario=scenario,
                            stage="provider",
                            failure_code=failure.failure_code,
                            completed_step_count=failure.completed_steps,
                            model_called=True,
                            proposal_formed=failure.proposal_formed,
                            java_eligibility=failure.java_eligibility,
                            java_commit=failure.java_commit,
                            status_readback=failure.status_readback,
                        )
                        return _showcase_failure(
                            batch_id,
                            started,
                            chain_results,
                            frame_paths,
                            failure,
                            frame_groups,
                        )
                    captured = _capture_chain_frames(
                        password,
                        account_a.username,
                        report_dir / "browser",
                        scenario,
                        capture_session_id,
                        _capture_expected_markers(scenario),
                    )
                    frame_groups[scenario] = captured
                    frame_paths.extend(captured["frames"])
                    if not captured["valid"]:
                        failure = ShowcaseError("browser_capture_failed", scenario=scenario, stage="capture")
                        append_release_event(
                            event_type="scenario", operation=f"showcase.{scenario}.frames", outcome="failed",
                            failure_class="scenario_failure", scenario=scenario, stage="capture", failure_code=failure.failure_code,
                        )
                        return _showcase_failure(batch_id, started, chain_results, frame_paths, failure, frame_groups)
                    append_release_event(
                        event_type="scenario", operation=f"showcase.{scenario}", outcome="succeeded",
                        scenario=scenario, stage="complete", completed_step_count=int(result.get("completedStepCount", 0)),
                        model_called=provider_mode == "live", proposal_formed=bool(result.get("proposalFormed", False)),
                        java_eligibility=bool(result.get("javaRechecked", False)), java_commit=bool(result.get("confirmedWrite", False)),
                        status_readback=bool(result.get("statusReadback", False)),
                    )
        except ShowcaseError as exc:
            failure = exc.for_scenario(exc.scenario if exc.scenario != "unknown" else "runtime")
            append_release_event(
                event_type="scenario", operation="showcase.runtime", outcome="failed",
                failure_class="scenario_failure", scenario=failure.scenario, stage=failure.stage,
                failure_code=failure.failure_code,
            )
            return _showcase_failure(batch_id, started, chain_results, frame_paths, failure, frame_groups)
        except (httpx.HTTPError, OSError, ValueError):
            failure = ShowcaseError("unknown_failure", scenario="runtime", stage="http")
            append_release_event(
                event_type="scenario", operation="showcase.runtime", outcome="failed",
                failure_class="scenario_failure", scenario="runtime", stage="http", failure_code=failure.failure_code,
            )
            return _showcase_failure(batch_id, started, chain_results, frame_paths, failure, frame_groups)
        except Exception:
            # Keep unexpected implementation errors inside the same safe
            # public failure contract; never print a provider body, token, or
            # traceback from a showcase report.
            failure = ShowcaseError("unknown_failure", scenario="runtime", stage="unexpected")
            append_release_event(
                event_type="scenario", operation="showcase.runtime", outcome="failed",
                failure_class="scenario_failure", scenario="runtime", stage="unexpected", failure_code=failure.failure_code,
            )
            return _showcase_failure(batch_id, started, chain_results, frame_paths, failure, frame_groups)
    cross_scenario_frames_distinct = _cross_scenario_frames_distinct(frame_groups)
    status = "passed" if (
        all(item.get("status") == "passed" for item in chain_results)
        and len(frame_paths) >= 12
        and all(group.get("valid") is True for group in frame_groups.values())
        and len(frame_groups) == 3
        and cross_scenario_frames_distinct
    ) else "failed"
    gif_paths = _build_offline_gifs(frame_groups, report_dir / "gifs") if status == "passed" else []
    report = {
        "status": status,
        "batchId": batch_id,
        "providerMode": provider_mode,
        "durationMs": round((time.monotonic() - started) * 1000),
        "chains": chain_results,
        "frames": frame_paths,
        "browserFrameCount": len(frame_paths),
        "frameGroups": frame_groups,
        "crossScenarioFramesDistinct": cross_scenario_frames_distinct,
        "gifPaths": gif_paths,
        "fixture": {"kind": "local_demo_synthetic", "containsRawValuesInReport": False},
    }
    report.update(_aggregate_showcase_metrics(chain_results))
    return report


def _showcase_failure(
    batch_id: str,
    started: float,
    chains: list[dict[str, Any]],
    frames: list[str],
    failure: ShowcaseError,
    frame_groups: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ledger_events = read_release_events(
        os.getenv("MALL_RELEASE_LEDGER_PATH", ""),
        batch_id=batch_id,
    ) if os.getenv("MALL_RELEASE_LEDGER_PATH") else []
    provider_usage = summarize_release_events(ledger_events)
    malformed_before_network = any(
        item.get("eventType") == "provider_request"
        and item.get("failureClass") == "ledger_malformed"
        for item in ledger_events
    ) and provider_usage.get("providerHttpAttempts", 0) == 0
    if malformed_before_network:
        failure.failure_code = "release_infrastructure_failure"
        failure.task_metrics["rootFailureClass"] = "release_infrastructure_failure"
        failure.task_metrics["ledgerFailureClass"] = "ledger_malformed"
        failure.task_metrics["providerHttpAttempts"] = 0
    report = {
        "status": "failed",
        "batchId": batch_id,
        "durationMs": round((time.monotonic() - started) * 1000),
        "chains": chains,
        "frames": frames,
        "browserFrameCount": len(frames),
        "frameGroups": frame_groups or {},
        "failure": failure.to_public(),
        "providerUsage": {
            "logicalProviderRequests": provider_usage.get("logicalProviderRequests", 0),
            "providerHttpAttempts": provider_usage.get("providerHttpAttempts", 0),
            "providerSuccesses": provider_usage.get("providerSuccesses", 0),
            "providerFailures": provider_usage.get("providerFailures", 0),
            "totalTokens": provider_usage.get("totalTokens", 0),
            "ledgerReconciled": True,
        },
    }
    report.update(_aggregate_showcase_metrics(chains))
    return report


def _provider_usage(batch_id: str) -> dict[str, Any]:
    ledger_path = os.getenv("MALL_RELEASE_LEDGER_PATH")
    if not ledger_path:
        return {}
    return summarize_release_events(read_release_events(ledger_path, batch_id=batch_id))


def _provider_failure_after_scenario(
    scenario: str,
    result: dict[str, Any],
    provider_usage: dict[str, Any],
) -> ShowcaseError | None:
    provider_failures = int(provider_usage.get("providerFailures", 0))
    if provider_failures == 0:
        return None
    return ShowcaseError(
        "provider_http_failure",
        scenario=scenario,
        stage="provider",
        completed_steps=int(result.get("completedStepCount", 0)),
        model_called=True,
        proposal_formed=bool(result.get("proposalFormed", False)),
        java_eligibility=bool(result.get("javaRechecked", False)),
        java_commit=bool(result.get("confirmedWrite", False)),
        status_readback=bool(result.get("statusReadback", False)),
        task_metrics={
            "rootFailureClass": "provider_failure",
            "providerFailures": provider_failures,
        },
    )


def _cross_scenario_frames_distinct(frame_groups: dict[str, dict[str, Any]]) -> bool:
    """Reject reuse of scenario-specific final task cards.

    Goal and evidence projections may legitimately match after public DTO
    redaction. The final task card must still reflect each scenario's own
    status and therefore cannot be reused across independent chains.
    """

    if len(frame_groups) != 3:
        return False
    status_hashes: list[str] = []
    for group in frame_groups.values():
        stages = group.get("stages")
        hashes = group.get("hashes")
        if not isinstance(stages, list) or not isinstance(hashes, list) or len(stages) != len(hashes):
            return False
        try:
            status_hashes.append(str(hashes[stages.index("status")]))
        except ValueError:
            return False
    if len(status_hashes) != 3:
        return False
    return len(set(status_hashes)) == len(status_hashes)


def _aggregate_showcase_metrics(chains: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep task-level counters distinct from batch-level Provider ledger data."""

    keys = ("modelCalls", "contextModelCalls", "criticCalls", "toolCalls", "clarificationCount")
    totals = {key: 0 for key in keys}
    for item in chains:
        if not isinstance(item, dict):
            continue
        nested = item.get("taskMetrics") if isinstance(item.get("taskMetrics"), dict) else {}
        for key in keys:
            totals[key] += int(item.get(key, nested.get(key, 0)) or 0)
    return totals


def _provider_headers() -> dict[str, str]:
    """Forward only formal release metadata, never provider credentials."""

    values = {
        "X-Mall-Provider-Mode": os.getenv("MALL_RUNTIME_PROVIDER_MODE", "offline"),
        "X-Mall-Release-Id": os.getenv("MALL_RELEASE_ID", ""),
        "X-Mall-Release-Batch-Id": os.getenv("MALL_RELEASE_BATCH_ID", ""),
        "X-Mall-Release-Ledger-Path": os.getenv(
            "MALL_RELEASE_LEDGER_CONTAINER_PATH", "/app/release-ledger/ledger.jsonl"
        ),
        "X-Mall-Runtime-Commit": os.getenv("MALL_RUNTIME_COMMIT", ""),
    }
    return {key: value for key, value in values.items() if value}


def _agent_closed_loop(
    client: httpx.Client,
    api_base: str,
    auth_a: str,
    auth_b: str,
    order_sn: str,
) -> dict[str, Any]:
    """Open-task Agent -> proposal -> confirmation -> Java status readback."""

    session_id = str(uuid.uuid4())
    _create_customer_conversation(client, api_base, auth_a, session_id)
    before = _list_applications(client, api_base, auth_a)
    created = _create_agent_task(
        client,
        api_base,
        auth_a,
        session_id,
        f"订单号：{order_sn}，申请取消退款，完成售后闭环",
    )
    task_ref = created.get("task_ref")
    if not isinstance(task_ref, str):
        raise ShowcaseError("closed_loop_proposal_missing", stage="agent_task_create")
    before_events = _list_agent_events(client, api_base, auth_a, task_ref)
    if created.get("status") == "waiting_for_user":
        if not created.get("open_question") or isinstance(created.get("action"), dict):
            raise ShowcaseError("clarification_not_resumed", stage="agent_task_create", completed_steps=1)
        created = _continue_agent_task(
            client,
            api_base,
            auth_a,
            task_ref,
            "继续形成取消退款待确认草案；我理解最终资格仍需 Java 重校验。",
        )
        if created.get("task_ref") != task_ref:
            raise ShowcaseError("clarification_not_resumed", stage="agent_task_continue", completed_steps=2)
        if created.get("status") == "waiting_for_user":
            raise ShowcaseError("proposal_not_formed_after_clarification", stage="agent_task_continue", completed_steps=2)
    if created.get("status") != "ready_to_commit" or not isinstance(created.get("action"), dict):
        raise ShowcaseError(
            _task_failure_code(created, fallback="task_terminal_state_unexpected"),
            stage="agent_task_create",
            completed_steps=_completed_steps(created),
            model_called=_model_called(created),
            task_metrics=_safe_task_metrics(created, before_events),
        )
    current_action = created["action"]
    amended = _amend_agent_task(client, api_base, auth_a, task_ref, current_action, "cancel_refund")
    if amended.get("status") != "ready_to_commit" or not isinstance(amended.get("action"), dict):
        raise ShowcaseError("closed_loop_proposal_missing", stage="draft_amendment", completed_steps=_completed_steps(created), proposal_formed=True)
    stale = _confirm_agent_task_raw(client, api_base, auth_a, task_ref, "confirm", created)
    if stale.status_code != 409:
        raise ShowcaseError("stale_proposal_was_submitted", stage="stale_revision", completed_steps=_completed_steps(amended), proposal_formed=True)
    committed = _confirm_agent_task(client, api_base, auth_a, task_ref, "confirm", amended)
    action = committed.get("action") or {}
    # A committed proposal is intentionally omitted from the public action
    # card.  The task status plus the Java-backed list read establish the
    # commit without leaking the internal proposal state.
    if committed.get("status") not in {"executing", "completed"}:
        raise ShowcaseError(
            "closed_loop_java_submission_missing",
            stage="java_commit",
            completed_steps=_completed_steps(amended) + 1,
            proposal_formed=True,
            java_eligibility=True,
        )
    after = _list_applications(client, api_base, auth_a)
    if len(after) != len(before) + 1:
        raise ShowcaseError(
            "status_readback_missing",
            stage="status_readback",
            completed_steps=_completed_steps(amended) + 2,
            proposal_formed=True,
            java_eligibility=True,
            java_commit=True,
        )
    # A second confirmation must fail closed because the proposal was already
    # consumed; it must not create a second Java application.
    duplicate = _confirm_agent_task_raw(client, api_base, auth_a, task_ref, "confirm", amended)
    duplicate_after = _list_applications(client, api_base, auth_a)
    if duplicate.status_code not in {404, 409} or len(duplicate_after) != len(after):
        raise ShowcaseError(
            "duplicate_confirmation_not_idempotent",
            stage="idempotency",
            completed_steps=_completed_steps(amended) + 3,
            proposal_formed=True,
            java_eligibility=True,
            java_commit=True,
            status_readback=True,
        )
    foreign = _list_applications(client, api_base, auth_b)
    if foreign:
        raise ShowcaseError(
            "cross_account_scope_failed",
            stage="scope_check",
            completed_steps=_completed_steps(amended) + 4,
            proposal_formed=True,
            java_eligibility=True,
            java_commit=True,
            status_readback=True,
        )
    return {
        "scenario": "main_open_task_closed_loop",
        "status": "passed",
        "completedStepCount": _completed_steps(amended) + 5,
        "taskContinuity": True,
        "draftAmended": True,
        "oldRevisionHttpStatus": 409,
        "javaRechecked": True,
        "confirmedWrite": True,
        "proposalFormed": True,
        "statusReadback": True,
        "duplicateConfirmationWrites": 0,
        "crossAccountLeakage": 0,
        "_captureSessionId": session_id,
        **_safe_task_metrics(amended, _list_agent_events(client, api_base, auth_a, task_ref)),
    }


def _agent_pause_resume(
    client: httpx.Client,
    api_base: str,
    auth: str,
    order_sn: str,
) -> dict[str, Any]:
    """Persist a waiting task, restart FastAPI, and resume the same task."""

    session_id = str(uuid.uuid4())
    _create_customer_conversation(client, api_base, auth, session_id)
    waiting = _create_agent_task(client, api_base, auth, session_id, "查询订单物流")
    task_ref = waiting.get("task_ref")
    if waiting.get("status") != "waiting_for_user" or not waiting.get("open_question") or not isinstance(task_ref, str):
        raise ShowcaseError("agent_task_waiting_missing", stage="waiting_for_input", completed_steps=1)
    events = _list_agent_events(client, api_base, auth, task_ref)
    if not any(item.get("event_type") == "waiting_for_user" for item in events):
        raise ShowcaseError("agent_task_waiting_missing", stage="waiting_trace", completed_steps=1)
    first_hash = _hash(task_ref)
    # A second message without the required reference must remain a safe wait;
    # it does not consume a model call or replace the task.
    detour = _continue_agent_task(client, api_base, auth, task_ref, "先保留这个任务，稍后补订单号")
    if detour.get("task_ref") != task_ref or detour.get("status") != "waiting_for_user":
        raise ShowcaseError("agent_task_resume_failed", stage="safe_detour", completed_steps=2)
    _restart_ai_service()
    resumed = _continue_agent_task(client, api_base, auth, task_ref, f"订单号：{order_sn}")
    facts = resumed.get("artifacts")
    if not isinstance(facts, list) or not facts or resumed.get("task_ref") != task_ref:
        raise ShowcaseError("agent_task_resume_failed", stage="resume_after_restart", completed_steps=3)
    if _hash(str(resumed.get("task_ref"))) != first_hash:
        raise ShowcaseError("pause_resume_task_changed", stage="resume_after_restart", completed_steps=3)
    return {
        "scenario": "clarify_pause_resume",
        "status": "passed",
        "completedStepCount": 4,
        "taskContinuity": True,
        "waitingForInput": True,
        "serviceRestarted": True,
        "sameTaskHash": True,
        "javaFactsAfterResume": True,
        "businessWrites": 0,
        "statusReadback": True,
        "_captureSessionId": session_id,
    }


def _agent_fact_change_replan(
    client: httpx.Client,
    api_base: str,
    admin_base: str,
    auth: str,
    order_id: int,
    order_sn: str,
    password: str,
) -> dict[str, Any]:
    """Invalidate a proposal through a real Java fact transition."""

    session_id = str(uuid.uuid4())
    _create_customer_conversation(client, api_base, auth, session_id)
    before = _list_applications(client, api_base, auth)
    created = _create_agent_task(
        client,
        api_base,
        auth,
        session_id,
        f"订单号：{order_sn}，申请取消退款，完成售后闭环",
    )
    task_ref = created.get("task_ref")
    if created.get("status") != "ready_to_commit" or not isinstance(created.get("action"), dict) or not isinstance(task_ref, str):
        raise ShowcaseError("fact_change_proposal_missing", stage="proposal", completed_steps=1)
    try:
        from verify_build14_eligibility_live import _deliver, _operations_login

        operations_auth = _operations_login(client, api_base, "localDemoOperations", password)
        _deliver(client, admin_base, operations_auth, order_id)
    except Exception as exc:
        del exc
        raise ShowcaseError("java_fact_transition_failed", stage="java_fact_transition", completed_steps=2, proposal_formed=True)
    confirmed = _confirm_agent_task(client, api_base, auth, task_ref, "confirm", created)
    confirmed_action = confirmed.get("action") or {}
    if confirmed_action.get("confirmation_status") not in {"blocked", "unknown", None}:
        raise ShowcaseError(
            "stale_proposal_was_submitted",
            stage="java_recheck",
            completed_steps=3,
            proposal_formed=True,
            java_eligibility=True,
            java_commit=True,
        )
    after = _list_applications(client, api_base, auth)
    if len(after) != len(before):
        raise ShowcaseError(
            "stale_proposal_was_submitted",
            stage="status_readback",
            completed_steps=4,
            proposal_formed=True,
            java_eligibility=True,
            status_readback=True,
        )
    return {
        "scenario": "fact_change_replan",
        "status": "passed",
        "completedStepCount": 5,
        "initialProposal": True,
        "proposalFormed": True,
        "javaFactTransition": True,
        "oldProposalSubmitted": False,
        "recheckOrHandoffObserved": True,
        "businessWritesForStaleProposal": 0,
        "statusReadback": True,
        "_captureSessionId": session_id,
    }


def _create_customer_conversation(
    client: httpx.Client,
    api_base: str,
    auth: str,
    session_id: str,
) -> None:
    try:
        response = client.post(
            f"{api_base}/customer-service/conversations/{session_id}",
            headers={"Authorization": auth},
        )
    except httpx.HTTPError as exc:
        raise ShowcaseError("conversation_create_failed", stage="fixture") from exc
    if response.status_code not in {200, 201, 409}:
        raise ShowcaseError(
            "conversation_create_failed",
            stage="fixture",
            http_status_class=_status_class(response.status_code),
        )


def _create_agent_task(client: httpx.Client, api_base: str, auth: str, session_id: str, goal: str) -> dict[str, Any]:
    try:
        response = client.post(
            f"{api_base}/agent-tasks",
            headers={"Authorization": auth},
            json={"session_id": session_id, "goal": goal, "success_criteria": ["事实已核验"]},
        )
    except httpx.TimeoutException as exc:
        raise ShowcaseError("client_read_timeout", stage="agent_task_create") from exc
    except httpx.HTTPError as exc:
        raise ShowcaseError("gateway_timeout", stage="agent_task_create") from exc
    if response.status_code != 201:
        raise ShowcaseError(
            _response_failure_code(response),
            stage="agent_task_create",
            http_status_class=_status_class(response.status_code),
        )
    payload = _json_object(response)
    _assert_task_public(payload)
    return payload


def _continue_agent_task(client: httpx.Client, api_base: str, auth: str, task_ref: str, message: str) -> dict[str, Any]:
    try:
        response = client.post(
            f"{api_base}/agent-tasks/{task_ref}/messages",
            headers={"Authorization": auth},
            json={"message": message},
        )
    except httpx.TimeoutException as exc:
        raise ShowcaseError("client_read_timeout", stage="agent_task_continue") from exc
    except httpx.HTTPError as exc:
        raise ShowcaseError("gateway_timeout", stage="agent_task_continue") from exc
    if response.status_code != 200:
        raise ShowcaseError(
            _response_failure_code(response),
            stage="agent_task_continue",
            http_status_class=_status_class(response.status_code),
        )
    payload = _json_object(response)
    _assert_task_public(payload)
    return payload


def _amend_agent_task(
    client: httpx.Client,
    api_base: str,
    auth: str,
    task_ref: str,
    action: dict[str, Any],
    application_type: str,
) -> dict[str, Any]:
    """Exercise the public versioned-draft API before final confirmation."""

    try:
        response = client.patch(
            f"{api_base}/agent-tasks/{task_ref}/action",
            headers={"Authorization": auth},
            json={
                "proposal_ref": action.get("proposal_ref"),
                "revision": action.get("revision"),
                "application_type": application_type,
            },
        )
    except httpx.TimeoutException as exc:
        raise ShowcaseError("client_read_timeout", stage="draft_amendment") from exc
    except httpx.HTTPError as exc:
        raise ShowcaseError("gateway_timeout", stage="draft_amendment") from exc
    if response.status_code != 200:
        raise ShowcaseError(_response_failure_code(response), stage="draft_amendment", http_status_class=_status_class(response.status_code))
    payload = _json_object(response)
    _assert_task_public(payload)
    return payload


def _safe_task_metrics(payload: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Project only persisted counters and public artifact/event metadata."""

    metrics = payload.get("execution_metrics")
    if not isinstance(metrics, dict):
        raise ShowcaseError("task_metrics_mismatch", stage="task_metrics")
    required = ("model_calls", "context_model_calls", "critic_calls", "tool_calls")
    if any(not isinstance(metrics.get(key), int) or int(metrics[key]) < 0 for key in required):
        raise ShowcaseError("task_metrics_mismatch", stage="task_metrics")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ShowcaseError("task_metrics_mismatch", stage="task_metrics")
    skill_sequence = [item.get("source_skill") for item in artifacts if isinstance(item, dict) and isinstance(item.get("source_skill"), str)]
    artifact_kinds = [item.get("kind") for item in artifacts if isinstance(item, dict) and isinstance(item.get("kind"), str)]
    observed = sum(item.get("event_type") == "skill_observed" for item in events)
    if observed and metrics["tool_calls"] < observed:
        raise ShowcaseError("task_metrics_mismatch", stage="task_metrics")
    return {
        "modelCalls": metrics["model_calls"],
        "contextModelCalls": metrics["context_model_calls"],
        "criticCalls": metrics["critic_calls"],
        "toolCalls": metrics["tool_calls"],
        "skillSequence": skill_sequence,
        "artifactKinds": artifact_kinds,
        "taskStatusTransitions": [item.get("event_type") for item in events if isinstance(item.get("event_type"), str)],
        "clarificationCount": sum(item.get("event_type") == "waiting_for_user" for item in events),
    }


def _completed_steps(payload: dict[str, Any]) -> int:
    """Count completed safe stages from persisted artifacts/proposal state."""

    artifacts = payload.get("artifacts")
    artifact_count = len(artifacts) if isinstance(artifacts, list) else 0
    return artifact_count + (1 if isinstance(payload.get("action"), dict) else 0)


def _model_called(payload: dict[str, Any]) -> bool:
    metrics = payload.get("execution_metrics")
    return isinstance(metrics, dict) and isinstance(metrics.get("model_calls"), int) and metrics["model_calls"] > 0


def _confirm_agent_task(client: httpx.Client, api_base: str, auth: str, task_ref: str, confirmation: str, task: dict[str, Any]) -> dict[str, Any]:
    response = _confirm_agent_task_raw(client, api_base, auth, task_ref, confirmation, task)
    payload = _json_object(response)
    if response.status_code != 200:
        raise ShowcaseError("closed_loop_java_submission_missing", stage="java_commit", http_status_class=_status_class(response.status_code))
    _assert_task_public(payload)
    return payload


def _confirm_agent_task_raw(client: httpx.Client, api_base: str, auth: str, task_ref: str, confirmation: str, task: dict[str, Any]) -> httpx.Response:
    try:
        action = task.get("action") if isinstance(task.get("action"), dict) else {}
        return client.post(
            f"{api_base}/agent-tasks/{task_ref}/action",
            headers={"Authorization": auth},
            json={
                "confirmation": confirmation,
                "proposal_ref": action.get("proposal_ref"),
                "revision": action.get("revision"),
            },
        )
    except httpx.TimeoutException as exc:
        raise ShowcaseError("client_read_timeout", stage="java_commit") from exc
    except httpx.HTTPError as exc:
        raise ShowcaseError("gateway_timeout", stage="java_commit") from exc


def _list_agent_events(client: httpx.Client, api_base: str, auth: str, task_ref: str) -> list[dict[str, Any]]:
    response = client.get(f"{api_base}/agent-tasks/{task_ref}/events", headers={"Authorization": auth})
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, list):
        raise ShowcaseError("agent_task_waiting_missing", stage="waiting_trace", http_status_class=_status_class(response.status_code))
    return [item for item in payload if isinstance(item, dict)]


def _assert_task_public(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("task_ref"), str) or not isinstance(payload.get("status"), str):
        raise ShowcaseError("public_answer_missing", stage="public_projection")
    _assert_no_forbidden(payload)


def _response_failure_code(response: httpx.Response) -> str:
    """Classify an HTTP failure without reading or persisting its body."""

    header_code = response.headers.get("x-mall-failure-code", "").strip()
    if header_code in SAFE_FAILURE_CODES:
        return header_code
    if response.status_code == 504 or response.status_code >= 500:
        return "gateway_timeout"
    return "scenario_assertion_failure"


def _task_failure_code(payload: dict[str, Any], *, fallback: str) -> str:
    codes = payload.get("limitation_codes")
    if isinstance(codes, list):
        for code in codes:
            if code in {"ledger_malformed", "release_infrastructure_failure"}:
                return "release_infrastructure_failure"
            if code == "runtime_deadline_exceeded":
                return "runtime_deadline_exceeded"
            if code in {"model_timeout", "provider_timeout"}:
                return "provider_timeout"
            if code in {"model_provider_http_failure", "provider_http_failure", "model_provider_unavailable", "model_network"}:
                return "provider_http_failure"
            if code in {"model_invalid_response", "schema_failure", "invalid_executor_decision"}:
                return "schema_failure"
    return fallback


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx" if status_code >= 100 else "none"


def _prepare_fixture(password: str):
    nonce = uuid.uuid4().hex[:12]
    seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount("v301-A", f"v301_a_{nonce}", password, f"197{seed:08d}"),
        DemoAccount("v301-B", f"v301_b_{nonce}", password, f"196{(seed + 1) % 100_000_000:08d}"),
    )
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    with httpx.Client(timeout=60, trust_env=False) as client:
        order_a = _prepare_account_order(client, java_base, accounts[0], int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")), required_stock=2)
        _prepare_account_order(client, java_base, accounts[1], int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")), required_stock=1)
    return accounts[0], accounts[1], order_a


def _prepare_showcase_fixture(password: str):
    """Create independent synthetic orders for mutually exclusive scenarios.

    The closed-loop path intentionally changes an order through the after-sales
    state machine.  A later fact-change/replan assertion must therefore use a
    different, still-paid order instead of trying to deliver the already
    changed order.  All identities and identifiers stay process-local.
    """

    nonce = uuid.uuid4().hex[:12]
    seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount("v301-A", f"v301_a_{nonce}", password, f"197{seed:08d}"),
        DemoAccount("v301-B", f"v301_b_{nonce}", password, f"196{(seed + 1) % 100_000_000:08d}"),
    )
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    with httpx.Client(timeout=60, trust_env=False) as client:
        closed_loop_order = _prepare_account_order(
            client,
            java_base,
            accounts[0],
            int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")),
            required_stock=3,
        )
        fact_change_order = _prepare_account_order(
            client,
            java_base,
            accounts[0],
            int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")),
            required_stock=2,
        )
        _prepare_account_order(
            client,
            java_base,
            accounts[1],
            int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")),
            required_stock=1,
        )
    return accounts[0], accounts[1], closed_loop_order, fact_change_order


def _capture_chain_frames(
    password: str,
    customer_username: str,
    directory: Path,
    scenario: str,
    conversation_id: str,
    expected_markers: tuple[str, ...],
) -> dict[str, Any]:
    """Capture four regions from the exact scenario conversation and task."""

    directory.mkdir(parents=True, exist_ok=True)
    old_username = os.environ.get("MALL_FIELD_BROWSER_CUSTOMER_USER")
    os.environ["MALL_FIELD_BROWSER_CUSTOMER_USER"] = customer_username
    frame_specs = (
        ("goal", ".agent-task-card .agent-task-heading"),
        ("evidence", ".agent-task-card .agent-artifact-list"),
        ("progress", ".agent-task-card .agent-plan-list"),
        ("status", ".agent-task-card"),
    )
    paths: list[str] = []
    hashes: list[str] = []
    try:
        from field_browser_support import BrowserSession

        with BrowserSession(password=password, evidence_dir=directory) as browser:
            browser.open_customer_conversation(
                conversation_id,
                expected_markers=expected_markers,
            )
            for stage, selector in frame_specs:
                browser.assert_ready()
                browser.assert_safe_public_text()
                target = directory / f"{scenario}-{stage}.png"
                browser.screenshot(target, selector=selector)
                if not target.is_file() or target.stat().st_size < 1024:
                    return {"frames": paths, "hashes": hashes, "valid": False, "frameCount": len(paths)}
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                paths.append(_safe_rel(target))
                hashes.append(digest)
    except Exception:
        return {"frames": paths, "hashes": hashes, "valid": False, "frameCount": len(paths)}
    finally:
        if old_username is None:
            os.environ.pop("MALL_FIELD_BROWSER_CUSTOMER_USER", None)
        else:
            os.environ["MALL_FIELD_BROWSER_CUSTOMER_USER"] = old_username
    adjacent_distinct = all(left != right for left, right in zip(hashes, hashes[1:]))
    return {
        "frames": paths,
        "hashes": hashes,
        "stages": [stage for stage, _selector in frame_specs],
        "valid": len(paths) == 4 and adjacent_distinct,
        "frameCount": len(paths),
        "adjacentDistinct": adjacent_distinct,
    }


def _capture_expected_markers(scenario: str) -> tuple[str, ...]:
    return {
        "main_open_task_closed_loop": ("申请取消退款", "已完成"),
        "clarify_pause_resume": ("查询订单物流",),
        "fact_change_replan": ("申请取消退款", "当前无法继续"),
    }.get(scenario, ())


def _build_offline_gifs(frame_groups: dict[str, dict[str, Any]], directory: Path) -> list[str]:
    """Build small GIFs from already captured frames without any provider call."""

    try:
        from PIL import Image
    except ImportError:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    names = {
        "main_open_task_closed_loop": "main-open-task-closed-loop.gif",
        "clarify_pause_resume": "clarify-pause-resume.gif",
        "fact_change_replan": "fact-change-replan-handoff.gif",
    }
    outputs: list[str] = []
    for scenario, group in frame_groups.items():
        if not group.get("valid") or scenario not in names:
            continue
        images: list[Image.Image] = []
        for relative in group.get("frames", []):
            path = ROOT / str(relative)
            try:
                with Image.open(path) as image:
                    images.append(image.convert("RGB"))
            except (OSError, ValueError):
                images = []
                break
        if len(images) != 4:
            continue
        target = directory / names[scenario]
        images[0].save(target, save_all=True, append_images=images[1:], duration=900, loop=0, optimize=True)
        for image in images:
            image.close()
        if target.stat().st_size <= 3 * 1024 * 1024:
            outputs.append(_safe_rel(target))
    return outputs


def _capture_browser_frames(password: str, customer_username: str, directory: Path) -> list[str]:
    """Backward-compatible helper for older local capture scripts."""
    try:
        from field_browser_support import BrowserSession
    except ImportError:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    old_username = os.environ.get("MALL_FIELD_BROWSER_CUSTOMER_USER")
    os.environ["MALL_FIELD_BROWSER_CUSTOMER_USER"] = customer_username
    paths: list[str] = []
    try:
        with BrowserSession(password=password, evidence_dir=directory) as browser:
            browser.open_route("customer")
            browser.assert_ready()
            browser.assert_safe_public_text()
            for name in ("main-open-task-closed-loop", "clarify-pause-resume", "fact-change-replan"):
                target = directory / f"{name}.png"
                browser.screenshot(target)
                paths.append(_safe_rel(target))
    except Exception:
        return paths
    finally:
        if old_username is None:
            os.environ.pop("MALL_FIELD_BROWSER_CUSTOMER_USER", None)
        else:
            os.environ["MALL_FIELD_BROWSER_CUSTOMER_USER"] = old_username
    return paths


def _restart_ai_service() -> None:
    result = subprocess.run(["docker", "compose", "restart", "mall-ai-service"], cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise ShowcaseError("ai_service_restart_failed")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = subprocess.run(["docker", "compose", "ps", "--format", "{{.Service}}|{{.State}}|{{.Health}}"], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        if any(line.strip() == "mall-ai-service|running|healthy" for line in ready.stdout.splitlines()):
            return
        time.sleep(2)
    raise ShowcaseError("ai_service_readiness_after_restart_failed")


def _login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    response = client.post(f"{api_base}/auth/login", json={"username": username, "password": password})
    payload = _json_object(response)
    if response.status_code != 200 or not isinstance(payload.get("authorization"), str) or not payload["authorization"].startswith("Bearer "):
        raise ShowcaseError("login_failed")
    return payload["authorization"]


def _list_applications(client: httpx.Client, api_base: str, auth: str) -> list[dict[str, Any]]:
    response = client.get(f"{api_base}/customer-service/after-sales-applications", headers={"Authorization": auth})
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, list):
        raise ShowcaseError("after_sales_list_failed")
    return [item for item in payload if isinstance(item, dict)]


def _assert_no_forbidden(value: object) -> None:
    if isinstance(value, dict):
        if FORBIDDEN_PUBLIC_FIELDS.intersection(value):
            raise ShowcaseError("public_projection_leak")
        for child in value.values():
            _assert_no_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden(child)


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ShowcaseError("non_json_response") from exc
    if not isinstance(payload, dict):
        raise ShowcaseError("object_response_expected")
    return payload


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _safe_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return "external-path"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=ROOT / "tmp" / "real-local-showcase.json")
    parser.add_argument("--provider-mode", choices=("deterministic", "replay", "live"), default=None)
    parser.add_argument("--batch-id", default=None)
    args = parser.parse_args()
    report_path = args.report
    result = run_real_local_showcase(
        report_dir=report_path.parent,
        batch_id=args.batch_id or os.getenv("MALL_RELEASE_BATCH_ID", "manual"),
        provider_mode=args.provider_mode,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result.get("status"), "chains": [item.get("status") for item in result.get("chains", [])], "frames": len(result.get("frames", []))}, ensure_ascii=False))
    raise SystemExit(0 if result.get("status") == "passed" else 1)
