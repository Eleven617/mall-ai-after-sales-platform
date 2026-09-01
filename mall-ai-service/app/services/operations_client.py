"""Client for the separately authenticated mall-admin operations authority."""

from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.config import settings
from app.services.request_context import correlation_headers
from app.schemas.operations import (
    CaseHandoffView,
    HandoffOverview,
    OperationsMetrics,
    OperatorLoginResponse,
    OperatorProfile,
)


class OperationsApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class OperationsAuthenticationError(OperationsApiError):
    pass


def login_operator(username: str, password: str) -> OperatorLoginResponse:
    try:
        response = httpx.post(
            f"{settings.mall_admin_api_base_url.rstrip('/')}/admin/login",
            json={"username": username, "password": password},
            timeout=settings.mall_admin_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise OperationsAuthenticationError("运营登录服务暂时不可用，请稍后重试。", status_code=503) from exc
    if response.status_code in {401, 403}:
        raise OperationsAuthenticationError("运营用户名或密码错误。", status_code=401)
    payload = _load_payload(response, "运营登录服务返回了无法解析的数据。")
    if response.status_code >= 500:
        raise OperationsAuthenticationError("运营登录服务暂时不可用，请稍后重试。", status_code=503)
    if response.status_code >= 400 or payload.get("code") != 200:
        raise OperationsAuthenticationError("运营用户名或密码错误。", status_code=401)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise OperationsAuthenticationError("运营登录服务返回的数据不完整。", status_code=502)
    token = data.get("token")
    token_head = data.get("tokenHead")
    if not isinstance(token, str) or not token.strip() or not isinstance(token_head, str):
        raise OperationsAuthenticationError("运营登录服务返回的数据不完整。", status_code=502)
    authorization = f"{token_head.strip()} {token.strip()}"
    if not authorization.startswith("Bearer "):
        raise OperationsAuthenticationError("运营登录服务返回了不支持的凭证格式。", status_code=502)
    return OperatorLoginResponse(
        authorization=authorization,
        operator=get_current_operator(authorization),
    )


def get_current_operator(authorization: str | None) -> OperatorProfile:
    response = _authorized_get("/ai/operations/me", authorization)
    data = _expect_data(response, "运营身份返回的数据不完整。")
    try:
        return OperatorProfile.model_validate(data, extra="forbid")
    except ValidationError as exc:
        raise OperationsApiError("运营身份返回的数据不完整。") from exc


def list_case_handoffs(authorization: str | None) -> list[CaseHandoffView]:
    response = _authorized_get("/ai/operations/cases?limit=50", authorization)
    data = _expect_data(response, "人工跟进列表返回的数据不完整。")
    if not isinstance(data, list):
        raise OperationsApiError("人工跟进列表返回的数据不完整。")
    try:
        return [CaseHandoffView.model_validate(item, extra="forbid") for item in data]
    except ValidationError as exc:
        raise OperationsApiError("人工跟进列表返回的数据不完整。") from exc


def get_case_handoff(case_id: str, authorization: str | None) -> CaseHandoffView:
    response = _authorized_get(
        f"/ai/operations/cases/{quote(case_id, safe='')}", authorization
    )
    data = _expect_data(response, "人工跟进事项返回的数据不完整。")
    try:
        return CaseHandoffView.model_validate(data, extra="forbid")
    except ValidationError as exc:
        raise OperationsApiError("人工跟进事项返回的数据不完整。") from exc


def get_after_sales_metrics(window_days: int, authorization: str | None) -> OperationsMetrics:
    if window_days not in {7, 30}:
        raise OperationsApiError("仅支持 7 或 30 天运营聚合窗口。", status_code=400)
    response = _authorized_get(
        f"/ai/operations/after-sales-metrics?windowDays={window_days}", authorization
    )
    data = _expect_data(response, "运营聚合返回的数据不完整。")
    try:
        return OperationsMetrics.model_validate(data, extra="forbid")
    except ValidationError as exc:
        raise OperationsApiError("运营聚合返回的数据不完整。") from exc


def get_handoff_overview(window_days: int, authorization: str | None) -> HandoffOverview:
    """Read the Java-computed handoff overview without invoking an LLM."""
    metrics = get_after_sales_metrics(window_days, authorization)
    if metrics.handoff_overview is None:
        raise OperationsApiError("转人工概览返回的数据不完整。")
    return metrics.handoff_overview


def _authorized_get(path: str, authorization: str | None) -> httpx.Response:
    if not authorization or not authorization.startswith("Bearer "):
        raise OperationsAuthenticationError("请先以运营身份登录。", status_code=401)
    try:
        response = httpx.get(
            f"{settings.mall_admin_api_base_url.rstrip('/')}{path}",
            headers={"Authorization": authorization, **correlation_headers()},
            timeout=settings.mall_admin_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise OperationsApiError("运营服务暂时不可用，请稍后重试。", status_code=503) from exc
    if response.status_code == 401:
        raise OperationsAuthenticationError("运营登录状态已失效，请重新登录。", status_code=401)
    if response.status_code == 403:
        raise OperationsAuthenticationError("当前账号没有售后运营分析权限。", status_code=403)
    if response.status_code >= 500:
        raise OperationsApiError("运营服务暂时不可用，请稍后重试。", status_code=503)
    return response


def _load_payload(response: httpx.Response, message: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OperationsApiError(message) from exc
    if not isinstance(payload, dict):
        raise OperationsApiError(message)
    return payload


def _expect_data(response: httpx.Response, message: str):
    payload = _load_payload(response, message)
    # The legacy mall-admin security filter sometimes serializes an auth error
    # as HTTP 200 with a CommonResult code. Normalize that boundary here so the
    # browser can distinguish expired credentials from an upstream failure.
    legacy_code = payload.get("code")
    if response.status_code == 401 or legacy_code == 401:
        raise OperationsAuthenticationError("运营登录状态已失效，请重新登录。", status_code=401)
    if response.status_code == 403 or legacy_code == 403:
        raise OperationsAuthenticationError("当前账号没有售后运营分析权限。", status_code=403)
    if response.status_code == 404:
        raise OperationsApiError("人工跟进事项不存在或已不可访问。", status_code=404)
    if response.status_code >= 400 or legacy_code != 200:
        raise OperationsApiError(
            payload.get("message") or "运营服务请求失败，请稍后重试。",
            status_code=403 if response.status_code == 403 else 502,
        )
    if "data" not in payload:
        raise OperationsApiError(message)
    return payload["data"]
