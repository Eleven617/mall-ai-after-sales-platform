"""Fail-closed authorization for every external LLM HTTP request.

The presence of a provider key is configuration only.  A request may leave
the process only when an explicit offline/mock/live grant is bound to the
current context.  The guard intentionally exposes only a safe error category;
it never accepts or logs prompts, model output, credentials, or business IDs.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlparse


_SHA = re.compile(r"^[0-9a-f]{40}$")
_GRANT: ContextVar["ProviderAccessGrant | None"] = ContextVar(
    "mall_provider_access_grant", default=None
)


class ProviderGuardError(RuntimeError):
    """Safe, categorized denial before any provider socket is opened."""

    category = "provider_guard"


@dataclass(frozen=True)
class ProviderAccessGrant:
    mode: str
    release_id: str | None
    batch_id: str | None
    ledger_path: str | None
    runtime_commit: str | None
    authorized: bool = False
    allow_mock: bool = False


def _safe(value: object, *, max_length: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_length:
        return None
    return value


def _env_grant() -> ProviderAccessGrant:
    return ProviderAccessGrant(
        mode=os.getenv("MALL_PROVIDER_MODE", os.getenv("MALL_RUNTIME_PROVIDER_MODE", "offline"))
        .strip()
        .lower(),
        release_id=_safe(os.getenv("MALL_RELEASE_ID")),
        batch_id=_safe(os.getenv("MALL_RELEASE_BATCH_ID")),
        ledger_path=_safe(os.getenv("MALL_RELEASE_LEDGER_PATH")),
        runtime_commit=_safe(os.getenv("MALL_RUNTIME_COMMIT")),
        authorized=os.getenv("MALL_PROVIDER_LIVE_AUTH", "0").strip() == "1",
    )


@contextmanager
def provider_access_context(
    *,
    mode: str,
    release_id: str | None = None,
    batch_id: str | None = None,
    ledger_path: str | None = None,
    runtime_commit: str | None = None,
    authorized: bool = False,
    allow_mock: bool = False,
) -> Iterator[None]:
    """Bind a short-lived grant for a runner, request, or unit-test fixture."""

    token = _GRANT.set(
        ProviderAccessGrant(
            mode=str(mode or "offline").strip().lower(),
            release_id=_safe(release_id),
            batch_id=_safe(batch_id),
            ledger_path=_safe(ledger_path),
            runtime_commit=_safe(runtime_commit),
            authorized=bool(authorized),
            allow_mock=bool(allow_mock),
        )
    )
    try:
        yield
    finally:
        _GRANT.reset(token)


def current_provider_access() -> ProviderAccessGrant:
    return _GRANT.get() or _env_grant()


def _complete(grant: ProviderAccessGrant) -> bool:
    return bool(
        grant.release_id
        and grant.batch_id
        and grant.ledger_path
        and grant.runtime_commit
        and _SHA.fullmatch(grant.runtime_commit)
    )


def _loopback_or_fixture(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"} or host.endswith(".invalid")


def assert_provider_request_allowed(url: str) -> None:
    """Reject a request before ``httpx`` is called."""

    grant = current_provider_access()
    mode = grant.mode
    if mode in {"", "offline", "deterministic", "replay", "disabled"}:
        raise ProviderGuardError("external provider disabled in offline mode")
    if mode == "mock":
        if not grant.allow_mock or not _complete(grant) or not _loopback_or_fixture(url):
            raise ProviderGuardError("mock provider context is incomplete")
        return
    if mode != "live":
        raise ProviderGuardError("provider mode is not allow-listed")
    if not grant.authorized or not _complete(grant):
        raise ProviderGuardError("formal live provider context is incomplete")


def provider_guard_snapshot() -> dict[str, object]:
    """Safe diagnostics for tests/readiness; no paths, IDs, or secrets."""

    grant = current_provider_access()
    return {
        "mode": grant.mode,
        "authorized": grant.authorized,
        "complete": _complete(grant),
        "ledgerConfigured": bool(grant.ledger_path),
        "releaseConfigured": bool(grant.release_id),
        "batchConfigured": bool(grant.batch_id),
        "runtimeCommitConfigured": bool(grant.runtime_commit and _SHA.fullmatch(grant.runtime_commit)),
    }
