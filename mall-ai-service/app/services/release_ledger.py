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
_SAFE_EVENT_TYPES = {
    "provider_request",
    "provider_reservation",
    "provider_reservation_settlement",
    "budget_denied",
    "scenario",
    "test",
}
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
    "budget_exhausted",
    "ledger_malformed",
}

DEFAULT_MAX_PROVIDER_HTTP_ATTEMPTS = 600
DEFAULT_MAX_TOTAL_TOKENS = 1_600_000
DEFAULT_RESERVE_TOKENS = 12_000


class ReleaseLedgerBudgetError(RuntimeError):
    """A provider attempt was denied before opening a network socket."""

    category = "budget_exhausted"


class ReleaseLedgerIntegrityError(RuntimeError):
    """The active budget ledger cannot be safely reconciled."""

    category = "ledger_malformed"


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


def _budget_limits() -> tuple[int, int, int] | None:
    """Return explicit limits when release budget mode is enabled.

    The defaults are used only when a release ledger is explicitly bound. A
    normal customer request therefore remains unaffected, while a release
    process cannot accidentally run without a bounded budget.
    """

    keys = (
        "MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS",
        "MALL_RELEASE_MAX_TOTAL_TOKENS",
        "MALL_RELEASE_RESERVE_TOKENS",
    )
    values = [os.getenv(key) for key in keys]
    if not any(value is not None for value in values):
        return None
    try:
        parsed = tuple(int(value) if value is not None else default for value, default in zip(values, (DEFAULT_MAX_PROVIDER_HTTP_ATTEMPTS, DEFAULT_MAX_TOTAL_TOKENS, DEFAULT_RESERVE_TOKENS)))
    except (TypeError, ValueError):
        raise ReleaseLedgerIntegrityError("release budget configuration is malformed")
    if any(value <= 0 for value in parsed):
        raise ReleaseLedgerIntegrityError("release budget configuration must be positive")
    return parsed  # type: ignore[return-value]


