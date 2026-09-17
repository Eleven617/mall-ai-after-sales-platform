"""Privacy-safe, cross-process release ledger.

The normal customer path does not write a ledger.  A release verification run
opts in with ``MALL_RELEASE_LEDGER_PATH``.  The FastAPI container and the host
runner can then append the same metadata-only JSONL file.  No prompt, model
text, reasoning, business identifier, credential, or tool argument is ever
accepted by this module.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


_BATCH_ID = ContextVar("mall_release_batch_id", default=None)
_LEDGER_PATH = ContextVar("mall_release_ledger_path", default=None)
_SOURCE = ContextVar("mall_release_ledger_source", default="runtime")
_WRITE_LOCK = threading.Lock()
_SAFE_EVENT_TYPES = {"provider_request", "scenario", "test"}
_SAFE_OUTCOMES = {"succeeded", "failed", "blocked"}
_SAFE_FAILURE_CLASSES = {
    "missing_configuration",
    "network",
    "timeout",
    "rate_limited",
    "provider_unavailable",
    "provider_http",
    "invalid_response",
    "schema_validate",
    "scenario_failure",
    "test_failure",
    "unknown",
    "provider_guard",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _safe_text(value: object, *, fallback: str = "unknown", limit: int = 80) -> str:
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    if not value or len(value) > limit:
        return fallback
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
    if any(char not in allowed for char in value):
        return fallback
    return value


def _safe_bool(value: object) -> bool:
    return value is True


def _safe_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(0, value)


def _configured_path() -> Path | None:
    value = os.getenv("MALL_RELEASE_LEDGER_PATH")
    if not value:
        return None
    return Path(value).expanduser()


def current_batch_id() -> str | None:
    return _BATCH_ID.get() or os.getenv("MALL_RELEASE_BATCH_ID") or None


@contextmanager
def release_ledger_context(
    *,
    batch_id: str | None = None,
    path: str | Path | None = None,
    source: str = "runtime",
) -> Iterator[None]:
    """Bind a release batch to the current process/request only."""

    batch_token = _BATCH_ID.set(batch_id or current_batch_id())
    path_token = _LEDGER_PATH.set(Path(path) if path is not None else _configured_path())
    source_token = _SOURCE.set(_safe_text(source, fallback="runtime"))
    try:
        yield
    finally:
        _SOURCE.reset(source_token)
        _LEDGER_PATH.reset(path_token)
        _BATCH_ID.reset(batch_token)


def _path() -> Path | None:
    return _LEDGER_PATH.get() or _configured_path()


def append_release_event(
    *,
    event_type: str,
    operation: str,
    outcome: str,
    failure_class: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    attempts: int = 1,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    protocol_correction: bool = False,
    network_retry: int = 0,
    provider_request_id_hash: str | None = None,
    scenario: str | None = None,
    stage: str | None = None,
    failure_code: str | None = None,
    completed_step_count: int = 0,
    model_called: bool = False,
    proposal_formed: bool = False,
    java_eligibility: bool = False,
    java_commit: bool = False,
    status_readback: bool = False,
) -> bool:
    """Append a bounded metadata event; return False when ledger is disabled."""

    batch_id = current_batch_id()
    path = _path()
    if not batch_id or path is None:
        return False
    safe_type = event_type if event_type in _SAFE_EVENT_TYPES else "test"
    safe_outcome = outcome if outcome in _SAFE_OUTCOMES else "failed"
    safe_failure = (
        failure_class if failure_class in _SAFE_FAILURE_CLASSES else "unknown"
        if safe_outcome != "succeeded"
        else None
    )
    event: dict[str, Any] = {
        "eventId": uuid.uuid4().hex,
        "eventType": safe_type,
        "batchId": _safe_text(batch_id, fallback="unknown", limit=96),
        "operation": _safe_text(operation, fallback="unknown"),
        "startedAt": started_at or _now_iso(),
        "endedAt": ended_at or _now_iso(),
        "outcome": safe_outcome,
        "failureClass": safe_failure,
        "attempts": max(1, _safe_int(attempts, default=1)),
        "promptTokens": _safe_int(prompt_tokens),
        "completionTokens": _safe_int(completion_tokens),
        "totalTokens": _safe_int(total_tokens),
        "latencyMs": _safe_int(latency_ms),
        "protocolCorrection": _safe_bool(protocol_correction),
        "networkRetry": _safe_int(network_retry),
        "providerRequestIdHash": _safe_text(provider_request_id_hash, fallback="", limit=128) if provider_request_id_hash else None,
        "runtimeCommit": _safe_text(os.getenv("MALL_RUNTIME_COMMIT"), fallback="unknown", limit=64),
        "promptVersion": _safe_text(os.getenv("MALL_PROMPT_VERSION"), fallback="unknown"),
        "schemaVersion": _safe_text(os.getenv("MALL_SCHEMA_VERSION"), fallback="unknown"),
        "source": _SOURCE.get(),
    }
    if safe_type in {"scenario", "test"}:
        event.update(
            {
                "scenario": _safe_text(scenario, fallback="unknown"),
                "stage": _safe_text(stage, fallback="unknown"),
                "failureCode": _safe_text(failure_code, fallback="unknown"),
                "completedStepCount": _safe_int(completed_step_count),
                "modelCalled": _safe_bool(model_called),
                "proposalFormed": _safe_bool(proposal_formed),
                "javaEligibility": _safe_bool(java_eligibility),
                "javaCommit": _safe_bool(java_commit),
                "statusReadback": _safe_bool(status_readback),
            }
        )
    payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # One append write per event prevents partial JSONL records.  The
        # process-local lock handles threads; O_APPEND serializes writers from
        # the FastAPI worker and the host evaluator on the same file.
        with _WRITE_LOCK:
            with path.open("ab") as handle:
                handle.write(payload)
        return True
    except OSError:
        # Observability must never block the customer or verification path.
        return False


def read_release_events(path: str | Path, *, batch_id: str | None = None) -> list[dict[str, Any]]:
    """Read only valid JSON objects for a batch; malformed lines are ignored."""

    result: list[dict[str, Any]] = []
    target = str(batch_id) if batch_id else None
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and (target is None or value.get("batchId") == target):
            result.append(value)
    return result


def summarize_release_events(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    provider = [item for item in events if item.get("eventType") == "provider_request"]
    provider_failures = [item for item in provider if item.get("outcome") == "failed"]
    scenario_failures = [
        item for item in events if item.get("eventType") == "scenario" and item.get("outcome") == "failed"
    ]
    test_failures = [
        item for item in events if item.get("eventType") == "test" and item.get("outcome") == "failed"
    ]
    return {
        "providerRequests": len(provider),
        "providerSuccesses": sum(1 for item in provider if item.get("outcome") == "succeeded"),
        "providerFailures": len(provider_failures),
        "scenarioFailures": len(scenario_failures),
        "testFailures": len(test_failures),
        "promptTokens": sum(_safe_int(item.get("promptTokens")) for item in provider),
        "completionTokens": sum(_safe_int(item.get("completionTokens")) for item in provider),
        "totalTokens": sum(_safe_int(item.get("totalTokens")) for item in provider),
        "networkRetries": sum(_safe_int(item.get("networkRetry")) for item in provider),
        "protocolCorrections": sum(1 for item in provider if item.get("protocolCorrection") is True),
        "events": len(events),
    }
