"""mall Java 后端 API Client。

AI 服务不直接访问数据库，只携带用户原始 Bearer Token 调用 Java 业务接口。
订单归属和 JWT 校验仍由 Java 服务负责，避免模型或客户端伪造 user_id。
"""
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.config import settings
from app.services.request_context import correlation_headers
from app.schemas.authentication import CustomerLoginResponse, MemberProfile
from app.schemas.after_sales_application import (
    AfterSalesApplicationType,
    AfterSalesApplicationView,
    AfterSalesEligibilityView,
)


class MallApiClientError(RuntimeError):
    """Java 业务服务调用失败时返回给上层的受控错误。"""


class MallOrderNotAccessibleError(MallApiClientError):
    """The requested order is not visible to the currently authenticated member."""


class MallAfterSalesSubmissionUnknownError(MallApiClientError):
    """A generic after-sales write may have committed without a final reply."""


class MallAfterSalesActionUnknownError(MallApiClientError):
    """A confirmed cancel/modify may have committed without a final reply."""


class MallAuthenticationError(MallApiClientError):
    """A safe authentication error plus the HTTP status FastAPI should expose."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def login_member(username: str, password: str) -> CustomerLoginResponse:
    """Forward credentials to Java; FastAPI never creates or signs a JWT."""
    url = f"{settings.mall_api_base_url.rstrip('/')}/sso/login"
    try:
        response = httpx.post(
            url,
            data={"username": username, "password": password},
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallAuthenticationError("登录服务暂时不可用，请稍后重试。", 503) from exc

    if response.status_code in {401, 403}:
        raise MallAuthenticationError("用户名或密码错误。", 401)
    payload = _load_auth_payload(response, "登录服务返回了无法解析的数据。")
    if response.status_code >= 500:
        raise MallAuthenticationError("登录服务暂时不可用，请稍后重试。", 503)
    if response.status_code >= 400 or payload.get("code") != 200:
        raise MallAuthenticationError("用户名或密码错误。", 401)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise MallAuthenticationError("登录服务返回的数据不完整。", 502)
    token = data.get("token")
    token_head = data.get("tokenHead")
    if not isinstance(token, str) or not token.strip() or not isinstance(token_head, str):
        raise MallAuthenticationError("登录服务返回的数据不完整。", 502)

    authorization = f"{token_head.strip()} {token.strip()}"
    if not authorization.startswith("Bearer "):
        raise MallAuthenticationError("登录服务返回了不支持的凭证格式。", 502)

    return CustomerLoginResponse(
        authorization=authorization,
        member=get_current_member(authorization),
    )


def get_current_member(authorization: str | None) -> MemberProfile:
    """Ask Java to validate the supplied Token and expose only a small profile."""
    if not authorization or not authorization.startswith("Bearer "):
        raise MallAuthenticationError("请先登录后再继续。", 401)

    url = f"{settings.mall_api_base_url.rstrip('/')}/sso/info"
    try:
        response = httpx.get(
            url,
            headers=_java_headers(authorization),
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallAuthenticationError("登录状态暂时无法验证，请稍后重试。", 503) from exc

    if response.status_code in {401, 403}:
        raise MallAuthenticationError("登录状态已失效，请重新登录后再试。", 401)
    payload = _load_auth_payload(response, "登录服务返回了无法解析的数据。")
    if response.status_code >= 500:
        raise MallAuthenticationError("登录状态暂时无法验证，请稍后重试。", 503)
    if payload.get("code") != 200:
        raise MallAuthenticationError("登录状态已失效，请重新登录后再试。", 401)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise MallAuthenticationError("登录服务返回的数据不完整。", 502)
    member_id = data.get("id")
    username = data.get("username")
    if isinstance(member_id, bool) or not isinstance(member_id, int):
        raise MallAuthenticationError("登录服务返回的数据不完整。", 502)
    if not isinstance(username, str) or not username.strip():
        raise MallAuthenticationError("登录服务返回的数据不完整。", 502)
    try:
        return MemberProfile(member_id=member_id, username=username.strip())
    except ValidationError as exc:
        # Java is the identity authority, but malformed upstream data must not
        # become an unhandled FastAPI 500 response.
        raise MallAuthenticationError("登录服务返回的数据不完整。", 502) from exc


def _load_auth_payload(response: httpx.Response, parse_error: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MallAuthenticationError(parse_error, 502) from exc
    if not isinstance(payload, dict):
        raise MallAuthenticationError(parse_error, 502)
    return payload


def check_after_sales_eligibility(
    order_sn: str,
    application_type: AfterSalesApplicationType,
    authorization: str | None,
    order_item_id: int | None = None,
) -> AfterSalesEligibilityView:
    """Ask Java for factual admission to an after-sales request.

    This is intentionally a read: policy explanation remains in RAG and final
    approval remains a later business lifecycle state.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再核验售后资格。")
    payload: dict[str, object] = {
        "orderSn": order_sn,
        "applicationType": application_type,
    }
    if order_item_id is not None:
        payload["orderItemId"] = order_item_id
    return _post_java_model(
        "/after-sales/ai/eligibility",
        payload,
        authorization,
        AfterSalesEligibilityView,
        "售后资格核验失败，请稍后重试。",
    )


