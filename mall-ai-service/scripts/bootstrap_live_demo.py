"""Create disposable local mall accounts and orders through the Java APIs.

This utility is intentionally for local live verification only. It does not
touch the database directly, print credentials or account/order identifiers,
or contain a password. Set the password in ``MALL_LIVE_DEMO_PASSWORD`` before
running it.  A caller that needs identifiers for an in-process verification
must opt in to the short-lived ``MALL_LIVE_DEMO_RESULT_FILE`` contract.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class LiveDemoSetupError(RuntimeError):
    """Raised when the local Java mall cannot prepare a disposable demo case."""


@dataclass(frozen=True)
class DemoAccount:
    label: str
    username: str
    password: str
    telephone: str


@dataclass(frozen=True)
class DemoOrder:
    username: str
    member_id: int
    order_id: int
    order_sn: str


def main() -> int:
    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        print("缺少 MALL_LIVE_DEMO_PASSWORD；请只在本地终端临时设置，不要写入脚本。")
        return 2

    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    # Product 26 is part of the seeded mall data and has multiple SKUs with
    # ample stock. The variable still permits an explicit local override.
    product_id = int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26"))
    nonce = uuid.uuid4().hex[:12]
    phone_seed = uuid.uuid4().int % 100_000_000
    accounts = (
        DemoAccount(
            label="A",
            # A fresh default prevents a stale password from an earlier local
            # run from making the supposedly disposable bootstrap impossible
            # to repeat. Explicit account variables still preserve the caller's
            # chosen fixture identity.
            username=os.getenv("MALL_LIVE_DEMO_USER_A") or f"ai_demo_a_{nonce}",
            password=password,
            telephone=os.getenv("MALL_LIVE_DEMO_PHONE_A") or f"199{phone_seed:08d}",
        ),
        DemoAccount(
            label="B",
            username=os.getenv("MALL_LIVE_DEMO_USER_B") or f"ai_demo_b_{nonce}",
            password=password,
            telephone=os.getenv("MALL_LIVE_DEMO_PHONE_B") or f"198{(phone_seed + 1) % 100_000_000:08d}",
        ),
    )

    try:
        # These fixtures intentionally exercise the local Compose Java API.
        # httpx otherwise honours Windows system proxy settings, which can
        # proxy 127.0.0.1 and turn a healthy local endpoint into HTTP 502.
        with httpx.Client(timeout=20, trust_env=False) as client:
            orders = [
                _prepare_account_order(
                    client,
                    java_base,
                    account,
                    product_id,
                    required_stock=len(accounts) - index,
                )
                for index, account in enumerate(accounts)
            ]
    except (httpx.HTTPError, LiveDemoSetupError, ValueError) as exc:
        print(f"本地演示数据准备失败：{exc}")
        return 1

    if orders[0].order_sn == orders[1].order_sn:
        print("本地演示数据准备失败：两个账号意外得到同一订单号。")
        return 1

    result = {
        "account_a": _machine_order_summary(orders[0]),
        "account_b": _machine_order_summary(orders[1]),
    }
    result_file = os.getenv("MALL_LIVE_DEMO_RESULT_FILE")
    if result_file:
        target = Path(result_file)
        if not target.is_absolute() or target.suffix.lower() not in {".json", ".tmp"}:
            print("本地演示结果文件路径不合法。")
            return 1
        try:
            target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            print(f"本地演示结果文件无法写入：{exc}")
            return 1

    # Never put member/order identifiers on stdout.  The caller that needs
    # them for an in-process verification reads the short-lived result file
    # above and deletes it immediately.
    print(
        json.dumps(
            {
                "status": "prepared",
                "accounts": [
                    {"label": "A", "username": orders[0].username},
                    {"label": "B", "username": orders[1].username},
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def _prepare_account_order(
    client: httpx.Client,
    java_base: str,
    account: DemoAccount,
    product_id: int,
    *,
    required_stock: int,
) -> DemoOrder:
    authorization, member_id = _ensure_login(client, java_base, account)
    headers = {"Authorization": authorization}
    address_id = _ensure_address(client, java_base, headers, account)
    product, sku = _get_available_sku(
        client,
        java_base,
        product_id,
        min_stock=required_stock,
    )
    cart_id = _add_product_to_cart(client, java_base, headers, product, sku)
    order_id, order_sn = _generate_order(client, java_base, headers, address_id, cart_id)
    _pay_order(client, java_base, headers, order_id)
    _verify_owned_order(client, java_base, headers, order_sn)
    return DemoOrder(
        username=account.username,
        member_id=member_id,
        order_id=order_id,
        order_sn=order_sn,
    )


def _ensure_login(
    client: httpx.Client,
    java_base: str,
    account: DemoAccount,
) -> tuple[str, int]:
    login = _form_request(
        client,
        "POST",
        f"{java_base}/sso/login",
        {"username": account.username, "password": account.password},
        f"账号 {account.label} 登录",
    )
    if login.get("code") != 200:
        auth_code = _get_auth_code(client, java_base, account.telephone)
        register = _form_request(
            client,
            "POST",
            f"{java_base}/sso/register",
            {
                "username": account.username,
                "password": account.password,
                "telephone": account.telephone,
                "authCode": auth_code,
            },
            f"账号 {account.label} 注册",
        )
        _expect_code(register, 200, f"账号 {account.label} 注册")
        login = _form_request(
            client,
            "POST",
            f"{java_base}/sso/login",
            {"username": account.username, "password": account.password},
            f"账号 {account.label} 注册后登录",
        )

    _expect_code(login, 200, f"账号 {account.label} 登录")
    token_data = _require_dict(login.get("data"), f"账号 {account.label} 登录凭证")
    token = _require_text(token_data.get("token"), f"账号 {account.label} Token")
    token_head = _require_text(token_data.get("tokenHead"), f"账号 {account.label} Token 前缀")
    # Java returns the Token value and its Bearer prefix separately.  Normalize
    # the separator instead of relying on a trailing space in the upstream
    # prefix; otherwise a valid JWT becomes the malformed header ``Bearerxxx``.
    authorization = f"{token_head.strip()} {token.strip()}"
    member = _json_request(
        client,
        "GET",
        f"{java_base}/sso/info",
        headers={"Authorization": authorization},
        label=f"账号 {account.label} 身份回读",
    )
    _expect_code(member, 200, f"账号 {account.label} 身份回读")
    member_data = _require_dict(member.get("data"), f"账号 {account.label} 会员资料")
    member_id = member_data.get("id")
    if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
        raise LiveDemoSetupError(f"账号 {account.label} 的会员标识不合法。")
    return authorization, member_id


def _get_auth_code(client: httpx.Client, java_base: str, telephone: str) -> str:
    response = _json_request(
        client,
        "GET",
        f"{java_base}/sso/getAuthCode",
        params={"telephone": telephone},
        label="获取本地测试验证码",
    )
    _expect_code(response, 200, "获取本地测试验证码")
    return _require_text(response.get("data"), "本地测试验证码")


def _ensure_address(
    client: httpx.Client,
    java_base: str,
    headers: dict[str, str],
    account: DemoAccount,
) -> int:
    address_list = _json_request(
        client,
        "GET",
        f"{java_base}/member/address/list",
        headers=headers,
        label=f"账号 {account.label} 查询地址",
    )
    _expect_code(address_list, 200, f"账号 {account.label} 查询地址")
    addresses = _require_list(address_list.get("data"), f"账号 {account.label} 地址列表")
    existing = _find_address_by_phone(addresses, account.telephone)
    if existing is None:
        created = _json_request(
            client,
            "POST",
            f"{java_base}/member/address/add",
            headers=headers,
            json={
                "defaultStatus": 1,
                "name": f"AI Demo User {account.label}",
                "phoneNumber": account.telephone,
                "postCode": "100000",
                "province": "Beijing",
                "city": "Beijing",
                "region": "Haidian",
                "detailAddress": f"Local AI demo address {account.label}",
            },
            label=f"账号 {account.label} 创建地址",
        )
        _expect_code(created, 200, f"账号 {account.label} 创建地址")
        refreshed = _json_request(
            client,
            "GET",
            f"{java_base}/member/address/list",
            headers=headers,
            label=f"账号 {account.label} 回读地址",
        )
        _expect_code(refreshed, 200, f"账号 {account.label} 回读地址")
        existing = _find_address_by_phone(
            _require_list(refreshed.get("data"), f"账号 {account.label} 地址列表"),
            account.telephone,
        )

    address_id = existing.get("id") if existing else None
    if isinstance(address_id, bool) or not isinstance(address_id, int) or address_id <= 0:
        raise LiveDemoSetupError(f"账号 {account.label} 没有可用的本地测试地址。")
    return address_id


def _get_available_sku(
    client: httpx.Client,
    java_base: str,
    product_id: int,
    *,
    min_stock: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    detail = _json_request(
        client,
        "GET",
        f"{java_base}/product/detail/{product_id}",
        label="读取本地测试商品",
    )
    _expect_code(detail, 200, "读取本地测试商品")
    data = _require_dict(detail.get("data"), "本地测试商品详情")
    product = _require_dict(data.get("product"), "本地测试商品")
    sku_list = _require_list(data.get("skuStockList"), "本地测试商品规格")
    for candidate in sku_list:
        if not isinstance(candidate, dict):
            continue
        stock = candidate.get("stock")
        sku_id = candidate.get("id")
        if (
            isinstance(stock, int)
            and stock >= min_stock
            and isinstance(sku_id, int)
            and sku_id > 0
        ):
            return product, candidate
    raise LiveDemoSetupError("本地测试商品没有可用库存。")


def _add_product_to_cart(
    client: httpx.Client,
    java_base: str,
    headers: dict[str, str],
    product: dict[str, Any],
    sku: dict[str, Any],
) -> int:
    payload = {
        "price": sku.get("price") or product.get("promotionPrice") or product.get("price"),
        "productId": product.get("id"),
        "productName": product.get("name"),
        "productSkuCode": sku.get("skuCode"),
        "productSkuId": sku.get("id"),
        "productSubTitle": product.get("subTitle"),
        "quantity": 1,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    added = _json_request(
        client,
        "POST",
        f"{java_base}/cart/add",
        headers=headers,
        json=payload,
        label="添加本地测试商品到购物车",
    )
    _expect_code(added, 200, "添加本地测试商品到购物车")
    carts = _json_request(
        client,
        "GET",
        f"{java_base}/cart/list",
        headers=headers,
        label="读取本地测试购物车",
    )
    _expect_code(carts, 200, "读取本地测试购物车")
    matches = [
        item
        for item in _require_list(carts.get("data"), "本地测试购物车")
        if isinstance(item, dict) and item.get("productSkuId") == sku.get("id")
    ]
    if not matches:
        raise LiveDemoSetupError("本地测试商品未出现在当前账号购物车。")
    cart_id = max(matches, key=lambda item: int(item.get("id") or 0)).get("id")
    if isinstance(cart_id, bool) or not isinstance(cart_id, int) or cart_id <= 0:
        raise LiveDemoSetupError("本地测试购物车条目不合法。")
    return cart_id


def _generate_order(
    client: httpx.Client,
    java_base: str,
    headers: dict[str, str],
    address_id: int,
    cart_id: int,
) -> tuple[int, str]:
    created = _json_request(
        client,
        "POST",
        f"{java_base}/order/generateOrder",
        headers=headers,
        json={"memberReceiveAddressId": address_id, "payType": 0, "cartIds": [cart_id]},
        label="生成本地测试订单",
    )
    _expect_code(created, 200, "生成本地测试订单")
    data = _require_dict(created.get("data"), "本地测试订单结果")
    order = _require_dict(data.get("order"), "本地测试订单")
    order_id = order.get("id")
    order_sn = order.get("orderSn")
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0:
        raise LiveDemoSetupError("本地测试订单 ID 不合法。")
    return order_id, _require_text(order_sn, "本地测试订单号")


def _pay_order(
    client: httpx.Client,
    java_base: str,
    headers: dict[str, str],
    order_id: int,
) -> None:
    paid = _json_request(
        client,
        "POST",
        f"{java_base}/order/paySuccess",
        headers=headers,
        params={"orderId": order_id, "payType": 0},
        label="支付本地测试订单",
    )
    _expect_code(paid, 200, "支付本地测试订单")


def _verify_owned_order(
    client: httpx.Client,
    java_base: str,
    headers: dict[str, str],
    order_sn: str,
) -> None:
    result = _json_request(
        client,
        "GET",
        f"{java_base}/order/ai/detail/by-sn/{order_sn}",
        headers=headers,
        label="回读本地测试订单",
    )
    _expect_code(result, 200, "回读本地测试订单")


def _json_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    label: str,
) -> dict[str, Any]:
    response = client.request(method, url, headers=headers, params=params, json=json)
    if response.status_code >= 400:
        raise LiveDemoSetupError(f"{label}失败：HTTP {response.status_code}")
    return _as_payload(response, label)


def _form_request(
    client: httpx.Client,
    method: str,
    url: str,
    data: dict[str, str],
    label: str,
) -> dict[str, Any]:
    response = client.request(method, url, data=data)
    if response.status_code >= 400:
        raise LiveDemoSetupError(f"{label}失败：HTTP {response.status_code}")
    return _as_payload(response, label)


def _as_payload(response: httpx.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise LiveDemoSetupError(f"{label}返回了无法解析的数据。") from exc
    if not isinstance(payload, dict):
        raise LiveDemoSetupError(f"{label}返回的数据不是对象。")
    return payload


def _expect_code(payload: dict[str, Any], expected: int, label: str) -> None:
    if payload.get("code") != expected:
        message = payload.get("message")
        suffix = f"：{message}" if isinstance(message, str) and message else ""
        raise LiveDemoSetupError(f"{label}未成功{suffix}")


def _find_address_by_phone(addresses: list[Any], telephone: str) -> dict[str, Any] | None:
    matches = [
        address
        for address in addresses
        if isinstance(address, dict) and address.get("phoneNumber") == telephone
    ]
    if not matches:
        return None
    return max(matches, key=lambda address: int(address.get("id") or 0))


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LiveDemoSetupError(f"{label}不完整。")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise LiveDemoSetupError(f"{label}不完整。")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveDemoSetupError(f"{label}不完整。")
    return value.strip()


def _machine_order_summary(order: DemoOrder) -> dict[str, Any]:
    return {
        "username": order.username,
        "member_id": order.member_id,
        "order_id": order.order_id,
        "order_sn": order.order_sn,
    }


if __name__ == "__main__":
    sys.exit(main())
