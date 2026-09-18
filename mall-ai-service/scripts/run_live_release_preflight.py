"""Run the no-model, no-lock live release environment preflight.

The process-only secret is read as ``MALL_LIVE_DEMO_PASSWORD`` by the shared
runtime preflight module; this script never prints its value.
"""
from __future__ import annotations

import json
import sys

from app.runtime.live_release_preflight import (
    LiveReleasePreflightError,
    verify_local_demo_accounts,
)


def main() -> int:
    try:
        result = verify_local_demo_accounts()
    except LiveReleasePreflightError as exc:
        print(json.dumps({"status": "blocked", "failureCode": exc.code}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result.status, "accountCount": result.account_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
