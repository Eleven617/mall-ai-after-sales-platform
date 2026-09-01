"""Verify public local endpoints after Docker Compose starts the demo stack."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable

import httpx


@dataclass(frozen=True)
class EndpointCheck:
    name: str
    url: str
    validator: Callable[[httpx.Response], bool]


def main() -> int:
    checks = (
        EndpointCheck(
            "Vue 页面",
            os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173"),
            _is_web_page,
        ),
        EndpointCheck(
            "FastAPI 就绪检查",
            os.getenv("MALL_AI_BASE_URL", "http://127.0.0.1:8000").rstrip("/") + "/health/ready",
            _is_fastapi_ready,
        ),
        EndpointCheck(
            "Java mall-portal 健康检查",
            os.getenv("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085").rstrip("/") + "/actuator/health",
            _is_java_ready,
        ),
    )
    reports: list[dict[str, str | bool]] = []
    try:
        with httpx.Client(timeout=5, follow_redirects=True) as client:
            for check in checks:
                reports.append(_check_endpoint(client, check))
    except httpx.HTTPError as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}, ensure_ascii=False))
        return 1

    passed = all(report["passed"] for report in reports)
    print(json.dumps({"status": "passed" if passed else "failed", "checks": reports}, ensure_ascii=False))
    return 0 if passed else 1


def _check_endpoint(client: httpx.Client, check: EndpointCheck) -> dict[str, str | bool]:
    try:
        response = client.get(check.url)
        passed = bool(check.validator(response))
    except httpx.HTTPError:
        passed = False
    return {"name": check.name, "passed": passed}


def _is_web_page(response: httpx.Response) -> bool:
    return response.status_code == 200 and "text/html" in response.headers.get("content-type", "")


def _is_fastapi_ready(response: httpx.Response) -> bool:
    return response.status_code == 200 and _json_status(response, "ok")


def _is_java_ready(response: httpx.Response) -> bool:
    return response.status_code == 200 and _json_status(response, "UP")


def _json_status(response: httpx.Response, expected: str) -> bool:
    try:
        payload: Any = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("status") == expected


if __name__ == "__main__":
    sys.exit(main())
