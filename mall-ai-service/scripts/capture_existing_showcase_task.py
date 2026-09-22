"""Capture an already persisted showcase task without creating or mutating it.

Credentials and the synthetic conversation identifier are process-only inputs.
The report stores only a one-way conversation hash, public frame paths and
hashes, plus provenance labels that make the post-capture boundary explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from run_real_local_showcase import _capture_chain_frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--capture-tool-version", required=True)
    args = parser.parse_args()

    password = os.getenv("MALL_LIVE_DEMO_PASSWORD", "")
    username = os.getenv("MALL_CAPTURE_CUSTOMER_USER", "")
    conversation_id = os.getenv("MALL_CAPTURE_CONVERSATION_ID", "")
    if not password or not username or not conversation_id:
        print(json.dumps({"status": "environment_blocked", "reason": "missing_process_capture_input"}))
        return 2

    captured = _capture_chain_frames(
        password,
        username,
        args.assets,
        "main_open_task_closed_loop",
        conversation_id,
        ("申请取消退款",),
    )
    report = {
        "schemaVersion": "v304-existing-task-post-capture.v1",
        "status": "passed" if captured.get("valid") else "failed",
        "source": {
            "releaseId": args.release_id,
            "batchId": args.batch_id,
            "runtimeCommit": args.runtime_commit,
            "conversationHash": hashlib.sha256(conversation_id.encode("utf-8")).hexdigest(),
        },
        "capture": {
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "captureToolVersion": args.capture_tool_version,
            "mode": "post_capture_existing_live_task",
            "frames": captured,
            "externalProviderRequests": 0,
            "taskCreateRequests": 0,
            "taskContinueRequests": 0,
            "taskAmendRequests": 0,
            "taskConfirmationRequests": 0,
        },
        "claimBoundary": (
            "Frames were captured after the source batch from its persisted task. "
            "They prove the later page state only, not an original real-time recording "
            "or missing intermediate steps."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "frameCount": captured.get("frameCount", 0)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
