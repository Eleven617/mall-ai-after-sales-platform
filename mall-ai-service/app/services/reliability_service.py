"""Small, explicit reliability controls for the local AgentOps runtime.

Redis is the Docker runtime's distributed token-bucket and lock backend.
Unit tests use the deterministic in-memory implementation.  Neither backend
stores prompts, JWTs, order numbers or tool payloads: Redis keys contain only a
hash of the trusted actor/role/action scope.
"""
from __future__ import annotations

import hashlib
import math
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Deque, Iterator, Protocol

from app.config import settings
from app.services.request_context import current_correlation_id


class ReliabilityError(RuntimeError):
    pass


class RateLimitExceeded(ReliabilityError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("当前操作过于频繁，请稍后重试。")
        self.retry_after_seconds = retry_after_seconds


class ConcurrentOperationError(ReliabilityError):
    pass


class ReliabilityBackendUnavailable(ReliabilityError):
    pass


class DependencyCircuitOpen(ReliabilityError):
    def __init__(self, dependency: str, retry_after_seconds: int) -> None:
        super().__init__("依赖服务正在恢复中。")
        self.dependency = dependency
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class RateLimitPolicy:
    capacity: int
    refill_per_second: float


@dataclass(frozen=True)
class LocalMetricSnapshot:
    name: str
    total: int
    succeeded: int
    failed: int
    p50_ms: int | None
    p95_ms: int | None


class ReliabilityBackend(Protocol):
    def consume(self, key: str, policy: RateLimitPolicy) -> tuple[bool, int]: ...

    def acquire_lock(self, key: str, token: str, ttl_seconds: int) -> bool: ...

    def release_lock(self, key: str, token: str) -> None: ...


class InMemoryReliabilityBackend:
    """Thread-safe fallback for tests and non-Docker local development."""

    def __init__(self, now_fn=time.monotonic) -> None:
        self._now_fn = now_fn
        self._buckets: dict[str, tuple[float, float]] = {}
        self._locks: dict[str, tuple[str, float]] = {}
        self._lock = RLock()

    def consume(self, key: str, policy: RateLimitPolicy) -> tuple[bool, int]:
        now = self._now_fn()
        with self._lock:
            tokens, updated_at = self._buckets.get(key, (float(policy.capacity), now))
            tokens = min(
                float(policy.capacity),
                tokens + max(0.0, now - updated_at) * policy.refill_per_second,
            )
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True, 0
            needed = max(0.0, 1 - tokens)
            retry_after = max(1, math.ceil(needed / policy.refill_per_second))
            self._buckets[key] = (tokens, now)
            return False, retry_after

    def acquire_lock(self, key: str, token: str, ttl_seconds: int) -> bool:
        now = self._now_fn()
        with self._lock:
            existing = self._locks.get(key)
            if existing and existing[1] > now:
                return False
            self._locks[key] = (token, now + ttl_seconds)
            return True

    def release_lock(self, key: str, token: str) -> None:
        with self._lock:
            existing = self._locks.get(key)
            if existing and existing[0] == token:
                self._locks.pop(key, None)


class RedisReliabilityBackend:
    """Atomic Redis Lua implementation used by Docker runtime controls."""

    _TOKEN_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local updated = tonumber(redis.call('HGET', KEYS[1], 'updated'))
if not tokens then tokens = capacity end
if not updated then updated = now end
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill)
if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
  redis.call('PEXPIRE', KEYS[1], ttl)
  return {1, 0}
