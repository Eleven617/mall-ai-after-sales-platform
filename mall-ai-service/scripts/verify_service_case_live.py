"""Website-proxy verification for the FR-19 human service-case closure.

The harness uses only disposable local accounts supplied through process
environment variables.  It never prints passwords, Bearer credentials, order
numbers, raw customer text, internal notes, queue details or trace data.

Required variables:
  MALL_SERVICE_CASE_LIVE_USER_A / _USER_B / _PASSWORD / _ORDER_A
  MALL_SERVICE_CASE_PROCESSOR_USERNAME / _PROCESSOR_PASSWORD
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any

import httpx


class VerificationError(RuntimeError):
    pass


_CUSTOMER_FORBIDDEN = {
    "member_id",
    "memberId",
    "queue_ref",
    "queueRef",
    "assignee_ref",
    "assigneeRef",
    "case_key",
    "caseKey",
    "internal_note",
    "internalNote",
    "trace",
    "token",
    "authorization",
    "order_sn",
    "orderSn",
    "rag_context",
    "tool_result",
}


def main() -> int:
    required = (
        "MALL_SERVICE_CASE_LIVE_USER_A",
        "MALL_SERVICE_CASE_LIVE_USER_B",
        "MALL_SERVICE_CASE_LIVE_PASSWORD",
        "MALL_SERVICE_CASE_LIVE_ORDER_A",
        "MALL_SERVICE_CASE_PROCESSOR_USERNAME",
        "MALL_SERVICE_CASE_PROCESSOR_PASSWORD",
    )
    if any(not os.getenv(name) for name in required):
        print("Service-case verification is missing local disposable-account variables.")
        return 2

    web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
    api_base = f"{web_base}/api"
    try:
        with httpx.Client(timeout=60, trust_env=False) as client:
            _expect_status(client.get(f"{api_base}/service-operations/cases"), 401, "anonymous processor read")
            password = os.environ["MALL_SERVICE_CASE_LIVE_PASSWORD"]
            customer_a = _customer_login(client, api_base, os.environ["MALL_SERVICE_CASE_LIVE_USER_A"], password)
            customer_b = _customer_login(client, api_base, os.environ["MALL_SERVICE_CASE_LIVE_USER_B"], password)
            processor = _processor_login(
                client,
                api_base,
                os.environ["MALL_SERVICE_CASE_PROCESSOR_USERNAME"],
                os.environ["MALL_SERVICE_CASE_PROCESSOR_PASSWORD"],
            )
            _expect_status(
                client.get(f"{api_base}/service-operations/me", headers=_headers(processor)),
                200,
                "dedicated processor profile",
            )

            before = _customer_cases(client, api_base, customer_a)
            conversation_id = str(uuid.uuid4())
            _expect_status(
                client.post(
                    f"{api_base}/customer-service/conversations/{conversation_id}",
                    headers=_headers(customer_a),
                ),
                200,
                "customer conversation creation",
            )
            diagnosis = _json_object(
                client.post(
                    f"{api_base}/customer-service",
                    headers=_headers(customer_a),
                    json={
                        "session_id": conversation_id,
                        "message": (
                            f"订单号：{os.environ['MALL_SERVICE_CASE_LIVE_ORDER_A']}。"
                            "请诊断该订单的配送异常：物流长期停滞，订单没有按预期完成。"
                            "请先核对订单和物流事实；若证据仍不足，请安全转人工。"
                        ),
                    },
                ),
                "customer diagnosis",
            )
            _assert_customer_safe(diagnosis)
            _expect(
                isinstance(diagnosis.get("diagnosis"), dict)
                and isinstance(diagnosis["diagnosis"].get("handoff"), dict),
                "diagnosis did not create a customer-safe human handoff",
            )

            queued = _find_new_case(before, _customer_cases(client, api_base, customer_a))
            _expect(queued.get("state") == "QUEUED", "new service case was not queued")
            case_id = _text(queued.get("case_id"), "service case id")

            processor_cases = _processor_cases(client, api_base, processor)
            _expect(
                any(item.get("case_id") == case_id and item.get("assigned_to_me") is False for item in processor_cases),
                "processor did not receive the queued minimal case",
            )
            claimed = _processor_claim(client, api_base, processor, case_id, _version(queued))
            _expect(claimed.get("state") == "CLAIMED" and claimed.get("assigned_to_me") is True, "claim failed")

            awaiting = _processor_action(
                client,
                api_base,
                processor,
                case_id,
                _version(claimed),
                action="request_information",
                information_type="purchase_context",
                public_message="请补充购买或首次使用的背景信息。",
                internal_note="本地合成验收：等待允许范围内的补件。",
            )
            _expect(awaiting.get("state") == "AWAITING_CUSTOMER_INFORMATION", "request-information state failed")

            awaiting_customer = _case_by_id(_customer_cases(client, api_base, customer_a), case_id)
            _expect(
                awaiting_customer.get("required_information_type") == "purchase_context",
                "customer did not receive the Java-selected supplement type",
            )
            reviewed = _customer_information(
                client,
                api_base,
                customer_a,
                case_id,
                _version(awaiting_customer),
                information_type="purchase_context",
                information="签收后第一次使用时出现问题，已按要求补充购买背景。",
            )
            _assert_customer_safe(reviewed)
            _expect(reviewed.get("state") == "IN_REVIEW", "customer supplement did not resume review")

            resolved = _processor_action(
                client,
                api_base,
                processor,
                case_id,
                _version(reviewed),
                action="resolve",
                public_message="人工已完成核验，并已给出处理结果。",
                internal_note="本地合成验收：处理结论仅写入内部审计。",
            )
            closed = _processor_action(
                client,
                api_base,
                processor,
                case_id,
                _version(resolved),
                action="close",
                public_message="人工协同事项已结案。",
                internal_note="本地合成验收：已结案。",
            )
            _expect(closed.get("state") == "CLOSED", "processor close failed")

            customer_closed = _case_by_id(_customer_cases(client, api_base, customer_a), case_id)
            _assert_customer_safe(customer_closed)
            _expect(customer_closed.get("state") == "CLOSED", "customer did not receive closed state")
            timeline = _json_list(
                client.get(f"{api_base}/customer-service/service-cases/{case_id}/timeline", headers=_headers(customer_a)),
                "customer public timeline",
            )
            _assert_customer_safe(timeline)
            _expect(bool(timeline), "customer timeline is empty")
            _expect(
                all(item.get("case_id") != case_id for item in _customer_cases(client, api_base, customer_b)),
                "second customer received another member's service case",
            )
    except (httpx.HTTPError, VerificationError) as exc:
        print(f"Service-case website-proxy verification failed: {exc}")
        return 1

    print("Service-case website-proxy verification passed.")
    return 0


def _customer_login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    payload = _json_object(client.post(f"{api_base}/auth/login", json={"username": username, "password": password}), "customer login")
    return _authorization(payload, "customer login")


def _processor_login(client: httpx.Client, api_base: str, username: str, password: str) -> str:
    payload = _json_object(
        client.post(f"{api_base}/service-operations/auth/login", json={"username": username, "password": password}),
        "processor login",
    )
    return _authorization(payload, "processor login")


def _customer_cases(client: httpx.Client, api_base: str, authorization: str) -> list[dict[str, Any]]:
    cases = _json_list(client.get(f"{api_base}/customer-service/service-cases", headers=_headers(authorization)), "customer cases")
    _assert_customer_safe(cases)
    return cases


def _processor_cases(client: httpx.Client, api_base: str, authorization: str) -> list[dict[str, Any]]:
    records = _json_list(client.get(f"{api_base}/service-operations/cases", headers=_headers(authorization)), "processor cases")
    for record in records:
        _expect("member_id" not in record and "memberId" not in record, "processor projection leaked member identity")
        _expect("internal_note" not in record and "internalNote" not in record, "processor list leaked internal note")
    return records


def _processor_claim(client: httpx.Client, api_base: str, authorization: str, case_id: str, version: int) -> dict[str, Any]:
    return _json_object(
        client.post(
            f"{api_base}/service-operations/cases/{case_id}/claim",
            headers=_headers(authorization),
            json={"expected_version": version, "idempotency_key": uuid.uuid4().hex},
        ),
        "processor claim",
    )


def _processor_action(
    client: httpx.Client,
    api_base: str,
    authorization: str,
    case_id: str,
    version: int,
    *,
    action: str,
    public_message: str,
    internal_note: str,
    information_type: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "expected_version": version,
        "idempotency_key": uuid.uuid4().hex,
        "action": action,
        "public_message": public_message,
        "internal_note": internal_note,
    }
    if information_type is not None:
        payload["information_type"] = information_type
    return _json_object(
        client.post(f"{api_base}/service-operations/cases/{case_id}/actions", headers=_headers(authorization), json=payload),
        f"processor {action}",
    )


def _customer_information(
    client: httpx.Client,
    api_base: str,
    authorization: str,
    case_id: str,
    version: int,
    *,
    information_type: str,
    information: str,
) -> dict[str, Any]:
    return _json_object(
        client.post(
            f"{api_base}/customer-service/service-cases/{case_id}/customer-information",
            headers=_headers(authorization),
            json={
                "expected_version": version,
                "idempotency_key": uuid.uuid4().hex,
                "information_type": information_type,
                "information": information,
            },
        ),
        "customer information",
    )


def _find_new_case(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    before_ids = {item.get("case_id") for item in before}
    candidates = [item for item in after if item.get("case_id") not in before_ids]
    _expect(len(candidates) == 1, "handoff did not create exactly one new customer case")
    return candidates[0]


def _case_by_id(cases: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    for case in cases:
        if case.get("case_id") == case_id:
            return case
    raise VerificationError("owned service case was not found")


def _authorization(payload: dict[str, Any], label: str) -> str:
    authorization = payload.get("authorization")
    _expect(isinstance(authorization, str) and authorization.startswith("Bearer "), f"{label} has no Bearer credential")
    return authorization


def _headers(authorization: str) -> dict[str, str]:
    return {"Authorization": authorization}


def _version(record: dict[str, Any]) -> int:
    value = record.get("state_version")
    _expect(isinstance(value, int) and value > 0, "service case state version is invalid")
    return value


def _text(value: object, label: str) -> str:
    _expect(isinstance(value, str) and value.strip(), f"{label} is missing")
    return value.strip()


def _json_object(response: httpx.Response, label: str) -> dict[str, Any]:
    _expect_status(response, 200, label)
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError(f"{label} returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} returned a malformed object")
    return payload


def _json_list(response: httpx.Response, label: str) -> list[dict[str, Any]]:
    _expect_status(response, 200, label)
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError(f"{label} returned non-JSON") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise VerificationError(f"{label} returned a malformed list")
    return payload


def _expect_status(response: httpx.Response, expected: int, label: str) -> None:
    _expect(response.status_code == expected, f"{label} returned HTTP {response.status_code}")


def _assert_customer_safe(value: object) -> None:
    if isinstance(value, dict):
        forbidden = _CUSTOMER_FORBIDDEN.intersection(value)
        _expect(not forbidden, "customer projection leaked internal fields")
        for nested in value.values():
            _assert_customer_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_customer_safe(nested)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


if __name__ == "__main__":
    sys.exit(main())
