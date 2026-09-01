"""Website-proxy smoke test for the final unified after-sales flow.

Use disposable local demo accounts and orders only. Credentials and Bearer
tokens are consumed from environment variables and are never printed or saved.
Callers may explicitly opt into a local synthetic-data bootstrap with
``MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO=true`` and a process-only
``MALL_LIVE_DEMO_PASSWORD``; otherwise all four fixture variables are required.
The script intentionally checks the public FastAPI projection through the Vue
website proxy rather than calling internal Java write endpoints directly.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
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
    "proposal_id",
    "idempotency_key",
    "request_fingerprint",
    "authorization",
    "token",
}


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveInputs:
    """Credentials and an order reference kept only in this verifier process."""

    user_a: str
    user_b: str
    password: str
    order_a: str


def main() -> int:
    inputs = _resolve_live_inputs()
    if inputs is None:
        return 2

    web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    api_base = web_base + "/api"

    try:
        with httpx.Client(timeout=45) as client:
            authorization_a = _login(client, api_base, inputs.user_a, inputs.password)
            authorization_b = _login(client, api_base, inputs.user_b, inputs.password)
            session_id = _create_conversation(client, api_base, authorization_a)

            policy = _message(
                client,
                api_base,
                authorization_a,
                session_id,
                "商品质量问题退货，运费由谁承担？",
            )
            _assert_public_response(policy)
            _expect("运费" in _require_text(policy.get("answer"), "policy answer"), "Policy smoke answer is missing")

            proposal: dict[str, Any] | None = None
            for message in (
                f"订单号：{inputs.order_a}，我要取消订单退款，原因是不想要了。",
                "我选择第一个商品，原因是不想要了，申请取消订单退款。",
                "我确认申请取消订单退款。",
            ):
                response = _message(client, api_base, authorization_a, session_id, message)
                _assert_public_response(response)
                value = response.get("after_sales_proposal")
                if isinstance(value, dict):
                    proposal = value
                    break
            _expect(proposal is not None, "Unified flow did not produce a customer confirmation proposal")

            submitted_response = _message(client, api_base, authorization_a, session_id, "确认")
            _assert_public_response(submitted_response)
            submitted = _require_dict(
                submitted_response.get("submitted_after_sales_application"),
                "submitted after-sales application",
            )
            application_id = submitted.get("application_id")
            _expect(isinstance(application_id, int) and application_id > 0, "Submission has no public application id")
            _expect(submitted.get("status") == "pending_review", "New application is not pending review")

            status_response = _message(
                client,
                api_base,
                authorization_a,
                session_id,
                f"查询售后申请 #{application_id} 的进度",
            )
            _assert_public_response(status_response)
            status_records = status_response.get("after_sales_applications")
            _expect(
                isinstance(status_records, list)
                and any(isinstance(item, dict) and item.get("application_id") == application_id for item in status_records),
                "Status query did not return the current member's application",
            )

            account_b_records = _list_applications(client, api_base, authorization_b)
            _expect(
                all(item.get("application_id") != application_id for item in account_b_records),
                "A second customer received another member's after-sales application",
            )

            pending_cancel = _message(
                client,
                api_base,
                authorization_a,
                session_id,
                f"取消售后申请 #{application_id}",
            )
            _assert_public_response(pending_cancel)
            pending_action = _require_dict(pending_cancel.get("after_sales_pending_action"), "pending cancel action")
            _expect(pending_action.get("action") == "cancel", "Cancellation did not require a server pending action")

            cancelled_response = _message(client, api_base, authorization_a, session_id, "确认")
            _assert_public_response(cancelled_response)
            _expect(
                cancelled_response.get("after_sales_completed_action") == "cancel",
                "Cancellation confirmation did not complete the pending action",
            )
            cancelled = _require_dict(
                cancelled_response.get("submitted_after_sales_application"),
                "cancelled after-sales application",
            )
            _expect(cancelled.get("application_id") == application_id, "Cancellation targeted a different application")
            _expect(cancelled.get("status") == "cancelled", "Application status was not updated to cancelled")
    except (httpx.HTTPError, VerificationError) as exc:
        print(f"Unified after-sales website-proxy verification failed: {exc}")
        return 1

    print("Unified after-sales website-proxy verification passed.")
    return 0


def _resolve_live_inputs() -> LiveInputs | None:
    required = (
        "MALL_UNIFIED_LIVE_USER_A",
        "MALL_UNIFIED_LIVE_USER_B",
        "MALL_UNIFIED_LIVE_PASSWORD",
        "MALL_UNIFIED_LIVE_ORDER_A",
    )
    values = {name: os.getenv(name) for name in required}
    if all(isinstance(value, str) and value.strip() for value in values.values()):
        return LiveInputs(
            user_a=values["MALL_UNIFIED_LIVE_USER_A"] or "",
            user_b=values["MALL_UNIFIED_LIVE_USER_B"] or "",
            password=values["MALL_UNIFIED_LIVE_PASSWORD"] or "",
            order_a=values["MALL_UNIFIED_LIVE_ORDER_A"] or "",
        )
    if os.getenv("MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO", "").strip().lower() != "true":
        print(
            "Missing unified-after-sales local fixture variables; or explicitly enable "
            "MALL_UNIFIED_BOOTSTRAP_LOCAL_DEMO=true."
        )
        return None
    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        print("Missing MALL_LIVE_DEMO_PASSWORD for explicit local unified-after-sales fixture bootstrap.")
        return None
    return _bootstrap_disposable_inputs(password)


def _bootstrap_disposable_inputs(password: str) -> LiveInputs:
    """Create disposable local customers and orders through Java public APIs only."""

    try:
        from bootstrap_live_demo import DemoAccount, LiveDemoSetupError, _prepare_account_order
    except ImportError as exc:  # pragma: no cover - script packaging error
        raise VerificationError("Unified after-sales local fixture helper is unavailable") from exc

    nonce = uuid.uuid4().hex[:12]
    phone_seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount("unified-A", f"unified_a_{nonce}", password, f"195{phone_seed:08d}"),
        DemoAccount("unified-B", f"unified_b_{nonce}", password, f"198{(phone_seed + 1) % 100_000_000:08d}"),
    )
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    try:
        with httpx.Client(timeout=45) as client:
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
        raise VerificationError("Unable to prepare local synthetic unified-after-sales fixtures") from exc
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
    _expect(isinstance(authorization, str) and authorization.startswith("Bearer "), "Login returned no Bearer credential")
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
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError("Customer after-sales list returned non-JSON") from exc
    _expect(isinstance(payload, list), "Customer after-sales list is not a list")
    records = [item for item in payload if isinstance(item, dict)]
    for record in records:
        _assert_no_internal_fields(record)
    return records


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
