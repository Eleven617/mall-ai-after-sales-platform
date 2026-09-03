"""Authenticated website-proxy verification for Build 21 durable diagnosis.

This script intentionally consumes disposable local-demo credentials from the
process environment.  It never prints or persists credentials, Bearer tokens,
or customer-visible order numbers.  It verifies the real Vue proxy -> FastAPI
-> Java/Redis path, including a restart of only ``mall-ai-service``.

By default the caller supplies the four ``MALL_BUILD21_LIVE_*`` variables.  A
local maintainer may instead explicitly set ``MALL_BUILD21_BOOTSTRAP_LOCAL_DEMO
=true`` together with an ephemeral ``MALL_LIVE_DEMO_PASSWORD``.  Only in that
opt-in mode does the verifier create disposable local A/B accounts and paid
orders in memory before it starts the read-only test; it never prints their
credentials or order references.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


FORBIDDEN_PUBLIC_FIELDS = {
    "rag_sources",
    "rag_context",
    "retrieved_context",
    "tool_result",
    "tool_results",
    "intent",
    "trace",
    "trace_id",
    "thread_id",
    "checkpoint",
    "resume_ref",
    "proposal_id",
    "idempotency_key",
    "request_fingerprint",
    "authorization",
    "token",
}


class VerificationError(RuntimeError):
    pass


class LiveInputs:
    """Private in-memory credentials and references for one local verifier run."""

    def __init__(self, *, user_a: str, user_b: str, password: str, order_a: str) -> None:
        self.user_a = user_a
        self.user_b = user_b
        self.password = password
        self.order_a = order_a


def main() -> int:
    inputs = _resolve_live_inputs()
    if inputs is None:
        return 2

    web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    api_base = web_base + "/api"

    try:
        with httpx.Client(timeout=45, trust_env=False) as client:
            authorization_a = _login(
                client, api_base, inputs.user_a, inputs.password
            )
            authorization_b = _login(
                client, api_base, inputs.user_b, inputs.password
            )
            # Local named volumes deliberately persist across verification runs.
            # A valid re-run therefore must compare each owner's baseline rather
            # than incorrectly assuming that a synthetic account has never used
            # the after-sales flow before.
            before_a = _list_applications(client, api_base, authorization_a)
            before_b = _list_applications(client, api_base, authorization_b)

            conversation_id = _create_conversation(client, api_base, authorization_a)
            paused = _message(
                client,
                api_base,
                authorization_a,
                conversation_id,
                # This is the documented multi-step diagnosis boundary: it
                # asks for cause, delivery exception and the next safe step,
                # rather than a single logistics lookup.
                "订单为什么未按预期完成、是否存在配送异常、我现在应如何处理？",
            )
            _assert_public_response(paused)
            pending = _require_dict(paused.get("pending_action"), "durable pending action")
            _expect(pending.get("kind") == "awaiting_order_sn", "Diagnosis did not wait for an order number")
            _expect(pending.get("resumable") is True, "Diagnosis was not persisted as a resumable read-only task")
            _expect(not paused.get("verified_facts"), "Interrupt unexpectedly queried business data")
            _assert_no_business_write_fields(paused)

            _restart_ai_service()
            _wait_for_proxy_readiness(client, web_base)

            resumed = _message(
                client, api_base, authorization_a, conversation_id, f"订单号：{inputs.order_a}"
            )
            _assert_public_response(resumed)
            _expect(
                isinstance(resumed.get("verified_facts"), list) and bool(resumed["verified_facts"]),
                "Authenticated resume did not return Java-derived fact cards",
            )
            _expect(isinstance(resumed.get("diagnosis"), dict), "Authenticated resume did not return diagnosis state")
            _expect(
                resumed.get("pending_action") is None,
                "Authenticated resume unexpectedly remained in a pending diagnostic state",
            )
            _assert_no_business_write_fields(resumed)

            duplicate = _message(
                client, api_base, authorization_a, conversation_id, f"订单号：{inputs.order_a}"
            )
            _assert_public_response(duplicate)
            _expect(
                "未重复执行查询" in _require_text(duplicate.get("answer"), "duplicate resume answer"),
                "Duplicate resume was not safely recognized as completed",
            )
            _assert_no_business_write_fields(duplicate)

            foreign = client.post(
                f"{api_base}/customer-service",
                headers={"Authorization": authorization_b},
                json={"session_id": conversation_id, "message": "继续查询"},
            )
            _expect(
                foreign.status_code in {403, 404},
                "A different member was not rejected before accessing the owner conversation",
            )
            _assert_foreign_error_has_no_private_payload(foreign)

            after_a = _list_applications(client, api_base, authorization_a)
            after_b = _list_applications(client, api_base, authorization_b)
            _expect(after_a == before_a and after_b == before_b, "Read-only diagnosis changed after-sales records")
    except (httpx.HTTPError, VerificationError) as exc:
        print(f"Build 21 authenticated website-proxy verification failed: {exc}")
        return 1

    print("Build 21 authenticated website-proxy verification passed.")
    return 0


def _resolve_live_inputs() -> LiveInputs | None:
    required = (
        "MALL_BUILD21_LIVE_USER_A",
        "MALL_BUILD21_LIVE_USER_B",
        "MALL_BUILD21_LIVE_PASSWORD",
        "MALL_BUILD21_LIVE_ORDER_A",
    )
    values = {name: os.getenv(name) for name in required}
    if all(isinstance(value, str) and value.strip() for value in values.values()):
        return LiveInputs(
            user_a=values["MALL_BUILD21_LIVE_USER_A"] or "",
            user_b=values["MALL_BUILD21_LIVE_USER_B"] or "",
            password=values["MALL_BUILD21_LIVE_PASSWORD"] or "",
            order_a=values["MALL_BUILD21_LIVE_ORDER_A"] or "",
        )

    if os.getenv("MALL_BUILD21_BOOTSTRAP_LOCAL_DEMO", "").strip().lower() != "true":
        missing = [name for name, value in values.items() if not value]
        print(
            "Missing local verification variables: "
            + ", ".join(missing)
            + "; or explicitly enable MALL_BUILD21_BOOTSTRAP_LOCAL_DEMO=true."
        )
        return None

    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        print("Missing MALL_LIVE_DEMO_PASSWORD for explicit local synthetic-data bootstrap.")
        return None
    return _bootstrap_disposable_inputs(password)


def _bootstrap_disposable_inputs(password: str) -> LiveInputs:
    """Prepare an isolated local fixture without logging identifiers or secrets.

    The established bootstrap helper only uses Java public APIs.  This verifier
    keeps its returned account/order data in request memory, which lets a real
    browser-proxy check run even after prior demo data exists in named volumes.
    """

    try:
        from bootstrap_live_demo import DemoAccount, LiveDemoSetupError, _prepare_account_order
    except ImportError as exc:  # pragma: no cover - execution packaging error
        raise VerificationError("Build 21 local fixture helper is unavailable") from exc

    nonce = uuid.uuid4().hex[:12]
    phone_seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount(
            label="build21-A",
            username=f"build21_a_{nonce}",
            password=password,
            telephone=f"199{phone_seed:08d}",
        ),
        DemoAccount(
            label="build21-B",
            username=f"build21_b_{nonce}",
            password=password,
            telephone=f"198{(phone_seed + 1) % 100_000_000:08d}",
        ),
    )
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    try:
        with httpx.Client(timeout=45, trust_env=False) as client:
            order_a = _prepare_account_order(
                client,
                java_base,
                accounts[0],
                int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")),
                required_stock=2,
            )
            _prepare_account_order(
                client,
                java_base,
                accounts[1],
                int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")),
                required_stock=1,
            )
    except (httpx.HTTPError, LiveDemoSetupError, ValueError) as exc:
        raise VerificationError("Unable to prepare local synthetic Build 21 fixtures") from exc

    return LiveInputs(
        user_a=accounts[0].username,
        user_b=accounts[1].username,
        password=password,
        order_a=order_a.order_sn,
    )


def _login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    response = client.post(f"{api_base}/auth/login", json={"username": username, "password": password})
    _expect(response.status_code == 200, "Customer login did not return HTTP 200")
    payload = _json_object(response, "customer login")
    authorization = payload.get("authorization")
    _expect(
        isinstance(authorization, str) and authorization.startswith("Bearer "),
        "Login returned no Bearer credential",
    )
    return authorization


def _create_conversation(client: httpx.Client, api_base: str, authorization: str) -> str:
    conversation_id = str(uuid.uuid4())
    response = client.post(
        f"{api_base}/customer-service/conversations/{conversation_id}",
        headers={"Authorization": authorization},
    )
    _expect(response.status_code == 200, "Customer conversation creation did not return HTTP 200")
    payload = _json_object(response, "customer conversation creation")
    _expect(payload.get("conversation_id") == conversation_id, "Conversation creation returned an unexpected id")
    return conversation_id


def _message(
    client: httpx.Client,
    api_base: str,
    authorization: str,
    session_id: str,
    message: str,
) -> dict[str, Any]:
    response = client.post(
        f"{api_base}/customer-service",
        headers={"Authorization": authorization},
        json={"session_id": session_id, "message": message},
    )
    _expect(response.status_code == 200, f"Customer message returned HTTP {response.status_code}")
    return _json_object(response, "customer-service response")


def _list_applications(client: httpx.Client, api_base: str, authorization: str) -> list[dict[str, Any]]:
    response = client.get(
        f"{api_base}/customer-service/after-sales-applications",
        headers={"Authorization": authorization},
    )
    _expect(response.status_code == 200, "Customer after-sales list did not return HTTP 200")
    payload = response.json()
    _expect(isinstance(payload, list), "Customer after-sales list is not a list")
    records = [item for item in payload if isinstance(item, dict)]
    for record in records:
        _assert_no_internal_fields(record)
    return records


def _restart_ai_service() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    compose_file = repo_root / "docker-compose.yml"
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "restart", "mall-ai-service"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    _expect(result.returncode == 0, "mall-ai-service restart did not complete")


def _wait_for_proxy_readiness(client: httpx.Client, web_base: str) -> None:
    """Wait for the restarted service's durable Redis dependency, not liveness.

    ``/health`` proves only that the FastAPI process has bound its socket.  A
    Build 21 continuation needs the Redis-backed checkpoint store after a
    restart, so this verifier requires two consecutive ready responses from the
    same Vue proxy path before sending the resume message.
    """

    deadline = time.monotonic() + 90
    consecutive_ready = 0
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{web_base}/api/health/ready", timeout=5)
            if response.status_code == 200 and response.json() == {
                "status": "ok",
                "conversation_store": "redis",
            }:
                consecutive_ready += 1
                if consecutive_ready >= 2:
                    return
            else:
                consecutive_ready = 0
        except httpx.HTTPError:
            consecutive_ready = 0
        time.sleep(1)
    raise VerificationError("Vue website proxy did not become Redis-ready after the AI service restart")


def _assert_public_response(payload: dict[str, Any]) -> None:
    _require_text(payload.get("answer"), "customer answer")
    _assert_no_internal_fields(payload)


def _assert_no_internal_fields(value: object) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_PUBLIC_FIELDS.intersection(value)
        _expect(not forbidden, "Public response leaked internal fields: " + ", ".join(sorted(forbidden)))
        for nested in value.values():
            _assert_no_internal_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_internal_fields(nested)


def _assert_no_business_write_fields(payload: dict[str, Any]) -> None:
    forbidden = {
        "after_sales_draft",
        "after_sales_proposal",
        "submitted_after_sales_application",
        "after_sales_completed_action",
        "after_sales_pending_action",
    }
    _expect(
        not any(payload.get(key) is not None for key in forbidden),
        "Read-only diagnosis returned a business write workflow field",
    )


def _assert_foreign_error_has_no_private_payload(response: httpx.Response) -> None:
    body = response.text.lower()
    forbidden_markers = ("verified_facts", "diagnosis", "order_sn", "rag_context", "tool_result")
    _expect(
        not any(marker in body for marker in forbidden_markers),
        "Foreign-member rejection exposed a private response payload",
    )


def _json_object(response: httpx.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError(f"{label} returned non-JSON") from exc
    return _require_dict(payload, label)


def _require_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerificationError(f"{label} is missing or malformed")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(f"{label} is missing or malformed")
    return value


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


if __name__ == "__main__":
    sys.exit(main())
