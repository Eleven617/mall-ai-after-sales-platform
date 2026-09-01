"""Safe FastAPI client for Java-owned customer service-case state."""

from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.service_case import (
    CustomerServiceCaseCancelRequest,
    CustomerServiceCaseInformationRequest,
    CustomerServiceCaseReopenRequest,
    CustomerServiceCaseTimelineEntry,
    CustomerServiceCaseView,
)
from app.services.request_context import correlation_headers


class ServiceCaseApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class ServiceCaseAuthenticationError(ServiceCaseApiError):
    pass


def list_my_service_cases(authorization: str | None) -> list[CustomerServiceCaseView]:
    data = _request("GET", "/service-cases/mine", authorization)
    if not isinstance(data, list):
        raise ServiceCaseApiError("人工协同案件列表返回的数据不完整。")
    try:
        return [CustomerServiceCaseView.model_validate(item) for item in data]
    except ValidationError as exc:
        raise ServiceCaseApiError("人工协同案件列表返回的数据不完整。") from exc


def get_my_service_case_timeline(
    case_id: str, authorization: str | None
) -> list[CustomerServiceCaseTimelineEntry]:
    data = _request(
        "GET", f"/service-cases/{quote(case_id, safe='')}/timeline", authorization
    )
    if not isinstance(data, list):
        raise ServiceCaseApiError("人工协同案件进度返回的数据不完整。")
    try:
        return [CustomerServiceCaseTimelineEntry.model_validate(item) for item in data]
    except ValidationError as exc:
        raise ServiceCaseApiError("人工协同案件进度返回的数据不完整。") from exc


def submit_customer_information(
    case_id: str,
    request: CustomerServiceCaseInformationRequest,
    authorization: str | None,
) -> CustomerServiceCaseView:
    return _post_case_action(
        case_id,
        "customer-information",
        {
            "expectedVersion": request.expected_version,
            "idempotencyKey": request.idempotency_key,
            "informationType": request.information_type,
            "information": request.information,
        },
        authorization,
    )


def cancel_my_service_case(
    case_id: str,
    request: CustomerServiceCaseCancelRequest,
    authorization: str | None,
) -> CustomerServiceCaseView:
    return _post_case_action(
        case_id,
        "cancel",
        {"expectedVersion": request.expected_version, "idempotencyKey": request.idempotency_key},
        authorization,
    )


def reopen_my_service_case(
    case_id: str,
    request: CustomerServiceCaseReopenRequest,
    authorization: str | None,
) -> CustomerServiceCaseView:
    return _post_case_action(
        case_id,
        "reopen",
        {
            "expectedVersion": request.expected_version,
            "idempotencyKey": request.idempotency_key,
            "reason": request.reason,
        },
        authorization,
    )


def _post_case_action(
    case_id: str, action: str, payload: dict[str, object], authorization: str | None
) -> CustomerServiceCaseView:
    data = _request(
        "POST", f"/service-cases/{quote(case_id, safe='')}/{action}", authorization, payload
    )
    try:
        return CustomerServiceCaseView.model_validate(data)
    except ValidationError as exc:
        raise ServiceCaseApiError("人工协同案件操作返回的数据不完整。") from exc


def _request(
    method: str,
    path: str,
    authorization: str | None,
    payload: dict[str, object] | None = None,
) -> object:
    if not authorization or not authorization.startswith("Bearer "):
        raise ServiceCaseAuthenticationError("请先登录后再查看或处理人工协同事项。", status_code=401)
    try:
        response = httpx.request(
            method,
            f"{settings.mall_api_base_url.rstrip('/')}{path}",
            headers={"Authorization": authorization, **correlation_headers()},
            json=payload,
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise ServiceCaseApiError("人工协同服务暂时不可用，请稍后重试。", status_code=503) from exc
    if response.status_code == 401:
        raise ServiceCaseAuthenticationError("登录状态已失效，请重新登录。", status_code=401)
    if response.status_code == 403:
        raise ServiceCaseAuthenticationError("当前账号没有访问该人工协同事项的权限。", status_code=403)
    if response.status_code >= 500:
        raise ServiceCaseApiError("人工协同服务暂时不可用，请稍后重试。", status_code=503)
    try:
        body = response.json()
    except ValueError as exc:
        raise ServiceCaseApiError("人工协同服务返回了无法解析的数据。") from exc
    if not isinstance(body, dict):
        raise ServiceCaseApiError("人工协同服务返回了无法解析的数据。")
    code = body.get("code")
    if code == 401:
        raise ServiceCaseAuthenticationError("登录状态已失效，请重新登录。", status_code=401)
    if code == 403:
        raise ServiceCaseAuthenticationError("当前账号没有访问该人工协同事项的权限。", status_code=403)
    if response.status_code == 404:
        raise ServiceCaseApiError("人工协同事项不存在或不属于当前账号。", status_code=404)
    if response.status_code == 409:
        raise ServiceCaseApiError(body.get("message") or "案件状态已变化，请刷新后重试。", status_code=409)
    if response.status_code >= 400 or code != 200:
        raise ServiceCaseApiError(body.get("message") or "人工协同服务请求失败。", status_code=400)
    if "data" not in body:
        raise ServiceCaseApiError("人工协同服务返回的数据不完整。")
    return body["data"]
