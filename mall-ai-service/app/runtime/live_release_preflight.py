"""Fail-closed checks required before a paid live release batch.

The preflight deliberately uses only the local Java demo API.  It never
creates a release id, batch id, ledger event, lock, or model client.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = SERVICE_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from bootstrap_live_demo import DemoAccount, LiveDemoSetupError, _ensure_login  # noqa: E402


PASSWORD_ENV_NAME = "MALL_LIVE_DEMO_PASSWORD"
_OBVIOUS_PLACEHOLDERS = {
    "password",
    "changeme",
    "change-me",
    "replace_with_your_key",
    "replace-with-your-password",
}


class LiveReleasePreflightError(RuntimeError):
    """Safe error whose text never contains the supplied secret."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LiveReleasePreflightResult:
    status: str
    account_count: int = 0


def require_demo_password(environ: Mapping[str, str] | None = None) -> str:
    """Return a usable process secret or raise a non-sensitive error code."""

    source = os.environ if environ is None else environ
    value = source.get(PASSWORD_ENV_NAME)
    if not isinstance(value, str) or not value.strip():
        raise LiveReleasePreflightError("missing_live_demo_password")
    normalized = value.strip()
    if len(normalized) < 12 or normalized.lower() in _OBVIOUS_PLACEHOLDERS:
        raise LiveReleasePreflightError("invalid_live_demo_password")
    return normalized


def verify_local_demo_accounts(*, java_base: str | None = None) -> LiveReleasePreflightResult:
    """Create and log in two disposable synthetic accounts through Java."""

    password = require_demo_password()
    base = (java_base or os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085")).rstrip("/")
    nonce = uuid.uuid4().hex[:12]
    phone_seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount("preflight_a", f"ai_preflight_a_{nonce}", password, f"199{phone_seed:08d}"),
        DemoAccount("preflight_b", f"ai_preflight_b_{nonce}", password, f"198{(phone_seed + 1) % 100_000_000:08d}"),
    )
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            for account in accounts:
                _ensure_login(client, base, account)
    except (httpx.HTTPError, LiveDemoSetupError, ValueError, TypeError) as exc:
        # Do not retain or expose response text, account data, or the secret.
        raise LiveReleasePreflightError("demo_account_preflight_failed") from exc
    return LiveReleasePreflightResult(status="passed", account_count=len(accounts))
