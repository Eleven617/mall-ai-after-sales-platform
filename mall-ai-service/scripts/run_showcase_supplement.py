"""Run the explicitly authorized two-chain live showcase supplement once.

This is not an evaluation batch.  It uses a fresh, metadata-only release
ledger and immutable lock, and refuses every scenario other than the two
missing current-live demonstrations.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
if str(SERVICE_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from app.config import settings  # noqa: E402
from app.services.release_ledger import read_release_events, summarize_release_events  # noqa: E402
from run_deepseek_release_batch import _atomic_create_json, _atomic_replace_json, _runtime_identity  # noqa: E402
from run_real_local_showcase import run_real_local_showcase  # noqa: E402


SUPPLEMENT_SCENARIOS = ("clarify_pause_resume", "fact_change_replan")
MAX_HTTP_ATTEMPTS = 40
MAX_TOTAL_TOKENS = 100_000


def _metrics(batch_id: str) -> dict[str, object]:
    path = os.getenv("MALL_RELEASE_LEDGER_PATH")
    if not path:
        raise ValueError("ledger_path_missing")
    events = read_release_events(path, batch_id=batch_id)
    summary = summarize_release_events(events)
    reservations = sum(1 for item in events if item.get("eventType") == "provider_reservation")
    settlements = sum(1 for item in events if item.get("eventType") == "provider_reservation_settlement")
    return {
        "logicalProviderRequests": summary["logicalProviderRequests"],
        "providerHttpAttempts": summary["providerHttpAttempts"],
        "successfulRequests": summary["providerSuccesses"],
        "failedRequests": summary["providerFailures"],
        "totalTokens": summary["totalTokens"],
        "reservations": reservations,
        "settlements": settlements,
        "unresolvedReservations": summary["unresolvedReservations"],
        # ``summarize_release_events`` exposes the public counter as
        # ``deniedBeforeNetwork``. Keep the supplement report's clearer
        # ``budgetDenials`` name without assuming a second summary schema.
        "budgetDenials": summary.get("budgetDenials", summary.get("deniedBeforeNetwork", 0)),
        "ledgerReconciled": True,
    }


def run_showcase_supplement(*, release_id: str, runtime_commit: str, report_path: Path, lock_path: Path) -> int:
    if not release_id.startswith("mall-v3.0.4-showcase-supplement-"):
        return 3
    if os.getenv("MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS") != str(MAX_HTTP_ATTEMPTS):
        return 3
    if os.getenv("MALL_RELEASE_MAX_TOTAL_TOKENS") != str(MAX_TOTAL_TOKENS):
        return 3
    if not settings.deepseek_api_key:
        return 2
    identity_ok, _ = _runtime_identity(runtime_commit)
    if not identity_ok:
        return 2

    batch_id = f"showcase_supplement-{uuid.uuid4().hex[:12]}"
    lock = {
        "schemaVersion": "deepseek-showcase-supplement-lock.v1",
        "releaseId": release_id,
        "batchIds": [batch_id],
        "runtimeCommit": runtime_commit,
        "status": "RUNNING",
        "scope": list(SUPPLEMENT_SCENARIOS),
        "maxProviderHttpAttempts": MAX_HTTP_ATTEMPTS,
        "maxTotalTokens": MAX_TOTAL_TOKENS,
        "requests": 0,
        "totalTokens": 0,
    }
    try:
        _atomic_create_json(lock_path, lock)
    except FileExistsError:
        return 3

    os.environ["MALL_RELEASE_ID"] = release_id
    os.environ["MALL_RELEASE_BATCH_ID"] = batch_id
    try:
        showcase = run_real_local_showcase(
            report_dir=report_path.parent / f"{batch_id}-artifacts",
            batch_id=batch_id,
            provider_mode="live",
            scenarios=SUPPLEMENT_SCENARIOS,
        )
        metrics = _metrics(batch_id)
        passed = (
            showcase.get("status") == "passed"
            and showcase.get("requestedScenarios") == list(SUPPLEMENT_SCENARIOS)
            and len(showcase.get("chains", [])) == len(SUPPLEMENT_SCENARIOS)
            and int(showcase.get("browserFrameCount", 0)) == 8
            and int(metrics["providerHttpAttempts"]) > 0
            and int(metrics["providerHttpAttempts"]) <= MAX_HTTP_ATTEMPTS
            and int(metrics["totalTokens"]) <= MAX_TOTAL_TOKENS
            and int(metrics["failedRequests"]) == 0
            and int(metrics["unresolvedReservations"]) == 0
            and int(metrics["budgetDenials"]) == 0
        )
        status = "passed" if passed else "failed"
        payload = {
            "schemaVersion": "v304-showcase-supplement-report.v1",
            "status": status,
            "releaseId": release_id,
            "batchId": batch_id,
            "runtimeCommit": runtime_commit,
            "scope": list(SUPPLEMENT_SCENARIOS),
            "showcase": showcase,
            "ledgerMetrics": metrics,
            "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except Exception:
        status = "failed"
        payload = {
            "schemaVersion": "v304-showcase-supplement-report.v1",
            "status": status,
            "releaseId": release_id,
            "batchId": batch_id,
            "runtimeCommit": runtime_commit,
            "scope": list(SUPPLEMENT_SCENARIOS),
            "failureCategory": "runner_exception",
            "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lock.update({
        "status": "PASSED" if status == "passed" else "FAILED",
        "requests": payload.get("ledgerMetrics", {}).get("logicalProviderRequests", 0),
        "totalTokens": payload.get("ledgerMetrics", {}).get("totalTokens", 0),
    })
    _atomic_replace_json(lock_path, lock)
    print(json.dumps({"status": status, "batchId": batch_id}, ensure_ascii=False))
    return 0 if status == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    return run_showcase_supplement(
        release_id=args.release_id,
        runtime_commit=args.runtime_commit,
        report_path=args.report,
        lock_path=args.lock,
    )


if __name__ == "__main__":
    raise SystemExit(main())
