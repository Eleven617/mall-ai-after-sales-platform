"""Java-backed customer history client.

The AI service never receives a member id from the browser. It forwards the
Java-issued Bearer token and Java enforces ownership for every list/read/delete
operation.
"""
import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.conversation_history import (
    ConversationHistoryDetail,
    ConversationHistoryMessage,
    ConversationHistorySummary,
)
from app.schemas.customer_service import CustomerServicePublicResponse
from app.services.mall_client import MallApiClientError


class ConversationHistoryError(MallApiClientError):
    """A controlled error from the Java member-scoped history surface."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def create_customer_conversation(
    conversation_id: str,
    authorization: str | None,
) -> ConversationHistorySummary:
    data = _request_data(
        "POST",
        "/ai/conversations",
        authorization,
        params={"conversationId": conversation_id},
    )
    return _summary(data)


def list_customer_conversations(
    authorization: str | None,
) -> list[ConversationHistorySummary]:
    data = _request_data("GET", "/ai/conversations", authorization)
    if not isinstance(data, list):
        raise ConversationHistoryError("历史会话服务返回的数据不完整。")
    try:
        return [ConversationHistorySummary.model_validate(item) for item in data]
    except ValidationError as exc:
        raise ConversationHistoryError("历史会话服务返回的数据不完整。") from exc


def get_customer_conversation(
    conversation_id: str,
    authorization: str | None,
) -> ConversationHistoryDetail:
    data = _request_data("GET", f"/ai/conversations/{conversation_id}", authorization)
    if not isinstance(data, dict):
        raise ConversationHistoryError("历史会话服务返回的数据不完整。")
    try:
        messages = [
            _history_message(item)
            for item in data.get("messages", [])
            if isinstance(item, dict)
        ]
        return ConversationHistoryDetail(
            conversation=ConversationHistorySummary.model_validate(data.get("conversation")),
            messages=messages,
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise ConversationHistoryError("历史会话服务返回的数据不完整。") from exc


def delete_customer_conversation(conversation_id: str, authorization: str | None) -> None:
    _request_data("DELETE", f"/ai/conversations/{conversation_id}", authorization)


def append_customer_conversation_exchange(
    *,
    conversation_id: str,
    title: str,
    user_message: str,
    assistant_message: str,
    public_response: CustomerServicePublicResponse,
    authorization: str | None,
) -> None:
    # Serialize the already-projected public DTO. Never serialize the internal
    # orchestration response, RAG context, trace, tool payload or token.
    payload = {
        "title": title,
        "messages": [
            {"role": "user", "content": user_message},
            {
                "role": "assistant",
                "content": assistant_message,
                "publicResponseJson": public_response.model_dump_json(),
            },
        ],
    }
    _request_data(
        "POST",
        f"/ai/conversations/{conversation_id}/transcript",
        authorization,
        json=payload,
        service_key=True,
    )


def _summary(value: object) -> ConversationHistorySummary:
    try:
        return ConversationHistorySummary.model_validate(value)
    except ValidationError as exc:
        raise ConversationHistoryError("历史会话服务返回的数据不完整。") from exc


def _history_message(value: dict[str, Any]) -> ConversationHistoryMessage:
    # Java returns association fields (conversationId and sequenceNo) because
    # they are needed internally for persistence ordering. Do not pass those
    # through a strict customer DTO; project only the customer-visible fields.
    response_json = value.get("publicResponseJson", value.get("public_response_json"))
    parsed_response: CustomerServicePublicResponse | None = None
    if response_json is not None:
        if not isinstance(response_json, str):
            raise ConversationHistoryError("历史会话服务返回的数据不完整。")
        try:
            parsed_response = CustomerServicePublicResponse.model_validate(json.loads(response_json))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ConversationHistoryError("历史会话服务返回的数据不完整。") from exc
    return ConversationHistoryMessage.model_validate(
        {
            "message_id": value.get("messageId", value.get("message_id")),
            "role": value.get("role"),
            "content": value.get("content"),
            "created_at": value.get("createdAt", value.get("created_at")),
            "public_response": parsed_response,
        }
    )


def _request_data(
    method: str,
    path: str,
    authorization: str | None,
    *,
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    service_key: bool = False,
) -> object:
    if not authorization or not authorization.startswith("Bearer "):
        raise ConversationHistoryError("请先登录后再查看历史会话。")
    headers = {"Authorization": authorization}
    if service_key:
        headers["X-AI-Handoff-Key"] = settings.ai_case_handoff_service_key
    url = f"{settings.mall_api_base_url.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            timeout=settings.mall_api_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise ConversationHistoryError("历史会话服务暂时不可用，请稍后重试。") from exc
    if response.status_code == 401:
        raise ConversationHistoryError("登录状态已失效，请重新登录后再试。", status_code=401)
    if response.status_code == 403:
        raise ConversationHistoryError("你没有访问该历史会话的权限。", status_code=403)
    if response.status_code == 404:
        raise ConversationHistoryError("历史会话不存在或已无法访问。", status_code=404)
    if response.status_code >= 500:
        raise ConversationHistoryError("历史会话服务暂时不可用，请稍后重试。", status_code=503)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ConversationHistoryError("历史会话服务返回了无法解析的数据。") from exc
    if not isinstance(payload, dict) or response.status_code >= 400 or payload.get("code") != 200:
        # Legacy Java errors are sometimes returned as CommonResult failures
        # with HTTP 200.  Do not forward a raw upstream message to the browser.
        # A denied or missing conversation deliberately has one indistinguishable
        # response so a member cannot probe another member's UUID.
        legacy_code = payload.get("code") if isinstance(payload, dict) else None
        if legacy_code in {401, 403}:
            raise ConversationHistoryError("你没有访问该历史会话的权限。", status_code=int(legacy_code))
        raise ConversationHistoryError("历史会话请求未完成，请稍后重试。")
    return payload.get("data")
