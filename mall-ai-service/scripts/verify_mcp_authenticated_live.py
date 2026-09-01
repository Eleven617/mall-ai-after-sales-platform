"""Authenticated website-proxy verification for the read-only MCP gateway.

This is a local Demo/CI-maintainer harness, not an MCP client library.  It
talks to the Vue Nginx proxy and proves that a customer MCP session is bound to
the Java-verified caller, exposes only the customer read catalog, and cannot
be reused by a different member.  It never prints passwords, credentials,
order references, session IDs or MCP tool payloads.

Supply ``MALL_MCP_LIVE_USER_A``, ``MALL_MCP_LIVE_USER_B``,
``MALL_MCP_LIVE_PASSWORD`` and ``MALL_MCP_LIVE_ORDER_A`` for an existing local
fixture.  Alternatively, set ``MALL_MCP_BOOTSTRAP_LOCAL_DEMO=true`` together
with a temporary ``MALL_LIVE_DEMO_PASSWORD``.  The opt-in path creates only
local synthetic accounts/orders through Java's public demo APIs.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SESSION_HEADER = "Mcp-Session-Id"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
}
CUSTOMER_TOOLS = {
    "get_order_summary",
    "get_logistics_status",
    "get_after_sales_status",
    "check_after_sales_readiness",
    "search_after_sales_policy",
}
FORBIDDEN_RESULT_FIELDS = {
    "authorization",
    "token",
    "memberid",
    "operatorid",
    "ragcontext",
    "toolresult",
    "trace",
    "outbox",
    "sql",
    "path",
    "url",
}


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveInputs:
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
    mcp_url = api_base + "/mcp"
    try:
        with httpx.Client(timeout=45) as client:
            anonymous = client.post(
                mcp_url,
                headers=MCP_HEADERS,
                json={"jsonrpc": "2.0", "id": "anonymous", "method": "tools/list", "params": {}},
            )
            _expect(anonymous.status_code == 401, "anonymous MCP call was not rejected")
            _expect_error_without_result(anonymous, "anonymous MCP call")

            authorization_a = _login(client, api_base, inputs.user_a, inputs.password)
            authorization_b = _login(client, api_base, inputs.user_b, inputs.password)
            session_a = _initialize(client, mcp_url, authorization_a, "a")

            tools = _require_tools(_mcp_post(
                client,
                mcp_url,
                authorization_a,
                session_a,
                {"jsonrpc": "2.0", "id": "list-a", "method": "tools/list", "params": {}},
            ))
            names = {item.get("name") for item in tools}
            _expect(names == CUSTOMER_TOOLS, "customer MCP catalog is not the fixed read-only catalog")
            _expect(
                not any(any(word in str(name).lower() for word in ("create", "cancel", "modify", "refund", "write", "sql", "shell")) for name in names),
                "customer MCP catalog exposed a write-shaped tool",
            )

            order_result = _mcp_post(
                client,
                mcp_url,
                authorization_a,
                session_a,
                {
                    "jsonrpc": "2.0",
                    "id": "owned-order",
                    "method": "tools/call",
                    "params": {"name": "get_order_summary", "arguments": {"orderRef": inputs.order_a}},
                },
            )
            _expect(order_result.status_code == 200, "owned read-only MCP order lookup failed")
            _assert_safe_success(order_result, expected_source="java_order_fact")

            sse = client.get(
                mcp_url,
                headers={
                    "Authorization": authorization_a,
                    "Accept": "text/event-stream",
                    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
                    MCP_SESSION_HEADER: session_a,
                },
            )
            _expect(sse.status_code == 200, "authenticated MCP SSE readiness failed")
            _expect("stream established" in sse.text and "order" not in sse.text.lower(), "MCP SSE exposed business data")

            foreign_session = _mcp_post(
                client,
                mcp_url,
                authorization_b,
                session_a,
                {"jsonrpc": "2.0", "id": "foreign-session", "method": "tools/list", "params": {}},
            )
            _expect(foreign_session.status_code == 404, "another member reused an MCP session")
            _expect_error_without_result(foreign_session, "foreign MCP session")

            session_b = _initialize(client, mcp_url, authorization_b, "b")
            foreign_order = _mcp_post(
                client,
                mcp_url,
                authorization_b,
                session_b,
                {
                    "jsonrpc": "2.0",
                    "id": "foreign-order",
                    "method": "tools/call",
                    "params": {"name": "get_order_summary", "arguments": {"orderRef": inputs.order_a}},
                },
            )
            _expect(foreign_order.status_code == 400, "foreign order reference was not rejected")
            _expect_error_without_result(foreign_order, "foreign MCP order")

            injected = _mcp_post(
                client,
                mcp_url,
                authorization_b,
                session_b,
                {
                    "jsonrpc": "2.0",
                    "id": "scope-injection",
                    "method": "tools/call",
                    "params": {
                        "name": "get_order_summary",
                        "arguments": {"orderRef": inputs.order_a, "memberId": 1},
                    },
                },
            )
            _expect(injected.status_code == 400, "MCP scope-shaped parameter was not rejected")
            _expect_error_without_result(injected, "MCP scope injection")

            closed = client.delete(
                mcp_url,
                headers={
                    "Authorization": authorization_a,
                    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
                    MCP_SESSION_HEADER: session_a,
                },
            )
            _expect(closed.status_code == 204, "MCP session close failed")
            after_close = _mcp_post(
                client,
                mcp_url,
                authorization_a,
                session_a,
                {"jsonrpc": "2.0", "id": "closed", "method": "tools/list", "params": {}},
            )
            _expect(after_close.status_code == 404, "closed MCP session remained usable")
            _expect_error_without_result(after_close, "closed MCP session")
    except (httpx.HTTPError, VerificationError) as exc:
        print(f"MCP website-proxy verification failed: {exc}")
        return 1

    print("MCP authenticated website-proxy verification passed.")
    return 0


def _resolve_live_inputs() -> LiveInputs | None:
    required = (
        "MALL_MCP_LIVE_USER_A",
        "MALL_MCP_LIVE_USER_B",
        "MALL_MCP_LIVE_PASSWORD",
        "MALL_MCP_LIVE_ORDER_A",
    )
    values = {name: os.getenv(name) for name in required}
    if all(isinstance(value, str) and value.strip() for value in values.values()):
        return LiveInputs(
            user_a=values["MALL_MCP_LIVE_USER_A"] or "",
            user_b=values["MALL_MCP_LIVE_USER_B"] or "",
            password=values["MALL_MCP_LIVE_PASSWORD"] or "",
            order_a=values["MALL_MCP_LIVE_ORDER_A"] or "",
        )
    if os.getenv("MALL_MCP_BOOTSTRAP_LOCAL_DEMO", "").strip().lower() != "true":
        print("Missing MCP local fixture variables; or explicitly enable MALL_MCP_BOOTSTRAP_LOCAL_DEMO=true.")
        return None
    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        print("Missing MALL_LIVE_DEMO_PASSWORD for explicit local MCP fixture bootstrap.")
        return None
    return _bootstrap_disposable_inputs(password)


def _bootstrap_disposable_inputs(password: str) -> LiveInputs:
    """Create only disposable local customer fixtures through Java public APIs."""

    try:
        from bootstrap_live_demo import DemoAccount, LiveDemoSetupError, _prepare_account_order
    except ImportError as exc:  # pragma: no cover - script packaging error
        raise VerificationError("MCP local fixture helper is unavailable") from exc

    nonce = uuid.uuid4().hex[:12]
    phone_seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount("mcp-A", f"mcp_a_{nonce}", password, f"197{phone_seed:08d}"),
        DemoAccount("mcp-B", f"mcp_b_{nonce}", password, f"196{(phone_seed + 1) % 100_000_000:08d}"),
    )
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    try:
        with httpx.Client(timeout=45) as client:
            order_a = _prepare_account_order(
                client, java_base, accounts[0], int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")), required_stock=2
            )
            _prepare_account_order(
                client, java_base, accounts[1], int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26")), required_stock=1
            )
    except (httpx.HTTPError, LiveDemoSetupError, ValueError) as exc:
        raise VerificationError("Unable to prepare local synthetic MCP fixtures") from exc
    return LiveInputs(accounts[0].username, accounts[1].username, password, order_a.order_sn)


def _login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    response = client.post(f"{api_base}/auth/login", json={"username": username, "password": password})
    _expect(response.status_code == 200, "customer login failed")
    payload = _json_object(response, "customer login")
    authorization = payload.get("authorization")
    _expect(isinstance(authorization, str) and authorization.startswith("Bearer "), "customer login has no credential")
    return authorization


def _initialize(client: httpx.Client, mcp_url: str, authorization: str, request_id: str) -> str:
    response = client.post(
        mcp_url,
        headers={**MCP_HEADERS, "Authorization": authorization},
        json={
            "jsonrpc": "2.0",
            "id": f"init-{request_id}",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mall-local-verifier", "version": "1"},
            },
        },
    )
    _expect(response.status_code == 200, "MCP initialize failed")
    payload = _json_object(response, "MCP initialize")
    _expect(payload.get("result", {}).get("protocolVersion") == MCP_PROTOCOL_VERSION, "MCP negotiation returned a wrong protocol")
    session_id = response.headers.get(MCP_SESSION_HEADER)
    _expect(isinstance(session_id, str) and bool(session_id.strip()), "MCP initialize returned no session")
    return session_id


def _mcp_post(
    client: httpx.Client,
    mcp_url: str,
    authorization: str,
    session_id: str,
    payload: dict[str, Any],
) -> httpx.Response:
    return client.post(
        mcp_url,
        headers={**MCP_HEADERS, "Authorization": authorization, MCP_SESSION_HEADER: session_id},
        json=payload,
    )


def _require_tools(response: httpx.Response) -> list[dict[str, Any]]:
    _expect(response.status_code == 200, "MCP tools/list failed")
    payload = _json_object(response, "MCP tools/list")
    value = payload.get("result", {}).get("tools")
    _expect(isinstance(value, list) and all(isinstance(item, dict) for item in value), "MCP tools/list returned malformed data")
    return value


def _assert_safe_success(response: httpx.Response, *, expected_source: str) -> None:
    payload = _json_object(response, "MCP tool result")
    result = payload.get("result")
    _expect(isinstance(result, dict), "MCP tool result is missing")
    structured = result.get("structuredContent")
    _expect(isinstance(structured, dict) and structured.get("source") == expected_source, "MCP tool did not return Java fact source")
    _assert_no_forbidden_fields(structured)


def _expect_error_without_result(response: httpx.Response, label: str) -> None:
    payload = _json_object(response, label)
    _expect(isinstance(payload.get("error"), dict), f"{label} did not return an MCP error")
    _expect("result" not in payload, f"{label} leaked MCP result data")


def _assert_no_forbidden_fields(value: object) -> None:
    if isinstance(value, dict):
        keys = {str(key).replace("_", "").lower() for key in value}
        _expect(not keys.intersection(FORBIDDEN_RESULT_FIELDS), "MCP result leaked an internal field")
        for nested in value.values():
            _assert_no_forbidden_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_fields(nested)


def _json_object(response: httpx.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError(f"{label} returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} returned malformed JSON")
    return payload


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


if __name__ == "__main__":
    sys.exit(main())