end
local retry = math.max(1, math.ceil((1 - tokens) / refill))
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('PEXPIRE', KEYS[1], ttl)
return {0, retry}
"""
    _RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

    def __init__(self, redis_url: str, key_prefix: str) -> None:
        try:
            from redis import Redis

            self._client = Redis.from_url(redis_url, decode_responses=True)
        except Exception as exc:
            raise ReliabilityBackendUnavailable("Redis 可靠性控制不可用。") from exc
        self._key_prefix = key_prefix.rstrip(":")

    def consume(self, key: str, policy: RateLimitPolicy) -> tuple[bool, int]:
        try:
            result = self._client.eval(
                self._TOKEN_BUCKET_SCRIPT,
                1,
                self._key("bucket", key),
                policy.capacity,
                policy.refill_per_second,
                time.time(),
                max(1_000, math.ceil(policy.capacity / policy.refill_per_second * 2_000)),
            )
            return bool(int(result[0])), max(0, int(result[1]))
        except Exception as exc:
            raise ReliabilityBackendUnavailable("Redis 限流服务暂时不可用。") from exc

    def acquire_lock(self, key: str, token: str, ttl_seconds: int) -> bool:
        try:
            return bool(self._client.set(self._key("lock", key), token, nx=True, ex=ttl_seconds))
        except Exception as exc:
            raise ReliabilityBackendUnavailable("Redis 并发控制暂时不可用。") from exc

    def release_lock(self, key: str, token: str) -> None:
        try:
            self._client.eval(self._RELEASE_LOCK_SCRIPT, 1, self._key("lock", key), token)
        except Exception:
            # The TTL is still a safe backstop. Never let metrics/cleanup turn
            # a completed business result into a false client failure.
            return

    def _key(self, kind: str, key: str) -> str:
        return f"{self._key_prefix}:{kind}:{key}"


@dataclass
class _CircuitState:
    failures: int = 0
    open_until: float = 0.0


class LocalMetricsStore:
    def __init__(self, max_samples_per_name: int = 500) -> None:
        self._max_samples = max_samples_per_name
        self._samples: dict[str, Deque[tuple[bool, int]]] = defaultdict(deque)
        self._lock = RLock()

    def record(self, name: str, *, succeeded: bool, duration_ms: int) -> None:
        safe_name = name if name in _METRIC_NAMES else "unrecognized"
        safe_duration = min(max(int(duration_ms), 0), 3_600_000)
        with self._lock:
            samples = self._samples[safe_name]
            samples.append((succeeded, safe_duration))
            while len(samples) > self._max_samples:
                samples.popleft()

    def snapshots(self) -> list[LocalMetricSnapshot]:
        with self._lock:
            result: list[LocalMetricSnapshot] = []
            for name, samples in sorted(self._samples.items()):
                durations = sorted(duration for _, duration in samples)
                total = len(samples)
                succeeded = sum(1 for success, _ in samples if success)
                result.append(
                    LocalMetricSnapshot(
                        name=name,
                        total=total,
                        succeeded=succeeded,
                        failed=total - succeeded,
                        p50_ms=_percentile(durations, 0.50),
                        p95_ms=_percentile(durations, 0.95),
                    )
                )
            return result


_METRIC_NAMES = {
    "customer_service",
    "mcp_read",
    "quality_evaluation",
    "operations_analysis",
    "llm",
    "java",
    "rag",
    "rabbitmq_callback",
    "tool_rejected",
    "confirmation_failed",
}
_DEPENDENCIES = {"llm", "java", "rag", "rabbitmq", "redis"}
_POLICIES = {
    "customer_service": RateLimitPolicy(capacity=20, refill_per_second=20 / 60),
    "mcp_read": RateLimitPolicy(capacity=30, refill_per_second=30 / 60),
    "quality_evaluation": RateLimitPolicy(capacity=6, refill_per_second=6 / 600),
    "operations_analysis": RateLimitPolicy(capacity=12, refill_per_second=12 / 600),
    "confirmation": RateLimitPolicy(capacity=6, refill_per_second=6 / 60),
}


class ReliabilityGovernor:
    def __init__(
        self,
        backend: ReliabilityBackend | None = None,
        now_fn=time.monotonic,
        *,
        runtime_only_circuit_accounting: bool = False,
    ) -> None:
        self._backend = backend or _default_backend()
        self._now_fn = now_fn
        self._runtime_only_circuit_accounting = runtime_only_circuit_accounting
        self._circuits = {dependency: _CircuitState() for dependency in _DEPENDENCIES}
        self._circuit_lock = RLock()
        self.metrics = LocalMetricsStore()

    def check_rate_limit(
        self,
        *,
        actor_scope: str,
        role: str,
        action: str,
        skill_id: str | None = None,
    ) -> None:
        policy = _POLICIES.get(action, _POLICIES["customer_service"])
        key = _safe_scope_hash(actor_scope, role, action, skill_id or "none")
        allowed, retry_after = self._backend.consume(key, policy)
        if not allowed:
            raise RateLimitExceeded(retry_after)

    @contextmanager
    def lock(
        self,
        *,
        scope: str,
        kind: str,
        ttl_seconds: int = 20,
    ) -> Iterator[None]:
        if kind not in {"session", "proposal", "confirmation", "evaluation"}:
            raise ReliabilityError("未注册的并发锁类型。")
        key = _safe_scope_hash(scope, kind)
        token = uuid.uuid4().hex
        if not self._backend.acquire_lock(key, token, ttl_seconds):
            raise ConcurrentOperationError("相同任务正在处理中，请不要重复提交。")
        try:
            yield
        finally:
            self._backend.release_lock(key, token)

    def ensure_dependency_available(self, dependency: str) -> None:
        if dependency not in _DEPENDENCIES:
            raise ReliabilityError("未知依赖。")
        now = self._now_fn()
        with self._circuit_lock:
            state = self._circuits[dependency]
            if state.open_until > now:
                raise DependencyCircuitOpen(
                    dependency,
                    max(1, math.ceil(state.open_until - now)),
                )

    def record_dependency_success(self, dependency: str, *, duration_ms: int) -> None:
        if dependency not in _DEPENDENCIES:
            return
        with self._circuit_lock:
            self._circuits[dependency] = _CircuitState()
        self.metrics.record(dependency if dependency != "rabbitmq" else "rabbitmq_callback", succeeded=True, duration_ms=duration_ms)

    def record_dependency_failure(self, dependency: str, *, duration_ms: int) -> None:
        if dependency not in _DEPENDENCIES:
            return
        # Module-level clients are also invoked directly by existing unit
        # tests. A test-local fake outage must not leave the long-lived runtime
        # circuit open for a later, unrelated test or developer request.
        if self._runtime_only_circuit_accounting and current_correlation_id() == "offline":
            self.metrics.record(
                dependency if dependency != "rabbitmq" else "rabbitmq_callback",
                succeeded=False,
                duration_ms=duration_ms,
            )
            return
        with self._circuit_lock:
            state = self._circuits[dependency]
            state.failures += 1
            if state.failures >= settings.reliability_circuit_failure_threshold:
                state.open_until = self._now_fn() + settings.reliability_circuit_cooldown_seconds
        self.metrics.record(dependency if dependency != "rabbitmq" else "rabbitmq_callback", succeeded=False, duration_ms=duration_ms)

    def record_request(self, name: str, *, succeeded: bool, duration_ms: int) -> None:
        self.metrics.record(name, succeeded=succeeded, duration_ms=duration_ms)

    def set_backend_for_tests(self, backend: ReliabilityBackend) -> None:
        self._backend = backend

    def reset_for_tests(self) -> None:
        self._circuits = {dependency: _CircuitState() for dependency in _DEPENDENCIES}
        self.metrics = LocalMetricsStore()


def _default_backend() -> ReliabilityBackend:
    if settings.reliability_backend == "redis":
        return RedisReliabilityBackend(settings.redis_url, settings.reliability_key_prefix)
    return InMemoryReliabilityBackend()


def _safe_scope_hash(*parts: str) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    index = max(0, math.ceil(len(values) * percentile) - 1)
    return values[min(index, len(values) - 1)]


reliability_governor = ReliabilityGovernor(runtime_only_circuit_accounting=True)
