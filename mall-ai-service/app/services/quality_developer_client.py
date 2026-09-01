"""Independent Java-backed identity boundary for the developer quality page."""

import httpx
from pydantic import ValidationError

from app.config import settings
from app.services.request_context import correlation_headers
from app.schemas.quality import DeveloperLoginResponse, DeveloperProfile


class QualityDeveloperApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class QualityDeveloperAuthenticationError(QualityDeveloperApiError):
    pass


def login_quality_developer(username: str, password: str) -> DeveloperLoginResponse:
    """Obtain a Java-issued admin token then prove the dedicated role."""
    try:
        response = httpx.post(
            f"{settings.mall_admin_api_base_url.rstrip('/')}/admin/login",
            json={"username": username, "password": password},
            timeout=settings.mall_admin_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise QualityDeveloperAuthenticationError(
            "开发者登录服务暂时不可用，请稍后重试。", status_code=503
        ) from exc
    if response.status_code in {401, 403}:
        raise QualityDeveloperAuthenticationError("开发者用户名或密码错误。", status_code=401)
    payload = _load_payload(response, "开发者登录服务返回了无法解析的数据。")
    if response.status_code >= 500:
        raise QualityDeveloperAuthenticationError(
            "开发者登录服务暂时不可用，请稍后重试。", status_code=503
        )
    if response.status_code >= 400 or payload.get("code") != 200:
        raise QualityDeveloperAuthenticationError("开发者用户名或密码错误。", status_code=401)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise QualityDeveloperAuthenticationError("开发者登录返回的数据不完整。", status_code=502)
    token = data.get("token")
    token_head = data.get("tokenHead")
    if not isinstance(token, str) or not token.strip() or not isinstance(token_head, str):
        raise QualityDeveloperAuthenticationError("开发者登录返回的数据不完整。", status_code=502)
    authorization = f"{token_head.strip()} {token.strip()}"
    if not authorization.startswith("Bearer "):
        raise QualityDeveloperAuthenticationError("开发者登录返回了不支持的凭证格式。", status_code=502)
    return DeveloperLoginResponse(
        authorization=authorization,
        developer=get_current_quality_developer(authorization),
    )


def get_current_quality_developer(authorization: str | None) -> DeveloperProfile:
    response = _authorized_get("/ai/developer/me", authorization)
    data = _expect_data(response, "开发者身份返回的数据不完整。")
    try:
        return DeveloperProfile.model_validate(data, extra="forbid")
    except ValidationError as exc:
        raise QualityDeveloperApiError("开发者身份返回的数据不完整。") from exc


def _authorized_get(path: str, authorization: str | None) -> httpx.Response:
    if not authorization or not authorization.startswith("Bearer "):
        raise QualityDeveloperAuthenticationError("请先以 AI 质量开发者身份登录。", status_code=401)
    try:
        response = httpx.get(
            f"{settings.mall_admin_api_base_url.rstrip('/')}{path}",
            headers={"Authorization": authorization, **correlation_headers()},
            timeout=settings.mall_admin_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise QualityDeveloperApiError("开发者身份服务暂时不可用，请稍后重试。", status_code=503) from exc
    if response.status_code == 401:
        raise QualityDeveloperAuthenticationError("开发者登录状态已失效，请重新登录。", status_code=401)
    if response.status_code == 403:
        raise QualityDeveloperAuthenticationError("当前账号没有 AI 质量评测权限。", status_code=403)
    if response.status_code >= 500:
        raise QualityDeveloperApiError("开发者身份服务暂时不可用，请稍后重试。", status_code=503)
    return response


def _load_payload(response: httpx.Response, message: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise QualityDeveloperApiError(message) from exc
    if not isinstance(payload, dict):
        raise QualityDeveloperApiError(message)
    return payload


def _expect_data(response: httpx.Response, message: str):
    payload = _load_payload(response, message)
    legacy_code = payload.get("code")
    if response.status_code == 401 or legacy_code == 401:
        raise QualityDeveloperAuthenticationError("开发者登录状态已失效，请重新登录。", status_code=401)
    if response.status_code == 403 or legacy_code == 403:
        raise QualityDeveloperAuthenticationError("当前账号没有 AI 质量评测权限。", status_code=403)
    if response.status_code >= 400 or legacy_code != 200:
        raise QualityDeveloperApiError(
            payload.get("message") or "开发者身份服务请求失败，请稍后重试。",
            status_code=403 if response.status_code == 403 else 502,
        )
    if "data" not in payload:
        raise QualityDeveloperApiError(message)
    return payload["data"]
