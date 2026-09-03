"""Build 06 manual verification for Java login and order ownership.

The script intentionally does not print or persist Bearer Tokens. It verifies
the deterministic authentication boundary before any LLM-dependent chat case.
Set the four account/order variables in the shell before running it.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TestAccount:
    username: str
    password: str
    own_order: str


def main() -> int:
    missing = [
        name
        for name in (
            "MALL_TEST_USER_A",
            "MALL_TEST_PASSWORD_A",
            "MALL_TEST_ORDER_A",
            "MALL_TEST_USER_B",
            "MALL_TEST_PASSWORD_B",
            "MALL_TEST_ORDER_B",
        )
        if not os.getenv(name)
    ]
    if missing:
        print("缺少验收环境变量：" + ", ".join(missing))
        print("请使用可删除的本地测试账号和各自订单，不要把密码写进脚本。")
        return 2

    ai_base = os.getenv("MALL_AI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    account_a = TestAccount(
        os.environ["MALL_TEST_USER_A"],
        os.environ["MALL_TEST_PASSWORD_A"],
        os.environ["MALL_TEST_ORDER_A"],
    )
    account_b = TestAccount(
        os.environ["MALL_TEST_USER_B"],
        os.environ["MALL_TEST_PASSWORD_B"],
        os.environ["MALL_TEST_ORDER_B"],
    )
    if account_a.own_order == account_b.own_order:
        print("验收配置错误：两个账号的订单号必须不同。")
        return 2

    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            token_a, member_a = _login_and_check(client, ai_base, account_a)
            token_b, member_b = _login_and_check(client, ai_base, account_b)
            if member_a == member_b:
                raise AssertionError("两个登录账号解析成了同一个会员。")

            _check_ai_auth_boundary(client, ai_base, token_a)
            _check_order_access(client, java_base, token_a, account_a.own_order, True)
            _check_order_access(client, java_base, token_a, account_b.own_order, False)
            _check_order_access(client, java_base, token_b, account_b.own_order, True)
            _check_order_access(client, java_base, token_b, account_a.own_order, False)
            _check_order_access(client, java_base, None, account_a.own_order, False)
            _check_order_access(client, java_base, "Bearer invalid-token", account_a.own_order, False)
    except (httpx.HTTPError, AssertionError) as exc:
        print(f"Build 06 验收失败：{exc}")
        return 1

    print("Build 06 验收通过：登录、Token 透传、两个账号归属和无效凭证边界均符合预期。")
    return 0


def _login_and_check(
    client: httpx.Client,
    ai_base: str,
    account: TestAccount,
) -> tuple[str, int]:
    response = client.post(
        f"{ai_base}/auth/login",
        json={"username": account.username, "password": account.password},
    )
    _expect_status(response, 200, f"账号 {account.username} 登录")
    payload = _json(response)
    authorization = payload.get("authorization")
    member = payload.get("member")
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise AssertionError(f"账号 {account.username} 没有得到 Bearer 凭证")
    if not isinstance(member, dict) or not isinstance(member.get("member_id"), int):
        raise AssertionError(f"账号 {account.username} 没有得到有效会员身份")

    me_response = client.get(
        f"{ai_base}/auth/me",
        headers={"Authorization": authorization},
    )
    _expect_status(me_response, 200, f"账号 {account.username} 身份回读")
    me = _json(me_response)
    if me.get("member_id") != member["member_id"]:
        raise AssertionError(f"账号 {account.username} 的身份回读不一致")
    print(f"登录通过：{account.username}（会员 {member['member_id']}）")
    return authorization, member["member_id"]


def _check_ai_auth_boundary(
    client: httpx.Client,
    ai_base: str,
    authorization: str,
) -> None:
    no_token = client.get(f"{ai_base}/auth/me")
    _expect_status(no_token, 401, "AI 身份接口拒绝无 Token")
    invalid = client.get(
        f"{ai_base}/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    _expect_status(invalid, 401, "AI 身份接口拒绝无效 Token")
    valid = client.get(f"{ai_base}/auth/me", headers={"Authorization": authorization})
    _expect_status(valid, 200, "AI 身份接口接受有效 Token")


def _check_order_access(
    client: httpx.Client,
    java_base: str,
    authorization: str | None,
    order_sn: str,
    expected_success: bool,
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = client.get(
        f"{java_base}/order/ai/detail/by-sn/{order_sn}",
        headers=headers,
    )
    payload = _json(response, allow_empty=True)
    success = response.status_code < 400 and payload.get("code") == 200
    if success != expected_success:
        raise AssertionError(
            f"订单归属验收不符：订单={order_sn}，HTTP={response.status_code}，成功={success}，"
            f"期望={expected_success}"
        )
    label = "允许" if expected_success else "拒绝"
    print(f"订单访问{label}：{order_sn}")


def _expect_status(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}失败：HTTP {response.status_code}，期望 {expected}")


def _json(response: httpx.Response, allow_empty: bool = False) -> dict:
    try:
        payload = response.json()
    except ValueError:
        if allow_empty:
            return {}
        raise AssertionError("服务返回了无法解析的 JSON")
    if not isinstance(payload, dict):
        raise AssertionError("服务返回的 JSON 不是对象")
    return payload


if __name__ == "__main__":
    sys.exit(main())
