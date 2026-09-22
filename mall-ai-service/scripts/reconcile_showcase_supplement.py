"""Create a read-only reconciliation for a completed supplement run.

The original report remains immutable when a wrapper fails during final
serialization after the business scenarios and ledger have completed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.release_ledger import read_release_events, summarize_release_events


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconcile(*, release_id: str, batch_id: str, runtime_commit: str, ledger: Path, artifacts: Path) -> dict[str, object]:
    events = read_release_events(ledger, batch_id=batch_id)
    metrics = summarize_release_events(events)
    assets = [
        {"path": str(path), "sha256": _sha256(path), "size": path.stat().st_size}
        for path in sorted(artifacts.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".png", ".gif"}
    ]
    scenarios = {}
    for event in events:
        if event.get("eventType") == "scenario" and event.get("outcome") == "succeeded":
            scenarios[str(event.get("scenario"))] = {
                "completedStepCount": event.get("completedStepCount", 0),
                "modelCalled": event.get("modelCalled", False),
                "javaCommit": event.get("javaCommit", False),
                "statusReadback": event.get("statusReadback", False),
            }
    return {
        "schemaVersion": "v304-showcase-supplement-reconciliation.v1",
        "sourceStatus": "FAILED/runner_exception",
        "sourceReason": "wrapper summary serialization failed after scenario and screenshot completion",
        "releaseId": release_id,
        "batchId": batch_id,
        "runtimeCommit": runtime_commit,
        "scenarios": scenarios,
        "ledgerMetrics": {
            "logicalProviderRequests": metrics["logicalProviderRequests"],
            "providerHttpAttempts": metrics["providerHttpAttempts"],
            "successfulRequests": metrics["providerSuccesses"],
            "failedRequests": metrics["providerFailures"],
            "totalTokens": metrics["totalTokens"],
            "reservations": len([e for e in events if e.get("eventType") == "provider_reservation"]),
            "settlements": len([e for e in events if e.get("eventType") == "provider_reservation_settlement"]),
            "unresolvedReservations": metrics["unresolvedReservations"],
            "budgetDenials": metrics["deniedBeforeNetwork"],
        },
        "assets": assets,
        "derivedOnly": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = reconcile(
        release_id=args.release_id,
        batch_id=args.batch_id,
        runtime_commit=args.runtime_commit,
        ledger=args.ledger,
        artifacts=args.artifacts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "assets": len(payload["assets"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
