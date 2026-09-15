"""One-shot zero-model slow request through the public Nginx proxy.

This is intentionally a release-gate runner, not a normal CI test.  The
deterministic provider is delayed by the Compose environment so the request
lasts longer than the historical 60-second gateway timeout while remaining
inside the bounded 240-second Runtime deadline.  The task is never confirmed,
so Java final-write count must remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

import httpx

from app.services.release_ledger import (
    append_release_event,
    read_release_events,
    release_ledger_context,
    summarize_release_events,
)
from scripts.run_real_local_showcase import (
    ShowcaseError,
    _create_agent_task,
    _list_applications,
    _login,
    _prepare_fixture,
)


ROOT = Path(__file__).resolve().parents[2]


def run(report_path: Path, batch_id: str) -> dict[str, object]:
    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        return {"status": "environment_blocked", "failureCode": "missing_process_fixture_password"}
    ledger_path = os.getenv("MALL_RELEASE_LEDGER_PATH")
    web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    api_base = web_base + "/api"
    started = time.monotonic()
    result: dict[str, object] = {
        "schemaVersion": "mall-v3.0.2-slow-gateway.v1",
        "batchId": batch_id,
        "providerMode": os.getenv("MALL_RUNTIME_PROVIDER_MODE", "deterministic"),
        "requestUrl": f"{api_base}/agent-tasks",
        "throughProxy": web_base.startswith("http://127.0.0.1:5173"),
        "externalProviderRequests": 0,
        "javaWriteObserved": False,
    }
    with release_ledger_context(batch_id=batch_id, path=ledger_path, source="slow-gateway-host"):
        try:
            account_a, _, order_a = _prepare_fixture(password)
            timeout = httpx.Timeout(330.0, connect=10.0, write=10.0, pool=10.0)
            with httpx.Client(timeout=timeout, trust_env=False, headers={"X-Mall-Release-Batch-Id": batch_id}) as client:
                auth = _login(client, api_base, account_a.username, password)
                before = _list_applications(client, api_base, auth)
                request_started = time.monotonic()
                created = _create_agent_task(
                    client,
                    api_base,
                    auth,
                    str(uuid.uuid4()),
                    f"订单号：{order_a.order_sn}，申请取消退款，形成待确认方案",
                )
                elapsed = time.monotonic() - request_started
                after = _list_applications(client, api_base, auth)
            status = created.get("status")
            proposal = isinstance(created.get("action"), dict)
            result.update(
                {
                    "status": "passed" if status == "ready_to_commit" and proposal and len(after) == len(before) else "failed",
                    "elapsedSeconds": round(elapsed, 3),
                    "httpStatus": 201,
                    "taskStatus": status,
                    "proposalFormed": proposal,
                    "durationAtLeast65Seconds": elapsed > 65,
                    "runtimeWithin240Seconds": elapsed < 240,
                    "javaWriteObserved": len(after) != len(before),
                }
            )
            if result["status"] == "passed":
                append_release_event(
                    event_type="scenario",
                    operation="v3.0.2.slow_gateway",
                    outcome="succeeded",
                    scenario="slow_gateway_create",
                    stage="agent_task_create",
                    completed_step_count=3,
                    proposal_formed=True,
                    java_commit=False,
                    status_readback=True,
                )
            else:
                result.update({"failureCode": "scenario_assertion_failure", "stage": "agent_task_create"})
        except ShowcaseError as exc:
            result.update(
                {
                    "status": "failed",
                    "failureCode": exc.failure_code,
                    "stage": exc.stage,
                    "httpStatusClass": exc.http_status_class,
                    "proposalFormed": exc.proposal_formed,
                    "javaWriteObserved": exc.java_commit,
                }
            )
            append_release_event(
                event_type="scenario",
                operation="v3.0.2.slow_gateway",
                outcome="failed",
                failure_class="scenario_failure",
                scenario="slow_gateway_create",
                stage=exc.stage,
                failure_code=exc.failure_code,
                proposal_formed=exc.proposal_formed,
                java_commit=exc.java_commit,
            )
        except httpx.TimeoutException:
            result.update({"status": "failed", "failureCode": "client_read_timeout", "stage": "agent_task_create"})
        except Exception:
            result.update({"status": "failed", "failureCode": "unknown_failure", "stage": "unexpected"})
        events = read_release_events(ledger_path, batch_id=batch_id) if ledger_path else []
        summary = summarize_release_events(events)
        result["ledger"] = {
            "providerRequests": summary["providerRequests"],
            "providerTokens": summary["totalTokens"],
            "scenarioFailures": summary["scenarioFailures"],
            "events": summary["events"],
        }
        result["externalProviderRequests"] = summary["providerRequests"]
        result["durationSeconds"] = round(time.monotonic() - started, 3)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    result = run(args.report, args.batch_id)
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "elapsedSeconds": result.get("elapsedSeconds"),
                "providerRequests": result.get("externalProviderRequests"),
                "failureCode": result.get("failureCode"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
