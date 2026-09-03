"""Run a privacy-safe local live check for the Build 14 diagnosis graph.

This script is intentionally a local verification harness, not application
code. It creates two disposable users/orders through the Java APIs, then calls
the public FastAPI endpoints exactly as a browser would. It prints only a
small result summary: never passwords, Bearer tokens, member IDs, or order
numbers.

Set ``MALL_LIVE_DEMO_PASSWORD`` plus unique demo username/phone environment
variables before running. See ``bootstrap_live_demo.py`` for the supported
variables.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from bootstrap_live_demo import DemoAccount, LiveDemoSetupError, _prepare_account_order


class LiveDiagnosisVerificationError(RuntimeError):
    """Raised when a local build cannot complete its safe verification setup."""


@dataclass(frozen=True)
class VerificationAccount:
    label: str
    username: str
    password: str
    telephone: str


def main() -> int:
    password = os.getenv("MALL_LIVE_DEMO_PASSWORD")
    if not password:
        return _fail("missing MALL_LIVE_DEMO_PASSWORD")

    java_base = os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/")
    ai_base = os.getenv("MALL_AI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    product_id = int(os.getenv("MALL_LIVE_DEMO_PRODUCT_ID", "26"))
    nonce = uuid.uuid4().hex[:12]
    phone_seed = uuid.uuid4().int % 100_000_000
    accounts = (
        VerificationAccount(
            label="A",
            username=os.getenv("MALL_LIVE_DEMO_USER_A") or f"ai_demo_a_{nonce}",
            password=password,
            telephone=os.getenv("MALL_LIVE_DEMO_PHONE_A") or f"199{phone_seed:08d}",
        ),
        VerificationAccount(
            label="B",
            username=os.getenv("MALL_LIVE_DEMO_USER_B") or f"ai_demo_b_{nonce}",
            password=password,
            telephone=os.getenv("MALL_LIVE_DEMO_PHONE_B") or f"198{(phone_seed + 1) % 100_000_000:08d}",
        ),
    )

    try:
        with httpx.Client(timeout=120, trust_env=False) as client:
            orders = [
                _prepare_account_order(
                    client,
                    java_base,
                    DemoAccount(
                        label=account.label,
                        username=account.username,
                        password=account.password,
                        telephone=account.telephone,
                    ),
                    product_id,
                    required_stock=len(accounts) - index,
                )
                for index, account in enumerate(accounts)
            ]
            if orders[0].order_sn == orders[1].order_sn:
                raise LiveDiagnosisVerificationError("demo orders unexpectedly match")

            authorization_a = _login(client, ai_base, accounts[0])
            authorization_b = _login(client, ai_base, accounts[1])
            headers_a = {"Authorization": authorization_a}
            headers_b = {"Authorization": authorization_b}
            returns_before = _return_application_count(client, ai_base, headers_a)

            message = f"订单号 {orders[0].order_sn} 为什么一直没到，我现在怎么办？"
            response_a = _customer_service(client, ai_base, headers_a, "build14-live-a", message)
            response_b = _customer_service(client, ai_base, headers_b, "build14-live-b", message)
            returns_after = _return_application_count(client, ai_base, headers_a)
    except (httpx.HTTPError, LiveDemoSetupError, LiveDiagnosisVerificationError, ValueError) as exc:
        return _fail(str(exc))

    summary = _build_summary(response_a, response_b, returns_before, returns_after)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if _is_pass(summary) else 1


def _login(client: httpx.Client, ai_base: str, account: VerificationAccount) -> str:
    response = client.post(
        f"{ai_base}/auth/login",
        json={"username": account.username, "password": account.password},
    )
    response.raise_for_status()
    payload = _as_dict(response, "AI login")
    authorization = payload.get("authorization")
    if not isinstance(authorization, str) or not authorization.strip():
        raise LiveDiagnosisVerificationError(f"account {account.label} did not receive authorization")
    return authorization


def _customer_service(
    client: httpx.Client,
    ai_base: str,
    headers: dict[str, str],
    session_id: str,
    message: str,
) -> dict[str, Any]:
    response = client.post(
        f"{ai_base}/customer-service",
        headers=headers,
        json={"session_id": session_id, "message": message},
    )
    response.raise_for_status()
    return _as_dict(response, "customer-service")


def _return_application_count(
    client: httpx.Client,
    ai_base: str,
    headers: dict[str, str],
) -> int:
    response = client.get(f"{ai_base}/customer-service/return-applications", headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise LiveDiagnosisVerificationError("return application response is not a list")
    return len(payload)


def _as_dict(response: httpx.Response, label: str) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise LiveDiagnosisVerificationError(f"{label} response is not an object")
    return payload


def _build_summary(
    response_a: dict[str, Any],
    response_b: dict[str, Any],
    returns_before: int,
    returns_after: int,
) -> dict[str, Any]:
    diagnosis_a = response_a.get("diagnosis")
    facts_a = _fact_sources(response_a)
    facts_b = _fact_sources(response_b)
    return {
        "authenticated_login": True,
        "diagnosis_a": {
            "diagnosis_present": isinstance(diagnosis_a, dict),
            "diagnosis_category": diagnosis_a.get("category") if isinstance(diagnosis_a, dict) else None,
            "evidence_status": diagnosis_a.get("evidence_status") if isinstance(diagnosis_a, dict) else None,
            "controlled_handoff": bool(diagnosis_a.get("handoff")) if isinstance(diagnosis_a, dict) else False,
            "verified_fact_sources": facts_a,
            "policy_sources_count": len(response_a.get("policy_sources") or []),
            "answer_present": isinstance(response_a.get("answer"), str) and bool(response_a["answer"].strip()),
        },
        "cross_account_protection": {
            "foreign_order_fact_sources": facts_b,
            "foreign_order_facts_disclosed": bool(facts_b),
            "answer_present": isinstance(response_b.get("answer"), str) and bool(response_b["answer"].strip()),
        },
        "no_return_application_created_by_diagnosis": returns_before == returns_after,
    }


def _fact_sources(response: dict[str, Any]) -> list[str]:
    facts = response.get("verified_facts") or []
    if not isinstance(facts, list):
        return []
    return sorted(
        {
            fact.get("source")
            for fact in facts
            if isinstance(fact, dict) and isinstance(fact.get("source"), str)
        }
    )


def _is_pass(summary: dict[str, Any]) -> bool:
    diagnosis = summary["diagnosis_a"]
    protection = summary["cross_account_protection"]
    return bool(
        diagnosis["diagnosis_present"]
        and diagnosis["answer_present"]
        and "order_service" in diagnosis["verified_fact_sources"]
        and protection["answer_present"]
        and not protection["foreign_order_facts_disclosed"]
        and summary["no_return_application_created_by_diagnosis"]
    )


def _fail(message: str) -> int:
    print(json.dumps({"verification_error": message}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
