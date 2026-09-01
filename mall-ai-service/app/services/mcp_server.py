"""Small Streamable-HTTP JSON-RPC adapter for the read-only MCP catalog."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable

from pydantic import ValidationError

from app.schemas.mcp import McpInitializeParams, McpJsonRpcRequest, McpToolCallParams
from app.services.mcp_context_resolver import McpAccessScope, McpContextError, resolve_mcp_access_scope
from app.services.mcp_tool_catalog import McpToolError, execute_mcp_tool, list_mcp_tools
from app.services.reliability_service import reliability_governor


MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_PROTOCOL_HEADER = "MCP-Protocol-Version"
MCP_SERVER_NAME = "mall-readonly-after-sales"
MCP_SERVER_VERSION = "1.0.0"
MCP_SESSION_HEADER = "Mcp-Session-Id"
MCP_SESSION_TTL_SECONDS = 30 * 60


class McpProtocolError(RuntimeError):
    def __init__(self, message: str, *, code: int) -> None:
        super().__init__(message)
        self.code = code


class McpSessionError(RuntimeError):
    """A Streamable HTTP session is missing, expired, or bound to another subject."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class _McpSession:
    subject_ref: str
    expires_at: float


class McpSessionStore:
    """Small opaque-session store with no token or customer payload retention.

    Each request still resolves the bearer credential with Java-backed clients;
    the session is a protocol continuity check, never an authorization cache.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = MCP_SESSION_TTL_SECONDS,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._now_fn = now_fn or time.monotonic
        self._sessions: OrderedDict[str, _McpSession] = OrderedDict()
        self._lock = RLock()

    def open(self, scope: McpAccessScope) -> str:
        session_id = secrets.token_urlsafe(24)
        with self._lock:
            self._purge_expired_locked()
            self._sessions[session_id] = _McpSession(
                subject_ref=_scope_ref(scope),
                expires_at=self._now_fn() + self._ttl_seconds,
            )
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > 200:
                self._sessions.popitem(last=False)
        return session_id

    def require(self, session_id: str | None, scope: McpAccessScope) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise McpSessionError("MCP 会话缺失，请先调用 initialize。", status_code=400)
        with self._lock:
            self._purge_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise McpSessionError("MCP 会话不存在或已失效，请重新初始化。", status_code=404)
            if session.subject_ref != _scope_ref(scope):
                # Do not disclose the owner of an opaque session reference.
                raise McpSessionError("MCP 会话不存在或已失效，请重新初始化。", status_code=404)
            self._sessions.move_to_end(session_id)

    def close(self, session_id: str | None, scope: McpAccessScope) -> None:
        self.require(session_id, scope)
        assert session_id is not None
        with self._lock:
            self._sessions.pop(session_id, None)

    def _purge_expired_locked(self) -> None:
        now = self._now_fn()
        for session_id, session in list(self._sessions.items()):
            if session.expires_at <= now:
                self._sessions.pop(session_id, None)


def _scope_ref(scope: McpAccessScope) -> str:
    # ``principal_fingerprint`` is derived only after Java validates the
    # credential.  In particular, two operations accounts no longer collapse
    # to the former shared ``operator`` subject.
    return hashlib.sha256(scope.principal_fingerprint.encode("utf-8")).hexdigest()[:24]


mcp_session_store = McpSessionStore()


def handle_mcp_request(
    payload: object,
    authorization: str | None,
    *,
    scope: McpAccessScope | None = None,
) -> tuple[int, dict[str, Any] | None]:
    """Execute one authenticated JSON-RPC request without exposing internals."""

    request = _parse_request(payload)
    scope = scope or resolve_mcp_access_scope(authorization)
    reliability_governor.check_rate_limit(
        actor_scope=f"{scope.subject_kind}:{scope.principal_fingerprint}",
        role="operations_analysis" if scope.subject_kind == "operator" else "unified_after_sales",
        action="mcp_read",
    )
    if request.method == "notifications/initialized":
        if "id" in request.model_fields_set:
            raise McpProtocolError("通知请求不能携带 id。", code=-32600)
        if request.params:
            raise McpProtocolError("初始化通知不接受参数。", code=-32602)
        return 202, None
    if "id" not in request.model_fields_set or request.id is None:
        raise McpProtocolError("MCP 请求必须携带非空 id。", code=-32600)
    if request.method == "initialize":
        params = _parse_params(McpInitializeParams, request.params)
        if params.protocol_version != MCP_PROTOCOL_VERSION:
            raise McpProtocolError("不支持的 MCP 协议版本。", code=-32602)
        return 200, _success(
            request.id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            },
        )
    if request.method == "tools/list":
        if request.params:
            raise McpProtocolError("tools/list 不接受参数。", code=-32602)
        return 200, _success(request.id, {"tools": list_mcp_tools(scope)})
    if request.method == "tools/call":
        params = _parse_params(McpToolCallParams, request.params)
        result = execute_mcp_tool(name=params.name, arguments=params.arguments, scope=scope)
        return 200, _success(
            request.id,
            {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result,
                "isError": False,
            },
        )
    raise McpProtocolError("未注册的 MCP 方法。", code=-32601)


def protocol_error_response(error: McpProtocolError, request_id: str | int | None = None) -> dict[str, Any]:
    return _error(request_id, error.code, str(error))


def context_error_response(error: McpContextError, request_id: str | int | None = None) -> dict[str, Any]:
    return _error(request_id, -32001, str(error))


def tool_error_response(error: McpToolError, request_id: str | int | None = None) -> dict[str, Any]:
    return _error(request_id, -32602 if error.code == "invalid_arguments" else -32002, str(error))


def _parse_request(payload: object) -> McpJsonRpcRequest:
    if not isinstance(payload, dict):
        raise McpProtocolError("MCP 请求必须是 JSON 对象。", code=-32600)
    try:
        return McpJsonRpcRequest.model_validate(payload)
    except ValidationError as exc:
        raise McpProtocolError("MCP JSON-RPC 请求不符合契约。", code=-32600) from exc


def _parse_params(model: type[Any], value: dict[str, Any]) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise McpProtocolError("MCP 方法参数不符合契约。", code=-32602) from exc


def _success(request_id: str | int | None, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
