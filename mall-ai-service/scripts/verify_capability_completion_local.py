"""Verify the v3.0.3 proposal-revision and human-handoff paths locally.

This is a one-shot local acceptance runner, deliberately distinct from unit
tests and from the broader field-acceptance manifest.  It sends requests only
through the Vue/Nginx proxy, creates disposable synthetic Java fixtures, and
uses the deterministic Runtime provider.  The JSON report is a safe summary:
it deliberately excludes credentials, task/proposal/case identifiers, order
identifiers, request bodies, traces and provider content.

The runner requires a process-only ``MALL_FIELD_FIXTURE_PASSWORD`` (or
``MALL_LIVE_DEMO_PASSWORD``).  It never writes that value to a report or
configuration file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SERVICE_ROOT.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
if str(SERVICE_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from bootstrap_live_demo import DemoAccount, _prepare_account_order  # noqa: E402


class CapabilityVerificationError(RuntimeError):
    """A bounded failure which never captures an HTTP response body."""

    def __init__(self, code: str, *, stage: str) -> None:
        self.code = code
        self.stage = stage
        super().__init__(code)


_ALLOWED_HTTP_STATUSES = {200, 201, 404, 409}


def run_local_capability_completion(*, report_path: Path) -> dict[str, Any]:
    """Run both confirmation contracts and return a privacy-safe report."""

    password = os.getenv("MALL_FIELD_FIXTURE_PASSWORD") or os.getenv("MALL_LIVE_DEMO_PASSWORD")
    web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    started = time.monotonic()
    report: dict[str, Any] = {
        "schemaVersion": "v3.0.3-capability-local.v1",
        "executionMode": "local_nginx_fastapi_java_deterministic",
        "proxyBase": "http://127.0.0.1:5173/api",
        "fixture": {"kind": "disposable_local_synthetic", "rawValuesPersisted": False},
        "externalProviderRequests": 0,
        "draftAmendment": {"status": "not_run"},
        "humanHandoff": {"status": "not_run"},
    }
    if not password:
        report.update({"status": "environment_blocked", "reason": "missing_process_fixture_password"})
        return report
    if web_base != "http://127.0.0.1:5173":
        report.update({"status": "environment_blocked", "reason": "proxy_base_not_local_nginx"})
        return report

    try:
        account_a, account_b, order_a = _prepare_fixture(password)
        api_base = f"{web_base}/api"
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0, write=10.0, pool=10.0), trust_env=False) as client:
            auth_a = _login(client, api_base, account_a.username, password)
            auth_b = _login(client, api_base, account_b.username, password)
            report["draftAmendment"] = _verify_draft_amendment(client, api_base, auth_a, order_a.order_sn)
            report["humanHandoff"] = _verify_human_handoff(client, api_base, auth_a, auth_b, order_a.order_sn)
        if report["draftAmendment"]["status"] != "passed" or report["humanHandoff"]["status"] != "passed":
            raise CapabilityVerificationError("scenario_assertion_failed", stage="summary")
        report["status"] = "passed"
    except CapabilityVerificationError as exc:
        report.update({"status": "failed", "failureCode": exc.code, "stage": exc.stage})
    except (httpx.HTTPError, OSError, ValueError):
        report.update({"status": "failed", "failureCode": "local_dependency_unavailable", "stage": "local_http"})
    finally:
        report["durationMs"] = round((time.monotonic() - started) * 1000)
    return report


def _prepare_fixture(password: str) -> tuple[DemoAccount, DemoAccount, Any]:
    """Create two owner-isolated, process-local accounts and one paid order."""

    nonce = uuid.uuid4().hex[:12]
    seed = uuid.uuid4().int % 100_000_000
    account_a = DemoAccount("v303-A", f"v303_a_{nonce}", password, f"195{seed:08d}")
    account_b = DemoAccount("v303-B", f"v303_b_{nonce}", password, f"194{(seed + 1) % 100_000_000:08d}")
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    product_id = int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26"))
    with httpx.Client(timeout=60.0, trust_env=False) as client:
        order_a = _prepare_account_order(client, java_base, account_a, product_id, required_stock=2)
        _prepare_account_order(client, java_base, account_b, product_id, required_stock=1)
    return account_a, account_b, order_a


def _verify_draft_amendment(client: httpx.Client, api_base: str, authorization: str, order_sn: str) -> dict[str, Any]:
    before = _list_json(client, f"{api_base}/customer-service/after-sales-applications", authorization, "draft_before_list")
    task = _create_task(client, api_base, authorization, f"订单号：{order_sn}，申请售后草案")
    action = _require_action(task, "draft_initial_proposal")
    initial_ref, initial_revision = _proposal_coordinates(action, "draft_initial_proposal")

    revision_two = _amend_task(client, api_base, authorization, _task_ref(task), initial_ref, initial_revision, "exchange")
    action_two = _require_action(revision_two, "draft_revision_two")
    revision_two_ref, revision_two_number = _proposal_coordinates(action_two, "draft_revision_two")
    if revision_two_number != initial_revision + 1 or revision_two_ref == initial_ref or action_two.get("application_type") != "exchange":
        raise CapabilityVerificationError("proposal_revision_not_created", stage="draft_amendment")
    if len(_list_json(client, f"{api_base}/customer-service/after-sales-applications", authorization, "draft_after_amend_list")) != len(before):
        raise CapabilityVerificationError("amendment_caused_java_write", stage="draft_amendment")

    stale = _confirm_raw(client, api_base, authorization, _task_ref(task), initial_ref, initial_revision)
    if stale.status_code != 409:
        raise CapabilityVerificationError("stale_confirmation_not_rejected", stage="draft_stale_confirmation")
    if len(_list_json(client, f"{api_base}/customer-service/after-sales-applications", authorization, "draft_after_stale_list")) != len(before):
        raise CapabilityVerificationError("stale_confirmation_caused_java_write", stage="draft_stale_confirmation")

    revision_three = _amend_task(
        client, api_base, authorization, _task_ref(task), revision_two_ref, revision_two_number, "cancel_refund"
    )
    action_three = _require_action(revision_three, "draft_revision_three")
    proposal_ref, revision = _proposal_coordinates(action_three, "draft_revision_three")
    if revision != revision_two_number + 1 or action_three.get("application_type") != "cancel_refund":
        raise CapabilityVerificationError("current_revision_not_created", stage="draft_amendment")

    committed = _confirm(client, api_base, authorization, _task_ref(task), proposal_ref, revision)
    if committed.get("status") not in {"executing", "completed"}:
        raise CapabilityVerificationError("current_revision_not_committed", stage="draft_confirmation")
    after = _list_json(client, f"{api_base}/customer-service/after-sales-applications", authorization, "draft_after_commit_list")
    if len(after) != len(before) + 1:
        raise CapabilityVerificationError("current_revision_java_write_missing", stage="draft_confirmation")
    duplicate = _confirm_raw(client, api_base, authorization, _task_ref(task), proposal_ref, revision)
    duplicate_after = _list_json(client, f"{api_base}/customer-service/after-sales-applications", authorization, "draft_after_duplicate_list")
    if duplicate.status_code not in {404, 409} or len(duplicate_after) != len(after):
        raise CapabilityVerificationError("draft_duplicate_not_idempotent", stage="draft_idempotency")
    return {
        "status": "passed",
        "proposalRevisionsObserved": 3,
        "staleConfirmationHttpStatus": 409,
        "amendmentJavaWrites": 0,
        "currentRevisionJavaWrites": 1,
        "duplicateConfirmationJavaWrites": 0,
    }


def _verify_human_handoff(
    client: httpx.Client,
    api_base: str,
    authorization_a: str,
    authorization_b: str,
    order_sn: str,
) -> dict[str, Any]:
    before = _list_json(client, f"{api_base}/customer-service/service-cases", authorization_a, "handoff_before_list")
    task = _create_task(client, api_base, authorization_a, f"订单号：{order_sn}，需要人工复核")
    action = _require_action(task, "human_proposal")
    if action.get("action_skill") != "open_human_case":
        raise CapabilityVerificationError("human_handoff_proposal_missing", stage="human_proposal")
    if len(_list_json(client, f"{api_base}/customer-service/service-cases", authorization_a, "handoff_pre_confirm_list")) != len(before):
        raise CapabilityVerificationError("human_case_created_before_confirmation", stage="human_proposal")
    proposal_ref, revision = _proposal_coordinates(action, "human_proposal")
    foreign = _confirm_raw(client, api_base, authorization_b, _task_ref(task), proposal_ref, revision)
    if foreign.status_code != 404:
        raise CapabilityVerificationError("cross_account_handoff_confirmation_allowed", stage="human_scope")
    committed = _confirm(client, api_base, authorization_a, _task_ref(task), proposal_ref, revision)
    if committed.get("status") not in {"executing", "completed"}:
        raise CapabilityVerificationError("human_handoff_not_committed", stage="human_confirmation")
    after = _list_json(client, f"{api_base}/customer-service/service-cases", authorization_a, "handoff_after_commit_list")
    if len(after) != len(before) + 1:
        raise CapabilityVerificationError("human_case_java_write_missing", stage="human_confirmation")
    duplicate = _confirm_raw(client, api_base, authorization_a, _task_ref(task), proposal_ref, revision)
    duplicate_after = _list_json(client, f"{api_base}/customer-service/service-cases", authorization_a, "handoff_after_duplicate_list")
    if duplicate.status_code not in {404, 409} or len(duplicate_after) != len(after):
        raise CapabilityVerificationError("human_handoff_duplicate_not_idempotent", stage="human_idempotency")
    return {
        "status": "passed",
        "proposalJavaWritesBeforeConfirmation": 0,
        "currentConfirmationJavaWrites": 1,
        "duplicateConfirmationJavaWrites": 0,
        "crossAccountConfirmationHttpStatus": 404,
    }


def _login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    response = client.post(f"{api_base}/auth/login", json={"username": username, "password": password})
    payload = _json_object(response, "login")
    authorization = payload.get("authorization")
    if response.status_code != 200 or not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise CapabilityVerificationError("synthetic_customer_login_failed", stage="login")
    return authorization


def _create_task(client: httpx.Client, api_base: str, authorization: str, goal: str) -> dict[str, Any]:
    response = client.post(
        f"{api_base}/agent-tasks",
        headers={"Authorization": authorization},
        json={"session_id": str(uuid.uuid4()), "goal": goal, "success_criteria": ["事实已核验"]},
    )
    payload = _json_object(response, "task_create")
    if response.status_code != 201 or payload.get("status") != "ready_to_commit":
        raise CapabilityVerificationError("agent_task_proposal_not_ready", stage="task_create")
    _assert_public_task(payload)
    return payload


def _amend_task(
    client: httpx.Client,
    api_base: str,
    authorization: str,
    task_ref: str,
    proposal_ref: str,
    revision: int,
    application_type: str,
) -> dict[str, Any]:
    response = client.patch(
        f"{api_base}/agent-tasks/{task_ref}/action",
        headers={"Authorization": authorization},
        json={"proposal_ref": proposal_ref, "revision": revision, "application_type": application_type},
    )
    payload = _json_object(response, "task_amend")
    if response.status_code != 200 or payload.get("status") != "ready_to_commit":
        raise CapabilityVerificationError("agent_task_amend_failed", stage="draft_amendment")
    _assert_public_task(payload)
    return payload


def _confirm(client: httpx.Client, api_base: str, authorization: str, task_ref: str, proposal_ref: str, revision: int) -> dict[str, Any]:
    response = _confirm_raw(client, api_base, authorization, task_ref, proposal_ref, revision)
    payload = _json_object(response, "task_confirm")
    if response.status_code != 200:
        raise CapabilityVerificationError("agent_task_confirm_failed", stage="confirmation")
    _assert_public_task(payload)
    return payload


def _confirm_raw(
    client: httpx.Client,
    api_base: str,
    authorization: str,
    task_ref: str,
    proposal_ref: str,
    revision: int,
) -> httpx.Response:
    return client.post(
        f"{api_base}/agent-tasks/{task_ref}/action",
        headers={"Authorization": authorization},
        json={"confirmation": "confirm", "proposal_ref": proposal_ref, "revision": revision},
    )


def _list_json(client: httpx.Client, url: str, authorization: str, stage: str) -> list[dict[str, Any]]:
    response = client.get(url, headers={"Authorization": authorization})
    if response.status_code != 200:
        raise CapabilityVerificationError("java_readback_failed", stage=stage)
    try:
        payload = response.json()
    except ValueError as exc:
        raise CapabilityVerificationError("java_readback_not_json", stage=stage) from exc
    if not isinstance(payload, list):
        raise CapabilityVerificationError("java_readback_shape_invalid", stage=stage)
    return [item for item in payload if isinstance(item, dict)]


def _require_action(task: dict[str, Any], stage: str) -> dict[str, Any]:
    action = task.get("action")
    if not isinstance(action, dict):
        raise CapabilityVerificationError("action_proposal_missing", stage=stage)
    return action


def _proposal_coordinates(action: dict[str, Any], stage: str) -> tuple[str, int]:
    proposal_ref = action.get("proposal_ref")
    revision = action.get("revision")
    if not isinstance(proposal_ref, str) or not isinstance(revision, int) or revision < 1:
        raise CapabilityVerificationError("action_proposal_coordinates_invalid", stage=stage)
    return proposal_ref, revision


def _task_ref(task: dict[str, Any]) -> str:
    reference = task.get("task_ref")
    if not isinstance(reference, str):
        raise CapabilityVerificationError("public_task_reference_missing", stage="public_projection")
    return reference


def _json_object(response: httpx.Response, stage: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise CapabilityVerificationError("response_not_json", stage=stage) from exc
    if not isinstance(payload, dict):
        raise CapabilityVerificationError("response_shape_invalid", stage=stage)
    return payload


def _assert_public_task(task: dict[str, Any]) -> None:
    forbidden = {"authorization", "token", "password", "trace", "order_sn", "orderSn", "proposal_id", "idempotency_key"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden.intersection(value):
                raise CapabilityVerificationError("public_projection_leak", stage="public_projection")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(task)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "tmp" / "v3.0.3-capability-completion-local.json")
    args = parser.parse_args()
    report = run_local_capability_completion(report_path=args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report.get("status"), "durationMs": report.get("durationMs")}, ensure_ascii=False))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