def create_after_sales_application(
    *,
    order_sn: str,
    application_type: AfterSalesApplicationType,
    order_item_id: int | None,
    reason: str,
    description: str,
    idempotency_key: str,
    authorization: str | None,
) -> AfterSalesApplicationView:
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再提交售后申请。")
    payload: dict[str, object] = {
        "orderSn": order_sn,
        "applicationType": application_type,
        "reason": reason,
        "description": description,
        "idempotencyKey": idempotency_key,
    }
    if order_item_id is not None:
        payload["orderItemId"] = order_item_id
    url = f"{settings.mall_api_base_url.rstrip('/')}/after-sales/ai/applications"
    try:
        response = httpx.post(
            url,
            headers=_after_sales_headers(authorization),
            json=payload,
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallAfterSalesSubmissionUnknownError(
            "售后服务响应中断，正在确认提交结果。"
        ) from exc
    if response.status_code in {401, 403}:
        raise MallApiClientError("登录状态已失效或无权提交该售后申请。")
    if response.status_code >= 500:
        raise MallAfterSalesSubmissionUnknownError(
            "售后服务未返回最终结果，正在确认提交状态。"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise MallAfterSalesSubmissionUnknownError(
            "售后服务返回异常，正在确认提交状态。"
        ) from exc
    if not isinstance(body, dict) or response.status_code >= 400 or body.get("code") != 200:
        message = body.get("message") if isinstance(body, dict) else None
        if "正在处理中" in str(message) or "结果无法确认" in str(message):
            raise MallAfterSalesSubmissionUnknownError("售后服务正在确认提交结果。")
        raise MallApiClientError(message or "售后申请提交失败，请稍后重试。")
    try:
        return _parse_after_sales_application_view(body.get("data"))
    except MallApiClientError as exc:
        raise MallAfterSalesSubmissionUnknownError(
            "售后服务返回的数据不完整，正在确认提交状态。"
        ) from exc


def get_after_sales_submission_status(
    idempotency_key: str,
    authorization: str | None,
) -> tuple[str, AfterSalesApplicationView | None]:
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再确认售后申请状态。")
    if len(idempotency_key) != 32 or any(
        character not in "0123456789abcdef" for character in idempotency_key
    ):
        raise MallApiClientError("售后提交标识不合法。")
    url = (
        f"{settings.mall_api_base_url.rstrip('/')}"
        f"/after-sales/ai/submissions/{quote(idempotency_key, safe='')}"
    )
    body = _get_java_payload(url, authorization, "售后提交状态暂时无法确认，请稍后重试。")
    data = body.get("data")
    if not isinstance(data, dict):
        raise MallApiClientError("售后提交状态返回的数据不完整。")
    status = data.get("status")
    if status not in {"created", "not_found"}:
        raise MallApiClientError("售后提交状态返回的数据不完整。")
    if status != "created":
        return status, None
    return status, _parse_after_sales_application_view(data.get("application"))


def list_my_after_sales_applications(
    authorization: str | None,
) -> list[AfterSalesApplicationView]:
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再查看售后记录。")
    url = f"{settings.mall_api_base_url.rstrip('/')}/after-sales/ai/applications"
    body = _get_java_payload(url, authorization, "售后记录查询失败，请稍后重试。")
    data = body.get("data")
    if not isinstance(data, list):
        raise MallApiClientError("售后记录返回的数据不完整。")
    try:
        return [AfterSalesApplicationView.model_validate(item) for item in data]
    except ValidationError as exc:
        raise MallApiClientError("售后记录返回的数据不完整。") from exc


def execute_after_sales_action(
    *,
    action_id: str,
    action: str,
    application_id: int,
    content_hash: str,
    reason: str | None,
    description: str | None,
    authorization: str | None,
) -> AfterSalesApplicationView:
    """Call Java only after a server-held pending action was explicitly confirmed.

    ``action_id`` and ``content_hash`` are not browser inputs.  They are kept
    in the owner/session-bound Redis state and let Java distinguish a safe retry
    from an altered request after a timeout or malformed response.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再执行售后操作。")
    if action not in {"cancel", "modify"}:
        raise MallApiClientError("售后操作类型不合法。")
    if not _is_hex(action_id, 32) or not _is_hex(content_hash, 64):
        raise MallApiClientError("售后操作确认标识不合法。")
    if not isinstance(application_id, int) or application_id <= 0:
        raise MallApiClientError("售后申请标识不合法。")
    payload: dict[str, object] = {
        "actionId": action_id,
        "contentHash": content_hash,
    }
    if action == "modify":
        if reason is not None:
            payload["reason"] = reason
        if description is not None:
            payload["description"] = description
        path = f"/after-sales/ai/applications/{application_id}"
        method = "PUT"
    else:
        path = f"/after-sales/ai/applications/{application_id}/cancel"
        method = "POST"
    url = f"{settings.mall_api_base_url.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method,
            url,
            headers=_after_sales_headers(authorization),
            json=payload,
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallAfterSalesActionUnknownError("售后操作响应中断，正在确认执行结果。") from exc
    if response.status_code in {401, 403}:
        raise MallApiClientError("登录状态已失效或无权执行该售后操作。")
    if response.status_code >= 500:
        raise MallAfterSalesActionUnknownError("售后服务未返回最终结果，正在确认执行状态。")
    try:
        body = response.json()
    except ValueError as exc:
        raise MallAfterSalesActionUnknownError("售后服务返回异常，正在确认执行状态。") from exc
    if not isinstance(body, dict) or response.status_code >= 400 or body.get("code") != 200:
        message = body.get("message") if isinstance(body, dict) else None
        if "正在处理中" in str(message) or "结果无法确认" in str(message):
            raise MallAfterSalesActionUnknownError("售后服务正在确认操作结果。")
        raise MallApiClientError(message or "售后操作失败，请稍后重试。")
    try:
        return _parse_after_sales_application_view(body.get("data"))
    except MallApiClientError as exc:
        raise MallAfterSalesActionUnknownError("售后服务返回的数据不完整，正在确认执行状态。") from exc


def get_after_sales_action_status(
    action_id: str,
    authorization: str | None,
) -> tuple[str, AfterSalesApplicationView | None]:
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再确认售后操作状态。")
    if not _is_hex(action_id, 32):
        raise MallApiClientError("售后操作确认标识不合法。")
    url = (
        f"{settings.mall_api_base_url.rstrip('/')}"
        f"/after-sales/ai/actions/{quote(action_id, safe='')}"
    )
    body = _get_java_payload(url, authorization, "售后操作状态暂时无法确认，请稍后重试。")
    data = body.get("data")
    if not isinstance(data, dict):
        raise MallApiClientError("售后操作状态返回的数据不完整。")
    status = data.get("status")
    if status not in {"completed", "not_found"}:
        raise MallApiClientError("售后操作状态返回的数据不完整。")
    if status != "completed":
        return status, None
    return status, _parse_after_sales_application_view(data.get("application"))


def _parse_after_sales_application_view(data: object) -> AfterSalesApplicationView:
    if not isinstance(data, dict):
        raise MallApiClientError("售后申请未创建，请稍后重试。")
    try:
        return AfterSalesApplicationView.model_validate(data)
    except ValidationError as exc:
        raise MallApiClientError("售后服务返回的数据不完整。") from exc


def _is_hex(value: str, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        character in "0123456789abcdef" for character in value
    )


def _post_java_model(
    path: str,
    payload: dict[str, object],
    authorization: str,
    model: type[AfterSalesEligibilityView] | type[AfterSalesApplicationView],
    fallback_message: str,
) -> AfterSalesEligibilityView | AfterSalesApplicationView:
    return _request_java_model(
        method="POST",
        path=path,
        payload=payload,
        authorization=authorization,
        model=model,
        fallback_message=fallback_message,
    )


def _request_java_model(
    *,
    method: str,
    path: str,
    payload: dict[str, object],
    authorization: str,
    model: type[AfterSalesEligibilityView] | type[AfterSalesApplicationView],
    fallback_message: str,
    include_capability: bool = False,
) -> AfterSalesEligibilityView | AfterSalesApplicationView:
    url = f"{settings.mall_api_base_url.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method,
            url,
            headers=(
                _after_sales_headers(authorization)
                if include_capability
                else _java_headers(authorization)
            ),
            json=payload,
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallApiClientError(fallback_message) from exc
    if response.status_code == 401:
        raise MallApiClientError("登录状态已失效，请重新登录后再试。")
    if response.status_code == 403:
        raise MallApiClientError("你没有执行该售后操作的权限。")
    try:
        body = response.json()
    except ValueError as exc:
        raise MallApiClientError(fallback_message) from exc
    if not isinstance(body, dict) or response.status_code >= 400 or body.get("code") != 200:
        message = body.get("message") if isinstance(body, dict) else None
        raise MallApiClientError(message or fallback_message)
    try:
        return model.model_validate(body.get("data"))
    except ValidationError as exc:
        raise MallApiClientError("售后服务返回的数据不完整。") from exc


def _after_sales_headers(authorization: str) -> dict[str, str]:
    """Attach FastAPI's capability only to the unified after-sales facade."""
    return {
        "Authorization": authorization,
        "X-AI-After-Sales-Key": settings.ai_after_sales_service_key,
        **correlation_headers(),
    }


def _java_headers(authorization: str) -> dict[str, str]:
    """Forward only trusted auth plus opaque correlation context to Java."""

    return {"Authorization": authorization, **correlation_headers()}


def _get_java_payload(
    url: str,
    authorization: str,
    fallback_message: str,
) -> dict:
    try:
        response = httpx.get(
            url,
            headers=_java_headers(authorization),
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallApiClientError(fallback_message) from exc
    if response.status_code == 401:
        raise MallApiClientError("登录状态已失效，请重新登录后再试。")
    if response.status_code == 403:
        raise MallApiClientError("你没有查看该售后信息的权限。")
    try:
        body = response.json()
    except ValueError as exc:
        raise MallApiClientError(fallback_message) from exc
    if not isinstance(body, dict) or response.status_code >= 400 or body.get("code") != 200:
        message = body.get("message") if isinstance(body, dict) else None
        raise MallApiClientError(message or fallback_message)
    return body


def get_order_snapshot(order_sn: str, authorization: str | None) -> dict:
    """查询当前登录用户可供 AI 使用的最小订单摘要。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise MallApiClientError("请先登录后再查询订单。")

    url = (
        f"{settings.mall_api_base_url.rstrip('/')}"
        f"/order/ai/detail/by-sn/{quote(order_sn, safe='')}"
    )

    try:
        response = httpx.get(
            url,
            headers=_java_headers(authorization),
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise MallApiClientError("订单服务暂时不可用，请稍后重试。") from exc

    if response.status_code == 401:
        raise MallApiClientError("登录状态已失效，请重新登录后再试。")
    if response.status_code == 403:
        raise MallApiClientError("你没有查询该订单的权限。")
    if response.status_code >= 500:
        raise MallApiClientError("订单服务暂时不可用，请稍后重试。")

    try:
        payload = response.json()
    except ValueError as exc:
        raise MallApiClientError("订单服务返回了无法解析的数据。") from exc

    if response.status_code >= 400 or payload.get("code") != 200:
        message = payload.get("message") or "订单查询失败，请稍后重试。"
        # The Java endpoint intentionally combines "does not exist" and
        # "does not belong to this member".  Preserve that non-enumerating
        # boundary and give the diagnosis graph a typed, non-escalating result.
        if isinstance(message, str) and "订单不存在或无权访问" in message:
            raise MallOrderNotAccessibleError(
                "未找到当前账号可查询的订单，请核对订单号后重试。"
            )
        raise MallApiClientError(message)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise MallApiClientError("订单服务返回了不完整的数据。")

    order_items = [
        {
            "order_item_id": item.get("orderItemId"),
            "product_name": item.get("productName"),
            "product_attr": item.get("productAttr"),
            "product_quantity": item.get("productQuantity"),
        }
        for item in data.get("orderItems", [])
        if isinstance(item, dict)
    ]

    return {
        "order_sn": data.get("orderSn"),
        "status_code": data.get("status"),
        "status": data.get("statusText"),
        "delivery_company": data.get("deliveryCompany"),
        "tracking_no": data.get("deliverySn"),
        "product_names": data.get("productNames") or [],
        "order_items": order_items,
    }
