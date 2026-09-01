import pytest

from app.services.reliability_service import (
    ConcurrentOperationError,
    DependencyCircuitOpen,
    InMemoryReliabilityBackend,
    RateLimitExceeded,
    ReliabilityGovernor,
)


def test_token_bucket_hashes_scope_and_returns_retry_after():
    clock = [0.0]
    governor = ReliabilityGovernor(
        InMemoryReliabilityBackend(now_fn=lambda: clock[0]), now_fn=lambda: clock[0]
    )

    for _ in range(20):
        governor.check_rate_limit(
            actor_scope="member:101",
            role="unified_after_sales",
            action="customer_service",
        )
    with pytest.raises(RateLimitExceeded) as raised:
        governor.check_rate_limit(
            actor_scope="member:101",
            role="unified_after_sales",
            action="customer_service",
        )

    assert raised.value.retry_after_seconds >= 1
    clock[0] += 3.1
    governor.check_rate_limit(
        actor_scope="member:101",
        role="unified_after_sales",
        action="customer_service",
    )


def test_session_lock_rejects_parallel_operation_and_releases_owner_token():
    governor = ReliabilityGovernor(InMemoryReliabilityBackend())

    with governor.lock(scope="member-scoped-session", kind="session"):
        with pytest.raises(ConcurrentOperationError):
            with governor.lock(scope="member-scoped-session", kind="session"):
                pass

    with governor.lock(scope="member-scoped-session", kind="session"):
        pass


def test_dependency_circuit_cools_down_and_metrics_expose_percentiles():
    clock = [0.0]
    governor = ReliabilityGovernor(
        InMemoryReliabilityBackend(now_fn=lambda: clock[0]), now_fn=lambda: clock[0]
    )
    for duration in (10, 20, 30):
        governor.record_dependency_failure("llm", duration_ms=duration)

    with pytest.raises(DependencyCircuitOpen):
        governor.ensure_dependency_available("llm")
    clock[0] += 21
    governor.ensure_dependency_available("llm")
    governor.record_dependency_success("llm", duration_ms=40)

    metric = next(item for item in governor.metrics.snapshots() if item.name == "llm")
    assert metric.total == 4
    assert metric.failed == 3
    assert metric.succeeded == 1
    assert metric.p50_ms == 20
    assert metric.p95_ms == 40
