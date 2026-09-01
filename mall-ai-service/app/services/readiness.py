"""Dependency readiness checks used by local deployment health probes."""
from collections.abc import Callable
from typing import Any

import redis

from app.config import settings


ReadinessReport = dict[str, str]


def get_readiness(
    conversation_backend: str | None = None,
    redis_url: str | None = None,
    redis_factory: Callable[..., Any] = redis.Redis.from_url,
) -> ReadinessReport:
    """Return a safe readiness summary without probing model providers.

    Liveness only proves the FastAPI process exists. Readiness additionally
    verifies the configured durable conversation dependency. External LLM and
    embedding providers are intentionally excluded: checking them would spend
    quota and turn a transient model outage into a container restart loop.
    """
    backend = (conversation_backend or settings.conversation_store_backend).strip().lower()
    if backend == "memory":
        return {"status": "ok", "conversation_store": "memory"}
    if backend != "redis":
        return {"status": "unavailable", "conversation_store": "invalid_configuration"}

    try:
        client = redis_factory(
            redis_url or settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        if not client.ping():
            return {"status": "unavailable", "conversation_store": "redis"}
    except Exception:
        return {"status": "unavailable", "conversation_store": "redis"}
    return {"status": "ok", "conversation_store": "redis"}
