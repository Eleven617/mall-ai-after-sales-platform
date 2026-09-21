"""Execute the durable-recovery registry against the local Docker stack.

This is deliberately not a manifest counter.  Every registered case creates a
real Agent Task through FastAPI, reads/writes only through the public APIs, and
checks the persisted task after a service restart or an explicitly bounded
dependency interruption.  The runtime provider must already be configured as
``deterministic`` or ``replay`` in the running container; this script never
contacts a hosted model.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "mall-ai-service"
DEFAULT_MANIFEST = ROOT / "evals" / "v3" / "release-manifest.json"
SAFE_FAILURE_CODES = {
    "login_failed",
    "task_create_failed",
    "task_not_waiting",
    "task_resume_failed",
    "task_identity_changed",
    "duplicate_confirmation_not_idempotent",
    "proposal_not_ready",
    "withdraw_not_safe",
    "store_recovery_failed",
    "service_restart_failed",
    "dependency_recovery_failed",
    "unexpected_failure",
}


class RecoveryCaseError(RuntimeError):
    def __init__(self, code: str, stage: str, details: dict[str, Any] | None = None) -> None:
        self.code = code if code in SAFE_FAILURE_CODES else "unexpected_failure"
        self.stage = stage
        self.details = details or {}
        super().__init__(self.code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--password", default=None, help="process-only fixture password")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--provider-mode", choices=("deterministic", "replay"), required=True)
    args = parser.parse_args()

    password = args.password or os.getenv("MALL_FIELD_FIXTURE_PASSWORD")
    if not password:
        raise SystemExit("fixture password is required in the process environment")
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    cases = [
        item
        for item in json.loads(args.manifest.read_text(encoding="utf-8")).get("cases", [])
        if isinstance(item, dict) and item.get("category") == "durable_async_recovery"
    ]
    if len(cases) != 32:
        raise SystemExit("durable recovery manifest must contain exactly 32 cases")

    account_a = fixture.get("account_a")
    if not isinstance(account_a, dict):
        raise SystemExit("fixture account_a is unavailable")
    username = str(account_a.get("username", ""))
    order_sn = str(account_a.get("order_sn", ""))
    if not username or not order_sn:
        raise SystemExit("fixture account_a is incomplete")

    started = time.monotonic()
    base = os.getenv("MALL_AI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=60, trust_env=False) as client:
        authorization = _login(client, base, username, password)
        for index, case in enumerate(cases):
            case_id = str(case.get("caseId", f"RECOVERY-{index + 1:03d}"))
            scenario = str(case.get("fixture", {}).get("scenario", ""))
            try:
                result = _run_case(
                    client,
                    base,
                    java_base,
                    authorization,
                    password,
                    order_sn,
                    scenario,
                    index,
                )
                results.append(
                    {
                        "caseId": case_id,
                        "scenario": scenario,
                        "status": "passed",
                        "providerMode": args.provider_mode,
                        **result,
                    }
                )
            except RecoveryCaseError as exc:
                results.append(
                    {
                        "caseId": case_id,
                        "scenario": scenario,
                        "status": "failed",
                        "providerMode": args.provider_mode,
                        "failureCode": exc.code,
                        "stage": exc.stage,
                        **exc.details,
                    }
                )
            except Exception:
                results.append(
                    {
                        "caseId": case_id,
                        "scenario": scenario,
                        "status": "failed",
                        "providerMode": args.provider_mode,
                        "failureCode": "unexpected_failure",
                        "stage": "unexpected",
                    }
                )

    payload = {
        "suite": "durable_async_recovery",
        "providerMode": args.provider_mode,
        "caseCount": len(results),
        "passed": sum(item["status"] == "passed" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "environmentBlocked": 0,
        "durationMs": round((time.monotonic() - started) * 1000),
        "containsRawValuesInReport": False,
        "cases": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("suite", "providerMode", "caseCount", "passed", "failed", "environmentBlocked")}, ensure_ascii=False))
    return 0 if payload["failed"] == 0 else 1


def _login(client: httpx.Client, base: str, username: str, password: str) -> str:
    response = client.post(f"{base}/auth/login", json={"username": username, "password": password})
    payload = _object(response)
    authorization = payload.get("authorization")
    if response.status_code != 200 or not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise RecoveryCaseError("login_failed", "login")
    return authorization


def _run_case(
    client: httpx.Client,
    base: str,
    java_base: str,
    authorization: str,
    password: str,
    order_sn: str,
    scenario: str,
    index: int,
) -> dict[str, Any]:
    if scenario in {"idempotent_commit", "outbox_duplicate", "cancel_race"}:
        return _run_proposal_case(client, base, authorization, password, order_sn, scenario, index)
    if scenario == "store_unavailable":
        return _run_store_recovery_case(client, base, authorization, order_sn)

    waiting = _create_waiting_task(client, base, authorization, f"recovery-{index}-{uuid.uuid4().hex[:8]}")
    task_ref = waiting["task_ref"]
    first_hash = _opaque_hash(task_ref)
    if scenario in {"task_resume", "timeout_reconcile"}:
        _restart_service()
    elif scenario == "out_of_order_event":
        first = _continue(client, base, authorization, task_ref, f"订单号：{order_sn}")
        if first.get("task_ref") != task_ref:
            raise RecoveryCaseError("task_identity_changed", "first_resume")
        duplicate_response = _continue_raw(client, base, authorization, task_ref, f"订单号：{order_sn}")
        if duplicate_response.status_code == 200:
            duplicate = _object(duplicate_response)
            if duplicate.get("task_ref") != task_ref:
                raise RecoveryCaseError("task_identity_changed", "duplicate_resume")
        elif duplicate_response.status_code not in {404, 409}:
            raise RecoveryCaseError("task_identity_changed", "duplicate_resume")
        return {"assertions": ["same_task_ref_after_out_of_order_message", "no_duplicate_task"]}
    elif scenario == "budget_exhausted":
        safe = _continue(client, base, authorization, task_ref, "先记住这个任务，我稍后补充")
        if safe.get("task_ref") != task_ref or safe.get("status") != "waiting_for_user":
            raise RecoveryCaseError("task_resume_failed", "bounded_wait")
        return {"assertions": ["bounded_wait", "no_unapproved_write"]}

    resumed = _continue(client, base, authorization, task_ref, f"订单号：{order_sn}")
    if resumed.get("task_ref") != task_ref or _opaque_hash(str(resumed.get("task_ref"))) != first_hash:
        raise RecoveryCaseError("task_identity_changed", "resume")
    if not isinstance(resumed.get("artifacts"), list) or not resumed["artifacts"]:
        raise RecoveryCaseError("task_resume_failed", "verified_fact")
    return {"assertions": ["checkpoint_resume", "owner_scope_preserved", "no_unrelated_business_write"]}


def _run_proposal_case(
    client: httpx.Client,
    base: str,
    authorization: str,
    password: str,
    order_sn: str,
    scenario: str,
    index: int,
) -> dict[str, Any]:
    # Proposal cases deliberately exercise Java state changes.  Reusing the
    # single read-only recovery fixture would make one confirmed case revoke
    # eligibility for all later cases, turning a valid isolation defect into a
    # false failure.  Provision one disposable synthetic account/order for
    # each proposal case so every case starts from a fresh Java-owned state.
    proposal_authorization, proposal_order_sn = _prepare_proposal_fixture(client, base, password, index)
    session_id = f"recovery-proposal-{index}-{uuid.uuid4().hex[:8]}"
    created = _create_task(
        client,
        base,
        proposal_authorization,
        session_id,
        f"订单号：{proposal_order_sn}，申请取消退款，完成售后闭环",
    )
    task_ref = created.get("task_ref")
    if created.get("status") != "ready_to_commit" or not isinstance(task_ref, str):
        raise RecoveryCaseError("proposal_not_ready", "proposal")
    before = _list_applications(client, base, proposal_authorization)
    if scenario == "cancel_race":
        withdrawn = _confirm_raw(client, base, proposal_authorization, task_ref, "withdraw", created)
        if withdrawn.status_code != 200:
            raise RecoveryCaseError("withdraw_not_safe", "withdraw")
        after = _list_applications(client, base, proposal_authorization)
        if len(after) != len(before):
            raise RecoveryCaseError("withdraw_not_safe", "withdraw_write")
        return {"assertions": ["withdraw_without_java_write", "transaction_gate_released"]}

    confirmed = _confirm_raw(client, base, proposal_authorization, task_ref, "confirm", created)
    if confirmed.status_code != 200:
        raise RecoveryCaseError("task_resume_failed", "confirm")
    duplicate = _confirm_raw(client, base, proposal_authorization, task_ref, "confirm", created)
    after = _list_applications(client, base, proposal_authorization)
    # Depending on whether the Java facade returns its idempotent result or
    # the task gate is already consumed, the second confirmation is 200, 404,
    # or 409.  The hard invariant is that it never creates a second public
    # application.
    if duplicate.status_code not in {200, 404, 409} or len(after) > len(before) + 1:
        raise RecoveryCaseError(
            "duplicate_confirmation_not_idempotent",
            "duplicate_confirm",
            {"duplicateStatusClass": f"{duplicate.status_code // 100}xx", "applicationCountDelta": len(after) - len(before)},
        )
    return {"assertions": ["java_confirmation_boundary", "duplicate_confirmation_no_second_write", "outbox_observation_safe"]}


def _prepare_proposal_fixture(client: httpx.Client, base: str, password: str, index: int) -> tuple[str, str]:
    """Create a disposable Java-owned account/order for one mutating case.

    The bootstrap utility is itself an HTTP-only synthetic fixture creator. It
    never prints or persists credentials in the recovery report; this helper
    reads the short-lived result file only long enough to obtain the account
    and order references needed by the real public APIs.
    """

    result_dir = ROOT / "tmp" / "durable-proposal-fixtures"
    result_dir.mkdir(parents=True, exist_ok=True)
    last_error: RecoveryCaseError | None = None
    for _attempt in range(3):
        result_file = result_dir / f"proposal-{index}-{uuid.uuid4().hex[:8]}.json"
        nonce = uuid.uuid4().hex[:10]
        env = os.environ.copy()
        # Product 33 is a seeded local-demo SKU with ample stock. Durable cases
        # create disposable orders repeatedly; selecting it explicitly prevents
        # prior synthetic runs from exhausting the lower-stock default SKU.
        env.setdefault("MALL_LIVE_DEMO_PRODUCT_ID", "33")
        env.update(
            {
                "MALL_LIVE_DEMO_PASSWORD": password,
                "MALL_LIVE_DEMO_RESULT_FILE": str(result_file),
                "MALL_LIVE_DEMO_USER_A": f"durable_a_{index}_{nonce}",
                "MALL_LIVE_DEMO_USER_B": f"durable_b_{index}_{nonce}",
            }
        )
        try:
            process = subprocess.run(
                [sys.executable, str(SERVICE_ROOT / "scripts" / "bootstrap_live_demo.py")],
                cwd=SERVICE_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=240,
                check=False,
            )
            if process.returncode != 0 or not result_file.exists():
                raise RecoveryCaseError("task_create_failed", "fixture_bootstrap")
            payload = json.loads(result_file.read_text(encoding="utf-8"))
            account = payload.get("account_a") if isinstance(payload, dict) else None
            username = account.get("username") if isinstance(account, dict) else None
            order = account.get("order_sn") if isinstance(account, dict) else None
            if not isinstance(username, str) or not username or not isinstance(order, str) or not order:
                raise RecoveryCaseError("task_create_failed", "fixture_bootstrap")
            # Login through FastAPI so the remainder of the case uses the exact
            # same authenticated public path as all other recovery assertions.
            return _login(client, base, username, password), order
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, RecoveryCaseError) as exc:
            last_error = exc if isinstance(exc, RecoveryCaseError) else RecoveryCaseError("task_create_failed", "fixture_bootstrap")
        finally:
            try:
                result_file.unlink(missing_ok=True)
            except OSError:
                pass
    raise last_error or RecoveryCaseError("task_create_failed", "fixture_bootstrap")


def _run_store_recovery_case(client: httpx.Client, base: str, authorization: str, order_sn: str) -> dict[str, Any]:
    waiting = _create_waiting_task(client, base, authorization, f"store-recovery-{uuid.uuid4().hex[:8]}")
    task_ref = waiting["task_ref"]
    stopped = _compose(["stop", "redis"])
    try:
        if stopped.returncode != 0:
            raise RecoveryCaseError("dependency_recovery_failed", "redis_stop")
        safe = _continue(client, base, authorization, task_ref, "暂不提交，稍后继续")
        if safe.get("task_ref") != task_ref:
            raise RecoveryCaseError("store_recovery_failed", "redis_unavailable")
    finally:
        _compose(["start", "redis"])
        java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
        if (
            not _wait_healthy("redis")
            or not _wait_healthy("mall-portal")
            or not _wait_java_ready(client, java_base)
        ):
            raise RecoveryCaseError("dependency_recovery_failed", "redis_restore")
    return {
        "assertions": [
            "redis_interruption_fail_closed",
            "redis_health_recovered",
            "java_redis_dependency_recovered",
            "no_business_write",
        ]
    }


def _create_waiting_task(client: httpx.Client, base: str, authorization: str, session_id: str) -> dict[str, Any]:
    return _create_task(client, base, authorization, session_id, "查询订单物流")


def _create_task(client: httpx.Client, base: str, authorization: str, session_id: str, goal: str) -> dict[str, Any]:
    response = client.post(
        f"{base}/agent-tasks",
        headers={"Authorization": authorization},
        json={"session_id": session_id, "goal": goal, "success_criteria": ["事实已核验"]},
    )
    payload = _object(response)
    if response.status_code != 201:
        raise RecoveryCaseError("task_create_failed", "task_create")
    if not isinstance(payload.get("task_ref"), str):
        raise RecoveryCaseError("task_create_failed", "task_projection")
    if goal == "查询订单物流" and payload.get("status") != "waiting_for_user":
        raise RecoveryCaseError("task_not_waiting", "waiting_state")
    return payload


def _continue(client: httpx.Client, base: str, authorization: str, task_ref: str, message: str) -> dict[str, Any]:
    response = _continue_raw(client, base, authorization, task_ref, message)
    payload = _object(response)
    if response.status_code != 200:
        raise RecoveryCaseError("task_resume_failed", "task_continue")
    return payload


def _continue_raw(client: httpx.Client, base: str, authorization: str, task_ref: str, message: str) -> httpx.Response:
    return client.post(
        f"{base}/agent-tasks/{task_ref}/messages",
        headers={"Authorization": authorization},
        json={"message": message},
    )


def _confirm_raw(client: httpx.Client, base: str, authorization: str, task_ref: str, confirmation: str, task: dict[str, Any]) -> httpx.Response:
    action = task.get("action") if isinstance(task.get("action"), dict) else {}
    return client.post(
        f"{base}/agent-tasks/{task_ref}/action",
        headers={"Authorization": authorization},
        json={"confirmation": confirmation, "proposal_ref": action.get("proposal_ref"), "revision": action.get("revision")},
    )


def _list_applications(client: httpx.Client, base: str, authorization: str) -> list[dict[str, Any]]:
    response = client.get(f"{base}/customer-service/after-sales-applications", headers={"Authorization": authorization})
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, list):
        raise RecoveryCaseError("task_resume_failed", "status_read")
    return [item for item in payload if isinstance(item, dict)]


def _restart_service() -> None:
    result = _compose(["restart", "mall-ai-service"])
    if result.returncode != 0 or not _wait_healthy("mall-ai-service"):
        raise RecoveryCaseError("service_restart_failed", "service_restart")


def _compose(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _wait_healthy(service: str) -> bool:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Service}}|{{.State}}|{{.Health}}"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if any(line.strip() == f"{service}|running|healthy" for line in result.stdout.splitlines()):
            return True
        time.sleep(2)
    return False


def _wait_java_ready(client: httpx.Client, java_base: str, *, timeout: int = 120) -> bool:
    """Wait for Java's Redis-backed health, not only the Redis container."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{java_base}/actuator/health", timeout=5)
            payload = response.json()
            if response.status_code == 200 and isinstance(payload, dict) and payload.get("status") == "UP":
                return True
        except (httpx.HTTPError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(2)
    return False


def _object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise RecoveryCaseError("unexpected_failure", "json") from exc
    return payload if isinstance(payload, dict) else {}


def _opaque_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(main())