@contextmanager
def _ledger_file_lock(path: Path) -> Iterator[None]:
    """Lock a sidecar file across host processes and container workers."""

    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _strict_events(path: Path, batch_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise ReleaseLedgerIntegrityError("active release ledger is missing")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseLedgerIntegrityError("active release ledger is unreadable") from exc
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ReleaseLedgerIntegrityError("active release ledger contains malformed JSON") from exc
        if not isinstance(value, dict):
            raise ReleaseLedgerIntegrityError("active release ledger contains a non-object event")
        if value.get("batchId") == batch_id:
            events.append(value)
    return events


def _append_event_locked(path: Path, event: dict[str, Any]) -> None:
    payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        handle.write(payload)
        handle.flush()


def reserve_provider_attempt(*, operation: str = "llm") -> str | None:
    """Atomically reserve one physical provider HTTP attempt.

    Returns ``None`` when release budgeting is not enabled. In enabled mode,
    missing or malformed ledger state fails closed before network I/O.
    """

    limits = _budget_limits()
    if limits is None:
        return None
    path = _path()
    batch_id = current_batch_id()
    if path is None or not batch_id:
        raise ReleaseLedgerIntegrityError("release budget requires ledger path and batch id")
    max_attempts, max_tokens, reserve_tokens = limits
    with _WRITE_LOCK, _ledger_file_lock(path):
        events = _strict_events(path, str(batch_id))
        reservations = [item for item in events if item.get("eventType") == "provider_reservation"]
        used_tokens = sum(_safe_int(item.get("totalTokens")) for item in events if item.get("eventType") == "provider_request")
        unresolved = {
            str(item.get("reservationId"))
            for item in reservations
            if item.get("reservationId")
        }
        settled = {
            str(item.get("reservationId"))
            for item in events
            if item.get("eventType") == "provider_reservation_settlement" and item.get("reservationId")
        }
        unresolved_count = len(unresolved - settled)
        if len(reservations) + 1 > max_attempts or used_tokens + unresolved_count * reserve_tokens + reserve_tokens > max_tokens:
            _append_event_locked(path, {
                "eventId": uuid.uuid4().hex,
                "eventType": "budget_denied",
                "batchId": _safe_text(batch_id, fallback="unknown", limit=96),
                "operation": _safe_text(operation, fallback="llm"),
                "startedAt": _now_iso(),
                "endedAt": _now_iso(),
                "outcome": "blocked",
                "failureClass": "budget_exhausted",
            })
            raise ReleaseLedgerBudgetError("provider budget exhausted")
        reservation_id = uuid.uuid4().hex
        event = {
            "eventId": uuid.uuid4().hex,
            "eventType": "provider_reservation",
            "batchId": _safe_text(batch_id, fallback="unknown", limit=96),
            "reservationId": reservation_id,
            "operation": _safe_text(operation, fallback="llm"),
            "reserveTokens": reserve_tokens,
            "startedAt": _now_iso(),
            "endedAt": _now_iso(),
            "outcome": "succeeded",
            "runtimeCommit": _safe_text(os.getenv("MALL_RUNTIME_COMMIT"), fallback="unknown", limit=64),
        }
        _append_event_locked(path, event)
        return reservation_id


def settle_provider_attempt(reservation_id: str | None, *, outcome: str = "succeeded") -> None:
    if not reservation_id:
        return
    path = _path()
    batch_id = current_batch_id()
    if path is None or not batch_id:
        return
    with _WRITE_LOCK, _ledger_file_lock(path):
        _strict_events(path, str(batch_id))
        event = {
            "eventId": uuid.uuid4().hex,
            "eventType": "provider_reservation_settlement",
            "batchId": _safe_text(batch_id, fallback="unknown", limit=96),
            "reservationId": _safe_text(reservation_id, fallback="unknown", limit=64),
            "operation": "llm",
            "startedAt": _now_iso(),
            "endedAt": _now_iso(),
            "outcome": outcome if outcome in _SAFE_OUTCOMES else "failed",
        }
        _append_event_locked(path, event)


def record_budget_denied(*, operation: str = "llm") -> None:
    path = _path()
    batch_id = current_batch_id()
    if path is None or not batch_id:
        return
    with _WRITE_LOCK, _ledger_file_lock(path):
        _strict_events(path, str(batch_id))
        _append_event_locked(path, {
            "eventId": uuid.uuid4().hex,
            "eventType": "budget_denied",
            "batchId": _safe_text(batch_id, fallback="unknown", limit=96),
            "operation": _safe_text(operation, fallback="llm"),
            "startedAt": _now_iso(),
            "endedAt": _now_iso(),
            "outcome": "blocked",
            "failureClass": "budget_exhausted",
        })


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
        # The sidecar lock serializes host runner and container workers. A
        # single append write prevents partial JSONL records.
        with _WRITE_LOCK, _ledger_file_lock(path):
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
    reservations = [item for item in events if item.get("eventType") == "provider_reservation"]
    settlements = [item for item in events if item.get("eventType") == "provider_reservation_settlement"]
    settled_ids = {str(item.get("reservationId")) for item in settlements if item.get("reservationId")}
    unresolved_reservations = [
        item for item in reservations if str(item.get("reservationId")) not in settled_ids
    ]
    denied = [item for item in events if item.get("eventType") == "budget_denied"]
    provider_failures = [item for item in provider if item.get("outcome") == "failed"]
    scenario_failures = [
        item for item in events if item.get("eventType") == "scenario" and item.get("outcome") == "failed"
    ]
    test_failures = [
        item for item in events if item.get("eventType") == "test" and item.get("outcome") == "failed"
    ]
    return {
        "logicalProviderRequests": len(provider),
        "providerHttpAttempts": len(reservations),
        "providerRequests": len(provider),
        "providerSuccesses": sum(1 for item in provider if item.get("outcome") == "succeeded"),
        "providerFailures": len(provider_failures),
        "successfulRequests": sum(1 for item in provider if item.get("outcome") == "succeeded"),
        "failedRequests": len(provider_failures),
        "deniedBeforeNetwork": len(denied),
        "unresolvedReservations": len(unresolved_reservations),
        "scenarioFailures": len(scenario_failures),
        "testFailures": len(test_failures),
        "promptTokens": sum(_safe_int(item.get("promptTokens")) for item in provider),
        "completionTokens": sum(_safe_int(item.get("completionTokens")) for item in provider),
        "totalTokens": sum(_safe_int(item.get("totalTokens")) for item in provider),
        "networkRetries": sum(_safe_int(item.get("networkRetry")) for item in provider),
        "protocolCorrections": sum(1 for item in provider if item.get("protocolCorrection") is True),
        "events": len(events),
    }
