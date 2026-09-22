"""In-memory, privacy-safe LLM measurements for explicit quality checkpoints.

Customer requests use the default no-op sink. A developer or CI process opts in
by entering ``capture_llm_metrics`` around a finite evaluation run. The events
contain operational numbers only, never prompts, model text, tool arguments,
customer identifiers, or credentials.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Protocol

from app.services.release_ledger import append_release_event


_ALLOWED_OPERATIONS = {"text", "tools", "json"}
_ALLOWED_RUNTIME_OPERATIONS = {
    "commerce_executor",
    "context_curator",
    "resolution_critic",
}
_ALLOWED_OUTCOMES = {"succeeded", "failed"}
_ALLOWED_FAILURE_CLASSES = {
    "missing_configuration",
    "network",
    "timeout",
    "rate_limited",
    "provider_unavailable",
    "provider_http",
    "invalid_response",
    "unknown",
    "provider_guard",
    "budget_exhausted",
    "ledger_malformed",
}
_ALLOWED_LEDGER_EVENT_TYPES = {"provider_request", "budget_denied", "test"}


@dataclass(frozen=True)
class LLMCallPolicy:
    """A temporary evaluation-only cap; normal runtime keeps provider defaults."""

    timeout_seconds: float | None = None
    max_attempts: int | None = None


@dataclass(frozen=True)
class LLMCallMetric:
    operation: str
    outcome: str
    elapsed_ms: int
    attempts: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    failure_class: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    provider_request_id_hash: str | None = None
    protocol_correction: bool = False


@dataclass(frozen=True)
class TokenPricing:
    """Optional caller-supplied current provider prices per one million tokens."""

    input_per_million: float
    output_per_million: float
    currency: str = "CNY"


class LLMMetricSink(Protocol):
    def emit(self, metric: LLMCallMetric) -> None: ...


class _NoOpLLMMetricSink:
    def emit(self, metric: LLMCallMetric) -> None:
        del metric


class InMemoryLLMMetricSink:
    """Checkpoint-local collector used by tests and explicit developer runs."""

    def __init__(self) -> None:
        self.events: list[LLMCallMetric] = []

    def emit(self, metric: LLMCallMetric) -> None:
        self.events.append(metric)


_sink_var: ContextVar[LLMMetricSink] = ContextVar(
    "mall_ai_llm_metric_sink",
    default=_NoOpLLMMetricSink(),
)
_policy_var: ContextVar[LLMCallPolicy] = ContextVar(
    "mall_ai_llm_call_policy",
    default=LLMCallPolicy(),
)
_operation_var: ContextVar[str | None] = ContextVar(
    "mall_ai_llm_operation",
    default=None,
)
_protocol_correction_var: ContextVar[bool] = ContextVar(
    "mall_ai_llm_protocol_correction",
    default=False,
)


@contextmanager
def llm_operation_context(operation: str) -> Iterator[None]:
    """Attach a reviewed model role to metrics without retaining payloads."""

    safe_operation = operation if operation in _ALLOWED_RUNTIME_OPERATIONS else None
    token = _operation_var.set(safe_operation)
    try:
        yield
    finally:
        _operation_var.reset(token)


def current_llm_operation(default: str) -> str:
    operation = _operation_var.get()
    return operation if operation in _ALLOWED_RUNTIME_OPERATIONS else default


@contextmanager
def protocol_correction_context() -> Iterator[None]:
    """Mark exactly one bounded structured-output repair request."""
    token = _protocol_correction_var.set(True)
    try:
        yield
    finally:
        _protocol_correction_var.reset(token)


def current_protocol_correction() -> bool:
    return _protocol_correction_var.get()


@contextmanager
def capture_llm_metrics(
    *,
    timeout_seconds: float | None = None,
    max_attempts: int | None = None,
) -> Iterator[InMemoryLLMMetricSink]:
    """Collect metrics for one explicit run without enabling runtime retention."""
    _validate_policy(timeout_seconds, max_attempts)
    sink = InMemoryLLMMetricSink()
    sink_token = _sink_var.set(sink)
    policy_token = _policy_var.set(
        LLMCallPolicy(
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )
    )
    try:
        yield sink
    finally:
        _policy_var.reset(policy_token)
        _sink_var.reset(sink_token)


def current_llm_call_policy() -> LLMCallPolicy:
    return _policy_var.get()


def record_llm_metric(
    *,
    operation: str,
    outcome: str,
    elapsed_ms: int,
    attempts: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    failure_class: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    provider_request_id_hash: str | None = None,
    protocol_correction: bool = False,
    ledger_event_type: str = "provider_request",
    write_ledger: bool = True,
) -> None:
    """Emit a validated number-only event to the checkpoint-local sink."""
    metric = LLMCallMetric(
        operation=(
            operation
            if operation in _ALLOWED_OPERATIONS | _ALLOWED_RUNTIME_OPERATIONS
            else "text"
        ),
        outcome=outcome if outcome in _ALLOWED_OUTCOMES else "failed",
        elapsed_ms=_non_negative_int(elapsed_ms),
        attempts=max(1, _non_negative_int(attempts)),
        prompt_tokens=_optional_non_negative_int(prompt_tokens),
        completion_tokens=_optional_non_negative_int(completion_tokens),
        total_tokens=_optional_non_negative_int(total_tokens),
        failure_class=(
            failure_class
            if failure_class in _ALLOWED_FAILURE_CLASSES
            else "unknown"
            if outcome != "succeeded"
            else None
        ),
        started_at=started_at or _now_iso(),
        ended_at=ended_at or _now_iso(),
        provider_request_id_hash=provider_request_id_hash,
        protocol_correction=bool(protocol_correction),
    )
    _sink_var.get().emit(metric)
    if not write_ledger:
        return
    append_release_event(
        event_type=(
            ledger_event_type
            if ledger_event_type in _ALLOWED_LEDGER_EVENT_TYPES
            else "provider_request"
        ),
        operation=metric.operation,
        outcome=metric.outcome,
        failure_class=metric.failure_class,
        started_at=metric.started_at,
        ended_at=metric.ended_at,
        attempts=metric.attempts,
        prompt_tokens=metric.prompt_tokens or 0,
        completion_tokens=metric.completion_tokens or 0,
        total_tokens=metric.total_tokens or 0,
        latency_ms=metric.elapsed_ms,
        protocol_correction=metric.protocol_correction,
        network_retry=max(0, metric.attempts - 1),
        provider_request_id_hash=metric.provider_request_id_hash,
    )


def summarize_llm_metrics(
    metrics: list[LLMCallMetric],
    pricing: TokenPricing | None = None,
) -> dict[str, object]:
    """Return aggregate metrics without retaining individual prompts or output."""
    succeeded = [metric for metric in metrics if metric.outcome == "succeeded"]
    failed = [metric for metric in metrics if metric.outcome == "failed"]
    elapsed = sorted(metric.elapsed_ms for metric in metrics)
    prompt_tokens = sum(metric.prompt_tokens or 0 for metric in metrics)
    completion_tokens = sum(metric.completion_tokens or 0 for metric in metrics)
    total_tokens = sum(metric.total_tokens or 0 for metric in metrics)
    usage_available_calls = sum(
        1
        for metric in metrics
        if metric.prompt_tokens is not None
        and metric.completion_tokens is not None
        and metric.total_tokens is not None
    )
    failure_classes = sorted(
        {
            metric.failure_class
            for metric in failed
            if metric.failure_class is not None
        }
    )

    result: dict[str, object] = {
        "total_calls": len(metrics),
        "total_attempts": sum(metric.attempts for metric in metrics),
        "network_retries": sum(max(0, metric.attempts - 1) for metric in metrics),
        "succeeded_calls": len(succeeded),
        "failed_calls": len(failed),
        "usage_available_calls": usage_available_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "average_latency_ms": round(sum(elapsed) / len(elapsed), 2) if elapsed else 0.0,
        "p95_latency_ms": _percentile(elapsed, 0.95),
        "max_latency_ms": elapsed[-1] if elapsed else 0,
        "failure_classes": failure_classes,
        "pricing_configured": pricing is not None,
        "estimated_cost": None,
        "currency": pricing.currency if pricing else None,
    }
    if pricing and usage_available_calls == len(metrics):
        result["estimated_cost"] = round(
            (prompt_tokens * pricing.input_per_million / 1_000_000)
            + (completion_tokens * pricing.output_per_million / 1_000_000),
            8,
        )
    return result


def _validate_policy(timeout_seconds: float | None, max_attempts: int | None) -> None:
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when set")
    if max_attempts is not None and max_attempts < 1:
        raise ValueError("max_attempts must be at least one when set")


def _optional_non_negative_int(value: int | None) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value)


def _non_negative_int(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return 0
    return max(0, value)


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    index = max(0, ceil(len(values) * fraction) - 1)
    return values[index]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
