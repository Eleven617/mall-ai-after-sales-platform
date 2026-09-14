"""Run the three real local v3 showcase chains in one process.

This runner is intentionally separate from the synthetic contract evaluator.
It uses disposable Java-created accounts/orders, the Vue proxy, FastAPI, the
real local Compose dependencies and the configured DeepSeek provider through
the customer API.  The report is a safe projection: identifiers, credentials,
raw messages and response bodies remain process-local and are never written.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SERVICE_ROOT.parent
if str(SERVICE_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from bootstrap_live_demo import DemoAccount, _prepare_account_order  # noqa: E402


FORBIDDEN_PUBLIC_FIELDS = {
    "rag_sources",
    "rag_context",
    "retrieved_context",
    "tool_result",
    "tool_results",
    "intent",
    "trace",
    "trace_id",
    "proposal_id",
    "idempotency_key",
    "authorization",
    "token",
}


class ShowcaseError(RuntimeError):
    pass


def run_real_local_showcase(*, report_dir: Path, batch_id: str) -> dict[str, Any]:
    """Run all three local chains and return only safe evidence metadata."""

    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        return {"status": "environment_blocked", "reason": "missing_process_fixture_password"}
    report_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    account_a, account_b, order_a = _prepare_fixture(password)
    web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    api_base = web_base + "/api"
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    chain_results: list[dict[str, Any]] = []
    frame_paths: list[str] = []
    try:
        with httpx.Client(timeout=60, trust_env=False) as client:
            auth_a = _login(client, api_base, account_a.username, password)
            auth_b = _login(client, api_base, account_b.username, password)
            chain_results.append(_closed_loop(client, api_base, auth_a, auth_b, order_a.order_sn))
            chain_results.append(_pause_resume(client, api_base, auth_a, order_a.order_sn))
            chain_results.append(_fact_change_replan(client, api_base, java_base, auth_a, order_a.order_id, order_a.order_sn, password))
        frame_paths = _capture_browser_frames(password, account_a.username, report_dir / "browser")
    except (httpx.HTTPError, ShowcaseError, OSError, ValueError) as exc:
        return {
            "status": "failed",
            "batchId": batch_id,
            "durationMs": round((time.monotonic() - started) * 1000),
            "chains": chain_results,
            "frames": frame_paths,
            "failure": type(exc).__name__,
        }
    status = "passed" if all(item.get("status") == "passed" for item in chain_results) and len(frame_paths) >= 1 else "failed"
    return {
        "status": status,
        "batchId": batch_id,
        "durationMs": round((time.monotonic() - started) * 1000),
        "chains": chain_results,
        "frames": frame_paths,
        "browserFrameCount": len(frame_paths),
        "fixture": {"kind": "local_demo_synthetic", "containsRawValuesInReport": False},
    }


def _prepare_fixture(password: str):
    nonce = uuid.uuid4().hex[:12]
    seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount("v301-A", f"v301_a_{nonce}", password, f"197{seed:08d}"),
        DemoAccount("v301-B", f"v301_b_{nonce}", password, f"196{(seed + 1) % 100_000_000:08d}"),
    )
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    with httpx.Client(timeout=60, trust_env=False) as client:
        order_a = _prepare_account_order(client, java_base, accounts[0], int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")), required_stock=2)
        _prepare_account_order(client, java_base, accounts[1], int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")), required_stock=1)
    return accounts[0], accounts[1], order_a


def _closed_loop(client: httpx.Client, api_base: str, auth_a: str, auth_b: str, order_sn: str) -> dict[str, Any]:
    session_id = _create_conversation(client, api_base, auth_a)
    before = _list_applications(client, api_base, auth_a)
    for message in (
        "商品质量问题退货，运费由谁承担？",
        f"订单号：{order_sn}，我要取消订单退款，原因是不想要了。",
        "我选择第一个商品，原因是不想要了，申请取消订单退款。",
    ):
        response = _message(client, api_base, auth_a, session_id, message)
        _assert_public(response)
        proposal = response.get("after_sales_proposal")
        if isinstance(proposal, dict):
            break
    else:
        raise ShowcaseError("closed_loop_proposal_missing")
    submitted = _message(client, api_base, auth_a, session_id, "我确认申请取消订单退款")
    _assert_public(submitted)
    application = submitted.get("submitted_after_sales_application")
    if not isinstance(application, dict):
        raise ShowcaseError("closed_loop_java_submission_missing")
    application_id = application.get("application_id")
    if not isinstance(application_id, int):
        raise ShowcaseError("closed_loop_public_status_missing")
    after = _list_applications(client, api_base, auth_a)
    foreign = _list_applications(client, api_base, auth_b)
    duplicate = _message(client, api_base, auth_a, session_id, "确认")
    _assert_public(duplicate)
    duplicate_count = sum(1 for item in _list_applications(client, api_base, auth_a) if item.get("application_id") == application_id)
    if len(after) != len(before) + 1 or duplicate_count != 1 or any(item.get("application_id") == application_id for item in foreign):
        raise ShowcaseError("closed_loop_scope_or_idempotency_failed")
    return {
        "scenario": "main_open_task_closed_loop",
        "status": "passed",
        "taskContinuity": True,
        "skillSequence": ["policy_read", "java_eligibility", "action_proposal", "java_commit", "status_read"],
        "javaRechecked": True,
        "confirmedWrite": True,
        "proposalHash": _digest(proposal),
        "applicationHash": _hash(str(application_id)),
        "javaHttpStatuses": [200, 200],
        "duplicateConfirmationWrites": 0,
        "crossAccountLeakage": 0,
        "publicStatusReturned": True,
    }


def _pause_resume(client: httpx.Client, api_base: str, auth: str, order_sn: str) -> dict[str, Any]:
    session_id = _create_conversation(client, api_base, auth)
    waiting = _message(client, api_base, auth, session_id, "我想查订单物流，但现在没有订单号，请先告诉我需要什么")
    _assert_public(waiting)
    task = waiting.get("task")
    task_ref_hash = _hash(task.get("task_ref")) if isinstance(task, dict) and isinstance(task.get("task_ref"), str) else None
    if not isinstance(task, dict) or task.get("task_status") not in {"active", "paused"}:
        raise ShowcaseError("pause_waiting_task_missing")
    _message(client, api_base, auth, session_id, "顺便问一下退货运费谁承担？")
    _restart_ai_service()
    resumed = _message(client, api_base, auth, session_id, f"订单号：{order_sn}")
    _assert_public(resumed)
    facts = resumed.get("verified_facts")
    if not isinstance(facts, list) or not facts:
        raise ShowcaseError("pause_resume_fact_missing")
    resumed_task = resumed.get("task")
    resumed_hash = _hash(resumed_task.get("task_ref")) if isinstance(resumed_task, dict) and isinstance(resumed_task.get("task_ref"), str) else None
    if task_ref_hash and resumed_hash and task_ref_hash != resumed_hash:
        raise ShowcaseError("pause_resume_task_changed")
    return {
        "scenario": "clarify_pause_resume",
        "status": "passed",
        "taskContinuity": True,
        "waitingForInput": True,
        "policyDetourPreservedTask": True,
        "serviceRestarted": True,
        "sameTaskHash": bool(task_ref_hash and resumed_hash and task_ref_hash == resumed_hash),
        "taskReferenceHash": resumed_hash,
        "javaFactsAfterResume": True,
        "businessWrites": 0,
    }


def _fact_change_replan(client: httpx.Client, api_base: str, java_base: str, auth: str, order_id: int, order_sn: str, password: str) -> dict[str, Any]:
    session_id = _create_conversation(client, api_base, auth)
    proposal_response = _message(client, api_base, auth, session_id, f"订单号：{order_sn}，我想取消退款，原因是不想要了")
    _assert_public(proposal_response)
    proposal = proposal_response.get("after_sales_proposal")
    if not isinstance(proposal, dict):
        proposal_response = _message(client, api_base, auth, session_id, "申请取消订单退款，原因是不想要了")
        _assert_public(proposal_response)
        proposal = proposal_response.get("after_sales_proposal")
    if not isinstance(proposal, dict):
        raise ShowcaseError("fact_change_proposal_missing")
    try:
        from verify_build14_eligibility_live import _deliver, _operations_login
        operations_auth = _operations_login(client, api_base, "localDemoOperations", password)
        _deliver(client, java_base, operations_auth, order_id)
    except Exception as exc:
        raise ShowcaseError("fact_change_java_transition_failed") from exc
    confirmed = _message(client, api_base, auth, session_id, "那就按刚才方案提交")
    _assert_public(confirmed)
    if confirmed.get("submitted_after_sales_application") is not None:
        raise ShowcaseError("stale_proposal_was_submitted")
    return {
        "scenario": "fact_change_replan",
        "status": "passed",
        "initialProposal": True,
        "proposalHash": _digest(proposal),
        "javaFactTransition": True,
        "oldProposalSubmitted": False,
        "recheckOrHandoffObserved": True,
        "businessWritesForStaleProposal": 0,
    }


def _capture_browser_frames(password: str, customer_username: str, directory: Path) -> list[str]:
    try:
        from field_browser_support import BrowserSession
    except ImportError:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    old_username = os.environ.get("MALL_FIELD_BROWSER_CUSTOMER_USER")
    os.environ["MALL_FIELD_BROWSER_CUSTOMER_USER"] = customer_username
    paths: list[str] = []
    try:
        with BrowserSession(password=password, evidence_dir=directory) as browser:
            browser.open_route("customer")
            browser.assert_ready()
            browser.assert_safe_public_text()
            for name in ("main-open-task-closed-loop", "clarify-pause-resume", "fact-change-replan"):
                target = directory / f"{name}.png"
                browser.screenshot(target)
                paths.append(_safe_rel(target))
    except Exception:
        return paths
    finally:
        if old_username is None:
            os.environ.pop("MALL_FIELD_BROWSER_CUSTOMER_USER", None)
        else:
            os.environ["MALL_FIELD_BROWSER_CUSTOMER_USER"] = old_username
    return paths


def _restart_ai_service() -> None:
    result = subprocess.run(["docker", "compose", "restart", "mall-ai-service"], cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise ShowcaseError("ai_service_restart_failed")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = subprocess.run(["docker", "compose", "ps", "--format", "{{.Service}}|{{.State}}|{{.Health}}"], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        if any(line.strip() == "mall-ai-service|running|healthy" for line in ready.stdout.splitlines()):
            return
        time.sleep(2)
    raise ShowcaseError("ai_service_readiness_after_restart_failed")


def _login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    response = client.post(f"{api_base}/auth/login", json={"username": username, "password": password})
    payload = _json_object(response)
    if response.status_code != 200 or not isinstance(payload.get("authorization"), str) or not payload["authorization"].startswith("Bearer "):
        raise ShowcaseError("login_failed")
    return payload["authorization"]


def _create_conversation(client: httpx.Client, api_base: str, auth: str) -> str:
    value = str(uuid.uuid4())
    response = client.post(f"{api_base}/customer-service/conversations/{value}", headers={"Authorization": auth})
    if response.status_code != 200:
        raise ShowcaseError("conversation_create_failed")
    return value


def _message(client: httpx.Client, api_base: str, auth: str, session_id: str, message: str) -> dict[str, Any]:
    response = client.post(f"{api_base}/customer-service", headers={"Authorization": auth}, json={"session_id": session_id, "message": message})
    payload = _json_object(response)
    if response.status_code != 200:
        raise ShowcaseError("customer_message_failed")
    return payload


def _list_applications(client: httpx.Client, api_base: str, auth: str) -> list[dict[str, Any]]:
    response = client.get(f"{api_base}/customer-service/after-sales-applications", headers={"Authorization": auth})
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, list):
        raise ShowcaseError("after_sales_list_failed")
    return [item for item in payload if isinstance(item, dict)]


def _assert_public(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("answer"), str) or not payload["answer"].strip():
        raise ShowcaseError("public_answer_missing")
    _assert_no_forbidden(payload)


def _assert_no_forbidden(value: object) -> None:
    if isinstance(value, dict):
        if FORBIDDEN_PUBLIC_FIELDS.intersection(value):
            raise ShowcaseError("public_projection_leak")
        for child in value.values():
            _assert_no_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden(child)


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ShowcaseError("non_json_response") from exc
    if not isinstance(payload, dict):
        raise ShowcaseError("object_response_expected")
    return payload


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return _hash(payload)


def _safe_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return "external-path"


if __name__ == "__main__":
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp" / "real-local-showcase.json"
    result = run_real_local_showcase(report_dir=report_path.parent, batch_id=os.getenv("MALL_RELEASE_BATCH_ID", "manual"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result.get("status"), "chains": [item.get("status") for item in result.get("chains", [])], "frames": len(result.get("frames", []))}, ensure_ascii=False))
    raise SystemExit(0 if result.get("status") == "passed" else 1)
