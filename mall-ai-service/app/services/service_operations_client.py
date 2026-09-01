"""Client for the separate, dedicated human service-processor authority."""

from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.service_case import (
    ServiceProcessorActionRequest,
    ServiceProcessorCaseView,
    ServiceProcessorClaimRequest,
    ServiceProcessorLoginResponse,
    ServiceProcessorProfile,
)
from app.services.request_context import correlation_headers


class ServiceProcessorApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class ServiceProcessorAuthenticationError(ServiceProcessorApiError):
    pass


def login_service_processor(username: str, password: str) -> ServiceProcessorLoginResponse:
    try:
        response = httpx.post(
            f"{settings.mall_admin_api_base_url.rstrip('/')}/admin/login",
            json={"username": username, "password": password},
            timeout=settings.mall_admin_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise ServiceProcessorAuthenticationError("人工处理人员登录服务暂时不可用，请稍后重试。", status_code=503) from exc
    if response.status_code in {401, 403}:
        raise ServiceProcessorAuthenticationError("用户名或密码错误。", status_code=401)
    body = _load_body(response, "人工处理人员登录服务返回了无法解析的数据。")
    if response.status_code >= 500:
        raise ServiceProcessorAuthenticationError("人工处理人员登录服务暂时不可用，请稍后重试。", status_code=503)
    data = body.get("data")
    if response.status_code >= 400 or body.get("code") != 200 or not isinstance(data, dict):
        raise ServiceProcessorAuthenticationError("用户名或密码错误。", status_code=401)
    token = data.get("token")
    token_head = data.get("tokenHead")
    if not isinstance(token, str) or not token.strip() or not isinstance(token_head, str):
        raise ServiceProcessorAuthenticationError("人工处理人员登录返回的数据不完整。")
    authorization = f"{token_head.strip()} {token.strip()}"
    if not authorization.startswith("Bearer "):
        raise ServiceProcessorAuthenticationError("人工处理人员登录返回了不支持的凭证格式。")
    return ServiceProcessorLoginResponse(
        authorization=authorization,
        processor=get_current_service_processor(authorization),
    )


def get_current_service_processor(authorization: str | None) -> ServiceProcessorProfile:
    data = _authorized_request("GET", "/ai/service-operations/me", authorization)
    try:
        return ServiceProcessorProfile.model_validate(data)
    except ValidationError as exc:
        raise ServiceProcessorApiError("人工处理人员身份返回的数据不完整。") from exc


def list_service_processor_cases(
    authorization: str | None, limit: int = 30
) -> list[ServiceProcessorCaseView]:
    if limit < 1 or limit > 50:
        raise ServiceProcessorApiError("案件列表数量不合法。", status_code=400)
    data = _authorized_request("GET", f"/ai/service-operations/cases?limit={limit}", authorization)
    if not isinstance(data, list):
        raise ServiceProcessorApiError("人工协同案件列表返回的数据不完整。")
    try:
        return [ServiceProcessorCaseView.model_validate(item) for item in data]
    except ValidationError as exc:
        raise ServiceProcessorApiError("人工协同案件列表返回的数据不完整。") from exc


def claim_service_case(
    case_id: str, request: ServiceProcessorClaimRequest, authorization: str | None
) -> ServiceProcessorCaseView:
    return _post_case(
        case_id,
        "claim",
        {"expectedVersion": request.expected_version, "idempotencyKey": request.idempotency_key},
        authorization,
    )


def act_on_service_case(
    case_id: str, request: ServiceProcessorActionRequest, authorization: str | None
) -> ServiceProcessorCaseView:
    payload: dict[str, object] = {
        "expectedVersion": request.expected_version,
        "idempotencyKey": request.idempotency_key,
        "action": request.action,
    }
    if request.information_type is not None:
        payload["informationType"] = request.information_type
    if request.public_message is not None:
        payload["publicMessage"] = request.public_message
    if request.internal_note is not None:
        payload["internalNote"] = request.internal_note
    return _post_case(case_id, "actions", payload, authorization)


def _post_case(
    case_id: str, endpoint: str, payload: dict[str, object], authorization: str | None
) -> ServiceProcessorCaseView:
    data = _authorized_request(
        "POST", f"/ai/service-operations/cases/{quote(case_id, safe='')}/{endpoint}", authorization, payload
    )
    try:
        return ServiceProcessorCaseView.model_validate(data)
    except ValidationError as exc:
        raise ServiceProcessorApiError("人工协同案件操作返回的数据不完整。") from exc


def _authorized_request(
    method: str,
    path: str,
    authorization: str | None,
    payload: dict[str, object] | None = None,
) -> object:
    if not authorization or not authorization.startswith("Bearer "):
        raise ServiceProcessorAuthenticationError("请先以售后处理人员身份登录。", status_code=401)
    try:
        response = httpx.request(
            method,
            f"{settings.mall_admin_api_base_url.rstrip('/')}{path}",
            headers={"Authorization": authorization, **correlation_headers()},
            json=payload,
            timeout=settings.mall_admin_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise ServiceProcessorApiError("人工处理服务暂时不可用，请稍后重试。", status_code=503) from exc
    if response.status_code == 401:
        raise ServiceProcessorAuthenticationError("人工处理人员登录状态已失效，请重新登录。", status_code=401)
    if response.status_code == 403:
        raise ServiceProcessorAuthenticationError("当前账号没有人工售后处理权限。", status_code=403)
    if response.status_code >= 500:
        raise ServiceProcessorApiError("人工处理服务暂时不可用，请稍后重试。", status_code=503)
    body = _load_body(response, "人工处理服务返回了无法解析的数据。")
    code = body.get("code")
    if code == 401:
        raise ServiceProcessorAuthenticationError("人工处理人员登录状态已失效，请重新登录。", status_code=401)
    if code == 403:
        raise ServiceProcessorAuthenticationError("当前账号没有人工售后处理权限。", status_code=403)
    if response.status_code == 404:
        raise ServiceProcessorApiError("案件不存在或已不可访问。", status_code=404)
    if response.status_code == 409:
        raise ServiceProcessorApiError(body.get("message") or "案件状态已变化，请刷新后重试。", status_code=409)
    if response.status_code >= 400 or code != 200:
        raise ServiceProcessorApiError(body.get("message") or "人工处理服务请求失败。", status_code=400)
    if "data" not in body:
        raise ServiceProcessorApiError("人工处理服务返回的数据不完整。")
    return body["data"]


def _load_body(response: httpx.Response, message: str) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise ServiceProcessorApiError(message) from exc
    if not isinstance(body, dict):
        raise ServiceProcessorApiError(message)
    return body
