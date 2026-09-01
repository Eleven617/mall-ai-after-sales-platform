"""Privacy-safe, versioned workflow traces used by Build 22 evaluation.

Traces are observability metadata, not a second conversation history. The
allow-list below is deliberately smaller than the application state: raw
customer text, identifiers, credentials, RAG passages, tool payloads and model
messages have no representable field in this schema.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

from app.services.request_context import current_correlation_ref


TRACE_SCHEMA_VERSION = "trace-v2"
_LOGGER = logging.getLogger("mall_ai.workflow")

# A caller supplies legacy/internal flow labels, but emitted traces use the
# product-level names. Unknown values are collapsed instead of logged.
_SAFE_FLOW_ALIASES = {
    "agent": "legacy_read_only_agent",
    "analysis_agent": "unified_after_sales_investigation",
    "unified_after_sales": "unified_after_sales",
    "after_sales_workflow": "unified_after_sales",
    "diagnosis_checkpoint": "unified_after_sales_checkpoint",
    "intent_routing": "intent_routing",
    "case_handoff": "case_handoff",
    "conversation_history": "conversation_history",
    "operations_analysis": "operations_analysis",
    "quality_evaluation": "quality_evaluation",
}
_SAFE_EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_CONTRACT_VIOLATION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_SAFE_RESULT_KINDS = {
    "success",
    "failure",
    "blocked",
    "unavailable",
    "timeout",
    "pending",
    "completed",
    "rejected",
    "skipped",
}

# Trace metadata uses an allow-list rather than attempting to redact every
# possible sensitive field. New attributes require an intentional review here.
_SAFE_DETAIL_KEYS = {
    "step",
    "tool_name",
    "has_order",
    "has_product",
    "has_reason",
    "product_option_count",
    "policy_source_count",
    "node",
    "diagnosis_category",
    "evidence_status",
    "handoff",
    "intent",
    "route",
    "prompt_version",
    "duration_ms",
    "result_kind",
    "contract_violation",
    "tool_call_count",
    "role",
    "skill_id",
    "skill_version",
    "profile_id",
    "profile_version",
    "fact_ref",
    "policy_ref",
    "submission_ref",
    "outbox_ref",
    "error_category",
    "dependency",
}
_SAFE_TOOL_NAMES = {
    "order_service",
    "logistics_service",
    "inventory_service",
    "rag_search",
    "analysis_agent",
}
_SAFE_GRAPH_NODES = {
    "agent_decide",
    "execute_tools",
    "await_identifier",
    "await_human_input",
    "resume_read_only_tool",
    "read_only_investigation",
    "resume_pending",
    "dispatch",
    "finalize",
    "handoff",
    "finish",
}
_SAFE_DIAGNOSIS_CATEGORIES = {
    "delivery_in_transit",
    "delivery_exception",
    "order_state_review",
    "facts_incomplete",
    "policy_consultation",
    "policy_insufficient",
    "tool_failure",
    "needs_order_identifier",
}
_SAFE_EVIDENCE_STATUSES = {"complete", "partial", "insufficient", "unavailable"}
_SAFE_INTENTS = {
    "query_order_status",
    "query_logistics",
    "query_inventory",
    "after_sales_policy",
    "after_sales_eligibility",
    "apply_after_sales",
    "list_after_sales",
    "status_after_sales",
    "cancel_after_sales",
    "modify_after_sales",
    "follow_up_after_sales",
    "product_question",
    "business_analysis",
    "general_chat",
    "unknown",
}
_SAFE_ROUTES = {"chat", "rag", "tool_calling", "agent", "ask_missing_info", "after_sales_flow"}
_SAFE_PROMPT_VERSIONS = {"intent_semantic_v1", "intent_semantic_v2"}
_SAFE_ROLES = {"unified_after_sales", "operations_analysis", "quality_evaluation"}
_SAFE_SKILL_IDS = {
    "policy_question_answering",
    "order_exception_diagnosis",
    "after_sales_proposal",
    "case_handoff",
    "handoff_operations_analysis",
    "quality_contract_evaluation",
}
_SAFE_DEPENDENCIES = {"llm", "java", "rag", "rabbitmq", "redis"}
_SAFE_VERSION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SAFE_REFERENCE_PATTERN = re.compile(r"^[a-f0-9]{16,64}$")
_SAFE_ERROR_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class TraceEvent:
    schema_version: str
    flow: str
    event: str
    session_hash: str
    correlation_ref: str
    occurred_at: float
    duration_ms: int | None = None
    result_kind: str | None = None
    contract_violation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class LoggingTraceSink:
    def emit(self, event: TraceEvent) -> None:
        _LOGGER.info(
            "ai_workflow_trace=%s",
            json.dumps(
                {
                    "schema_version": event.schema_version,
                    "flow": event.flow,
                    "event": event.event,
                    "session_hash": event.session_hash,
                    "correlation_ref": event.correlation_ref,
                    "occurred_at": event.occurred_at,
                    "duration_ms": event.duration_ms,
                    "result_kind": event.result_kind,
                    "contract_violation": event.contract_violation,
                    "details": event.details,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )


class InMemoryTraceSink:
    """Context-local deterministic sink for tests and isolated evaluations."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


class CompositeTraceSink:
    def __init__(self, *sinks: TraceSink) -> None:
        self._sinks = sinks

    def emit(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)


