"""Live verification for customer-scoped after-sales status tracking.

Use only disposable local demo accounts. The script creates one local return
application when necessary, checks its Java response, and proves that the
second demo account cannot see it through the FastAPI customer endpoint.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import httpx


SAFE_FIELDS = {
    "application_id",
    "order_sn",
    "product_name",
    "product_attr",
    "reason",
    "description",
    "status_code",
    "status",
    "status_label",
    "created_at",
    "updated_at",
    "handling_note",
}


class VerificationError(RuntimeError):
    pass


def main() -> int:
    required = (
        "MALL_TEST_USER_A",
        "MALL_TEST_PASSWORD_A",
        "MALL_TEST_ORDER_A",
        "MALL_TEST_USER_B",
        "MALL_TEST_PASSWORD_B",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print("Missing required local demo variables: " + ", ".join(missing))
        return 2

    ai_base = os.getenv("MALL_AI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    try:
        with httpx.Client(timeout=20) as client:
            authorization_a = _login(
                client,
                ai_base,
                os.environ["MALL_TEST_USER_A"],
                os.environ["MALL_TEST_PASSWORD_A"],
            )
            authorization_b = _login(
                client,
                ai_base,
                os.environ["MALL_TEST_USER_B"],
                os.environ["MALL_TEST_PASSWORD_B"],
            )
            order_sn = os.environ["MALL_TEST_ORDER_A"]
            application = _create_or_find_return_application(
                client,
                java_base,
                ai_base,
                authorization_a,
                order_sn,
            )
            application_id = _require_int(application.get("application_id"), "application_id")
            _assert_safe_fastapi_record(application)

            account_b_records = _list_return_applications(client, ai_base, authorization_b)
            account_b_ids = {
                record.get("application_id")
                for record in account_b_records
                if isinstance(record, dict)
            }
            if application_id in account_b_ids:
                raise VerificationError("Account B unexpectedly received account A's return application")
    except (httpx.HTTPError, VerificationError, ValueError) as exc:
        print(f"Build 14A live verification failed: {exc}")
        return 1

    print(
        "Build 14A live verification passed: "
        f"application={application_id}, status={application.get('status')}"
    )
    return 0


def _login(client: httpx.Client, ai_base: str, username: str, password: str) -> str:
    response = client.post(
        f"{ai_base}/auth/login",
        json={"username": username, "password": password},
    )
    payload = _require_dict(_json(response, "login"), "login payload")
    _expect(response.status_code == 200, "FastAPI login did not return HTTP 200")
    authorization = payload.get("authorization")
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise VerificationError("FastAPI login did not return a Bearer credential")
    return authorization


def _create_or_find_return_application(
    client: httpx.Client,
    java_base: str,
    ai_base: str,
    authorization: str,
    order_sn: str,
) -> dict[str, Any]:
    records_before = _list_return_applications(client, ai_base, authorization)
    existing = _find_by_order_sn(records_before, order_sn)
    if existing is not None:
        return existing

    order_response = client.get(
        f"{java_base}/order/ai/detail/by-sn/{order_sn}",
        headers={"Authorization": authorization},
    )
    order_payload = _require_dict(_json(order_response, "order detail"), "order detail payload")
    _expect(order_response.status_code == 200 and order_payload.get("code") == 200, "Cannot read demo order")
    order_data = _require_dict(order_payload.get("data"), "order detail data")
    items = order_data.get("orderItems")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise VerificationError("Demo order has no returnable item")
    order_item_id = _require_int(items[0].get("orderItemId"), "orderItemId")

    create_response = client.post(
        f"{java_base}/returnApply/ai/create",
        headers={"Authorization": authorization},
        json={
            "orderSn": order_sn,
            "orderItemId": order_item_id,
            "reason": "质量问题",
            "description": "Build 14A local live verification",
        },
    )
    create_payload = _require_dict(
        _json(create_response, "return application creation"),
        "return application creation payload",
    )
    _expect(
        create_response.status_code == 200 and create_payload.get("code") == 200,
        "Java did not create the disposable return application",
    )
    java_summary = _require_dict(create_payload.get("data"), "Java return summary")
    _expect(isinstance(java_summary.get("applicationId"), int), "Java did not return applicationId")
    _expect(java_summary.get("status") == "pending_review", "New application is not pending_review")

    records_after = _list_return_applications(client, ai_base, authorization)
    application_id = java_summary["applicationId"]
    for record in records_after:
        if isinstance(record, dict) and record.get("application_id") == application_id:
            return record
    raise VerificationError("FastAPI return history did not include the newly created application")


def _list_return_applications(
    client: httpx.Client,
    ai_base: str,
    authorization: str,
) -> list[dict[str, Any]]:
    response = client.get(
        f"{ai_base}/customer-service/return-applications",
        headers={"Authorization": authorization},
    )
    payload = _json(response, "FastAPI return history")
    _expect(response.status_code == 200, "FastAPI return history did not return HTTP 200")
    if not isinstance(payload, list):
        raise VerificationError("FastAPI return history is not a list")
    return [record for record in payload if isinstance(record, dict)]


def _find_by_order_sn(records: list[dict[str, Any]], order_sn: str) -> dict[str, Any] | None:
    for record in records:
        if record.get("order_sn") == order_sn:
            return record
    return None


def _assert_safe_fastapi_record(record: dict[str, Any]) -> None:
    unexpected = set(record) - SAFE_FIELDS
    if unexpected:
        raise VerificationError("FastAPI exposed unexpected fields: " + ", ".join(sorted(unexpected)))
    for forbidden in ("return_phone", "return_name", "product_price", "order_id", "member_username"):
        if forbidden in record:
            raise VerificationError("FastAPI exposed forbidden field: " + forbidden)


def _json(response: httpx.Response, label: str) -> dict[str, Any] | list[Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError(f"{label} returned non-JSON data") from exc
    if not isinstance(payload, (dict, list)):
        raise VerificationError(f"{label} returned an unexpected JSON type")
    return payload


def _require_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerificationError(f"{label} is missing or malformed")
    return value


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise VerificationError(f"{label} is missing or malformed")
    return value


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


if __name__ == "__main__":
    sys.exit(main())
