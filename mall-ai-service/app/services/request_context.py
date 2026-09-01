"""Request-scoped correlation context with a safe W3C traceparent bridge.

The values are opaque random identifiers.  They are useful for joining local
FastAPI, Java and message-event logs but are never derived from a JWT, member,
order or customer message.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_CORRELATION_PATTERN = re.compile(r"^[a-f0-9]{16,64}$")
_TRACEPARENT_PATTERN = re.compile(r"^00-[a-f0-9]{32}-[a-f0-9]{16}-[0-9a-f]{2}$")
_correlation_id: ContextVar[str | None] = ContextVar("mall_ai_correlation_id", default=None)
_traceparent: ContextVar[str | None] = ContextVar("mall_ai_traceparent", default=None)


def new_correlation_id() -> str:
    return secrets.token_hex(16)


def normalize_correlation_id(value: str | None) -> str:
    candidate = value.strip().lower() if isinstance(value, str) else ""
    return candidate if _CORRELATION_PATTERN.fullmatch(candidate) else new_correlation_id()


def normalize_traceparent(value: str | None, correlation_id: str) -> str:
    candidate = value.strip().lower() if isinstance(value, str) else ""
    if _TRACEPARENT_PATTERN.fullmatch(candidate):
        return candidate
    trace_id = hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:32]
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


@contextmanager
def request_correlation(
    correlation_id: str | None = None,
    traceparent: str | None = None,
) -> Iterator[tuple[str, str]]:
    normalized_correlation = normalize_correlation_id(correlation_id)
    normalized_traceparent = normalize_traceparent(traceparent, normalized_correlation)
    correlation_token = _correlation_id.set(normalized_correlation)
    traceparent_token = _traceparent.set(normalized_traceparent)
    try:
        yield normalized_correlation, normalized_traceparent
    finally:
        _traceparent.reset(traceparent_token)
        _correlation_id.reset(correlation_token)


def current_correlation_id() -> str:
    value = _correlation_id.get()
    return value if value is not None else "offline"


def current_correlation_ref() -> str:
    """Return only a fixed-length correlation reference for safe stores/traces."""

    return hashlib.sha256(current_correlation_id().encode("utf-8")).hexdigest()[:24]


def current_traceparent() -> str | None:
    return _traceparent.get()


def correlation_headers() -> dict[str, str]:
    """Headers allowed to cross internal service boundaries."""

    headers = {"X-Correlation-Id": current_correlation_id()}
    traceparent = current_traceparent()
    if traceparent is not None:
        headers["traceparent"] = traceparent
    return headers
