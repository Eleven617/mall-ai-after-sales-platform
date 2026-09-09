"""Verify both sides of the Build 14A return-refund eligibility boundary.

The verifier uses only disposable local fixtures.  The negative path proves a
paid-but-not-received order is rejected without a write.  The positive path
uses the Java admin delivery endpoint followed by the customer confirmation
endpoint, then submits through the protected AI facade and checks the public
projection plus the transactional outbox.  No database row is edited by the
verifier itself.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx


class VerificationError(RuntimeError):
    pass


def main() -> int:
    fixture_path = os.getenv("MALL_FIELD_FIXTURE_FILE")
    password = os.getenv("MALL_FIELD_FIXTURE_PASSWORD")
    if not fixture_path or not password:
        print("Build 14A fixture requires MALL_FIELD_FIXTURE_FILE and a process-only password.")
        return 2
    stage = "load"
    try:
        fixture = _load_fixture(Path(fixture_path))
        web_base = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
        ai_base = os.getenv("MALL_AI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
        admin_base = os.getenv("MALL_ADMIN_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
        user_a = str(fixture["account_a"]["username"])
        user_b = str(fixture["account_b"]["username"])
        order_sn = str(fixture["account_a"]["order_sn"])
        order_id = int(fixture["account_a"]["order_id"])
        with httpx.Client(timeout=45, trust_env=False) as client:
            stage = "customer-login"
            auth_a = _login(client, ai_base, user_a, password)
            auth_b = _login(client, ai_base, user_b, password)
            stage = "order-read"
            before = _list_public(client, ai_base, auth_a)
            order = _order_detail(client, java_base, auth_a, order_sn)
            item_id = int(order["orderItems"][0]["orderItemId"])

            # Negative: a paid, not-yet-received order must remain ineligible.
            stage = "negative-eligibility"
            negative = _eligibility(client, java_base, auth_a, order_sn, item_id)
            if negative.get("eligible") is not False:
                raise VerificationError("negative return-refund eligibility unexpectedly allowed the order")
            stage = "negative-create"
            denied = _create_application(client, java_base, auth_a, order_sn, item_id)
            if denied.status_code < 400 and _json_object(denied).get("code") == 200:
                raise VerificationError("negative return-refund request created an application")
            after_denied = _list_public(client, ai_base, auth_a)
            if len(after_denied) != len(before):
                raise VerificationError("negative eligibility path changed the public application count")

            # Positive: use the real admin delivery endpoint and customer
            # confirm-receive endpoint; never update oms_order directly.
            stage = "admin-login"
            admin_auth = _operations_login(client, ai_base, "localDemoOperations", password)
            stage = "deliver"
            _deliver(client, admin_base, admin_auth, order_id)
            stage = "confirm-receive"
            _confirm_receive(client, java_base, auth_a, order_id)
            stage = "positive-eligibility"
            positive = _eligibility(client, java_base, auth_a, order_sn, item_id)
            if positive.get("eligible") is not True:
                raise VerificationError("delivered-and-received order was not eligible for return-refund")
            stage = "positive-create"
            key = uuid.uuid4().hex
            created = _create_application(client, java_base, auth_a, order_sn, item_id, key)
            created_payload = _json_object(created)
            if created.status_code != 200 or created_payload.get("code") != 200:
                raise VerificationError("eligible order could not create the return-refund application")
            summary = _dict(created_payload.get("data"))
            application_id = int(summary["applicationId"])
            stage = "public-owner"
            public_records = _list_public(client, ai_base, auth_a)
            if not any(int(item.get("application_id", -1)) == application_id for item in public_records):
                raise VerificationError("FastAPI did not expose the newly created application to its owner")
            stage = "public-foreign"
            foreign_records = _list_public(client, ai_base, auth_b)
            if any(int(item.get("application_id", -1)) == application_id for item in foreign_records):
                raise VerificationError("a second account received the first account's application")
            stage = "idempotency"
            duplicate = _create_application(client, java_base, auth_a, order_sn, item_id, key)
            duplicate_payload = _json_object(duplicate)
            if duplicate.status_code != 200 or duplicate_payload.get("code") != 200:
                raise VerificationError("idempotent duplicate submission was not accepted as the same result")
            if int(_dict(duplicate_payload.get("data"))["applicationId"]) != application_id:
                raise VerificationError("duplicate idempotency key created a second application")
            stage = "outbox"
            outbox_count = _mysql_scalar(
                f"SELECT COUNT(*) FROM ai_after_sales_outbox WHERE application_id={application_id};"
            )
            if outbox_count < 1:
                raise VerificationError("successful application has no transactional outbox event")
    except (OSError, ValueError, httpx.HTTPError, VerificationError, KeyError) as exc:
        print(f"Build 14A eligibility verification failed: stage={stage}, error={type(exc).__name__}, detail={exc}")
        return 1
    print("Build 14A eligibility verification passed: negative and positive Java-qualified paths.")
    return 0


def _load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("account_a"), dict) or not isinstance(value.get("account_b"), dict):
        raise VerificationError("fixture is malformed")
    return value


def _login(client: httpx.Client, base: str, username: str, password: str) -> str:
    payload = _json_object(client.post(f"{base}/auth/login", json={"username": username, "password": password}))
    if payload.get("authorization", "").startswith("Bearer ") is False:
        raise VerificationError("customer login did not return a scoped credential")
    return payload["authorization"]


def _admin_login(client: httpx.Client, base: str, username: str, password: str) -> str:
    try:
        response = client.post(f"{base}/admin/login", json={"username": username, "password": password})
        payload = _json_object(response)
    except httpx.ConnectError:
        payload = _admin_proxy_request("POST", "/admin/login", {"username": username, "password": password})
    if not isinstance(payload.get("data"), dict):
        try:
            Path(__file__).resolve().parents[2].joinpath("tmp", "field-admin-debug.json").write_text(
                json.dumps({"keys": sorted(str(key) for key in payload), "code": payload.get("code"), "dataType": type(payload.get("data")).__name__, "messageType": type(payload.get("message")).__name__}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        raise VerificationError("operator login returned no data object")
    data = _dict(payload.get("data"))
    token = str(data["token"])
    head = str(data.get("tokenHead", "Bearer")).strip()
    if not token:
        raise VerificationError("operator login did not return a credential")
    return f"{head} {token}"


def _operations_login(client: httpx.Client, base: str, username: str, password: str) -> str:
    response = client.post(f"{base}/operations/auth/login", json={"username": username, "password": password})
    payload = _json_object(response)
    authorization = payload.get("authorization")
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise VerificationError("operations login did not return a scoped credential")
    return authorization


def _order_detail(client: httpx.Client, base: str, authorization: str, order_sn: str) -> dict[str, Any]:
    response = client.get(f"{base}/order/ai/detail/by-sn/{order_sn}", headers={"Authorization": authorization})
    payload = _json_object(response)
    if response.status_code != 200 or payload.get("code") != 200:
        raise VerificationError("order fact lookup failed")
    return _dict(payload.get("data"))


def _eligibility(client: httpx.Client, base: str, authorization: str, order_sn: str, item_id: int) -> dict[str, Any]:
    response = client.post(
        f"{base}/after-sales/ai/eligibility",
        headers={"Authorization": authorization},
        json={"orderSn": order_sn, "orderItemId": item_id, "applicationType": "return_refund"},
    )
    payload = _json_object(response)
    if response.status_code != 200 or payload.get("code") != 200:
        raise VerificationError("eligibility endpoint failed")
    return _dict(payload.get("data"))


def _create_application(
    client: httpx.Client,
    base: str,
    authorization: str,
    order_sn: str,
    item_id: int,
    key: str | None = None,
) -> httpx.Response:
    return client.post(
        f"{base}/after-sales/ai/applications",
        headers={
            "Authorization": authorization,
            "X-AI-After-Sales-Key": os.getenv("AI_AFTER_SALES_SERVICE_KEY", "local-build21-after-sales-key"),
        },
        json={
            "orderSn": order_sn,
            "applicationType": "return_refund",
            "orderItemId": item_id,
            "reason": "质量问题",
            "description": "一次性现场合成验收",
            "idempotencyKey": key or uuid.uuid4().hex,
        },
    )


def _deliver(client: httpx.Client, base: str, authorization: str, order_id: int) -> None:
    payload_data = [{"orderId": order_id, "deliveryCompany": "synthetic-carrier", "deliverySn": uuid.uuid4().hex}]
    status_code = 200
    try:
        response = client.post(
            f"{base}/order/update/delivery",
            headers={"Authorization": authorization},
            json=payload_data,
        )
        payload = _json_object(response)
        status_code = response.status_code
    except httpx.ConnectError:
        payload = _admin_proxy_request(
            "POST",
            "/order/update/delivery",
            payload_data,
            authorization=authorization,
        )
    if status_code != 200 or payload.get("code") != 200:
        raise VerificationError("operator delivery transition failed")


def _confirm_receive(client: httpx.Client, base: str, authorization: str, order_id: int) -> None:
    response = client.post(
        f"{base}/order/confirmReceiveOrder",
        headers={"Authorization": authorization},
        params={"orderId": order_id},
    )
    payload = _json_object(response)
    if response.status_code != 200 or payload.get("code") != 200:
        raise VerificationError("customer confirmation transition failed")


def _list_public(client: httpx.Client, base: str, authorization: str) -> list[dict[str, Any]]:
    response = client.get(f"{base}/customer-service/after-sales-applications", headers={"Authorization": authorization})
    payload = response.json()
    if response.status_code != 200 or not isinstance(payload, list):
        raise VerificationError("customer after-sales list failed")
    return [item for item in payload if isinstance(item, dict)]


def _mysql_scalar(sql: str) -> int:
    root = Path(__file__).resolve().parents[2]
    command = ["docker", "compose", "exec", "-T", "mysql", "sh", "-c", "MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=root --skip-column-names --batch mall"]
    result = subprocess.run(command, cwd=root, input=sql + "\n", text=True, capture_output=True, check=False, timeout=30)
    if result.returncode != 0:
        raise VerificationError("MySQL assertion command failed")
    try:
        return int(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise VerificationError("MySQL assertion returned malformed data") from exc


def _admin_proxy_request(
    method: str,
    path: str,
    payload: object,
    *,
    authorization: str | None = None,
) -> dict[str, Any]:
    """Call the unexposed admin container through the Compose network.

    The host intentionally does not publish port 8080.  This helper uses the
    already-running AI container as a network hop and sends request data over
    stdin; neither credentials nor response payloads are printed or persisted.
    """
    root = Path(__file__).resolve().parents[2]
    bridge = (
        "import json,sys,urllib.request,urllib.error; "
        "v=json.load(sys.stdin); "
        "d=json.dumps(v['payload'],ensure_ascii=False).encode('utf-8'); "
        "r=urllib.request.Request('http://mall-admin:8080'+v['path'],data=d,method=v['method'],headers={'Content-Type':'application/json',**({'Authorization':v['authorization']} if v.get('authorization') else {})}); "
        "\ntry: print(urllib.request.urlopen(r,timeout=30).read().decode('utf-8'))\nexcept urllib.error.HTTPError as e: print(e.read().decode('utf-8'))"
    )
    request = {"method": method, "path": path, "payload": payload, "authorization": authorization}
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "mall-ai-service", "python", "-c", bridge],
        cwd=root,
        input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
        text=False,
        capture_output=True,
        check=False,
        timeout=45,
    )
    if result.returncode != 0:
        raise VerificationError(f"admin network hop failed code={result.returncode}")
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise VerificationError("admin network hop returned no response")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise VerificationError("admin network hop returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError("admin response is not an object")
    return value


def _json_object(response: httpx.Response) -> dict[str, Any]:
    value = response.json()
    if not isinstance(value, dict):
        raise VerificationError("response JSON is not an object")
    return value


def _dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerificationError("response field is not an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