_sink: TraceSink = LoggingTraceSink()
_trace_recording_enabled: ContextVar[bool] = ContextVar(
    "mall_ai_trace_recording_enabled", default=True
)
_context_trace_sink: ContextVar[TraceSink | None] = ContextVar(
    "mall_ai_context_trace_sink", default=None
)


def record_trace(
    flow: str,
    event: str,
    session_id: str,
    **details: Any,
) -> None:
    """Emit metadata only, without allowing observability to break work."""

    if not _trace_recording_enabled.get():
        return
    safe_details = _sanitize_details(details)
    trace_event = TraceEvent(
        schema_version=TRACE_SCHEMA_VERSION,
        flow=_sanitize_flow(flow),
        event=_sanitize_event(event),
        session_hash=_hash_session_id(session_id),
        correlation_ref=current_correlation_ref(),
        occurred_at=time.time(),
        duration_ms=safe_details.pop("duration_ms", None),
        result_kind=safe_details.pop("result_kind", None),
        contract_violation=safe_details.pop("contract_violation", None),
        details=safe_details,
    )
    sink = _context_trace_sink.get() or _sink
    try:
        sink.emit(trace_event)
    except Exception:
        # Do not include the original exception: a third-party sink may have
        # put unsafe payload text inside it.
        try:
            _LOGGER.warning("ai_workflow_trace_unavailable")
        except Exception:
            pass


def set_trace_sink_for_tests(sink: TraceSink | None) -> None:
    global _sink
    _sink = sink or LoggingTraceSink()


@contextmanager
def capture_safe_traces() -> Iterator[InMemoryTraceSink]:
    """Capture a synthetic run without writing a runtime trace.

    The ContextVar scope prevents an offline quality evaluation from redirecting
    another request's sink. Captured values still pass the ordinary allow-list.
    """

    sink = InMemoryTraceSink()
    token = _context_trace_sink.set(sink)
    try:
        yield sink
    finally:
        _context_trace_sink.reset(token)


@contextmanager
def suppress_trace_recording() -> Iterator[None]:
    """Disable trace emission only inside an isolated evaluation execution."""

    token = _trace_recording_enabled.set(False)
    try:
        yield
    finally:
        _trace_recording_enabled.reset(token)


def _hash_session_id(session_id: str) -> str:
    value = session_id if isinstance(session_id, str) else ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _sanitize_flow(value: Any) -> str:
    return _SAFE_FLOW_ALIASES.get(value, "unrecognized_flow")


def _sanitize_event(value: Any) -> str:
    if isinstance(value, str) and _SAFE_EVENT_PATTERN.fullmatch(value):
        return value
    return "unrecognized_event"


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Keep only small, typed metrics that cannot carry customer content."""

    safe_details: dict[str, Any] = {}
    for key, value in details.items():
        if key not in _SAFE_DETAIL_KEYS:
            continue
        if key == "tool_name":
            safe_details[key] = value if value in _SAFE_TOOL_NAMES else "unrecognized_tool"
        elif key in {"has_order", "has_product", "has_reason", "handoff"}:
            if isinstance(value, bool):
                safe_details[key] = value
        elif key in {"step", "product_option_count", "policy_source_count", "tool_call_count"}:
            if isinstance(value, int) and 0 <= value <= 1000:
                safe_details[key] = value
        elif key == "duration_ms":
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3_600_000:
                safe_details[key] = value
        elif key == "result_kind":
            if value in _SAFE_RESULT_KINDS:
                safe_details[key] = value
        elif key == "contract_violation":
            if isinstance(value, str) and _SAFE_CONTRACT_VIOLATION_PATTERN.fullmatch(value):
                safe_details[key] = value
        elif key == "node":
            if value in _SAFE_GRAPH_NODES:
                safe_details[key] = value
        elif key == "diagnosis_category":
            if value in _SAFE_DIAGNOSIS_CATEGORIES:
                safe_details[key] = value
        elif key == "evidence_status":
            if value in _SAFE_EVIDENCE_STATUSES:
                safe_details[key] = value
        elif key == "intent":
            if value in _SAFE_INTENTS:
                safe_details[key] = value
        elif key == "route":
            if value in _SAFE_ROUTES:
                safe_details[key] = value
        elif key == "prompt_version":
            if value in _SAFE_PROMPT_VERSIONS:
                safe_details[key] = value
        elif key == "role":
            if value in _SAFE_ROLES:
                safe_details[key] = value
        elif key == "skill_id":
            if value in _SAFE_SKILL_IDS:
                safe_details[key] = value
        elif key in {"skill_version", "profile_id", "profile_version"}:
            if isinstance(value, str) and _SAFE_VERSION_PATTERN.fullmatch(value):
                safe_details[key] = value
        elif key in {"fact_ref", "policy_ref", "submission_ref", "outbox_ref"}:
            if isinstance(value, str) and _SAFE_REFERENCE_PATTERN.fullmatch(value):
                safe_details[key] = value
        elif key == "dependency":
            if value in _SAFE_DEPENDENCIES:
                safe_details[key] = value
        elif key == "error_category":
            if isinstance(value, str) and _SAFE_ERROR_CATEGORY_PATTERN.fullmatch(value):
                safe_details[key] = value
    return safe_details
