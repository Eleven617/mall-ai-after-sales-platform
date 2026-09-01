"""Authenticated, read-only Streamable HTTP MCP endpoint."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.mcp_context_resolver import McpContextError, resolve_mcp_access_scope
from app.services.mcp_server import (
    MCP_SESSION_HEADER,
    MCP_PROTOCOL_HEADER,
    MCP_PROTOCOL_VERSION,
    McpProtocolError,
    McpSessionError,
    context_error_response,
    handle_mcp_request,
    mcp_session_store,
    protocol_error_response,
    tool_error_response,
)
from app.services.mcp_tool_catalog import McpToolError
from app.services.reliability_service import (
    RateLimitExceeded,
    ReliabilityBackendUnavailable,
    reliability_governor,
)


router = APIRouter(prefix="/mcp", tags=["mcp-readonly"])
_MCP_HEADERS = {MCP_PROTOCOL_HEADER: MCP_PROTOCOL_VERSION, "Cache-Control": "no-store"}
_MCP_ACCEPT_TYPES = {"application/json", "text/event-stream"}


@router.get("/health")
def mcp_health() -> dict[str, str]:
    """A non-sensitive readiness endpoint; it never reveals data or tools."""

    return {"status": "ready", "protocolVersion": MCP_PROTOCOL_VERSION}


@router.post("")
async def mcp_post(
    request: Request,
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias=MCP_SESSION_HEADER),
    mcp_protocol_version: str | None = Header(default=None, alias=MCP_PROTOCOL_HEADER),
) -> Response:
    """Serve one authenticated Streamable HTTP JSON-RPC request.

    The transport is session-aware but authorization remains per-request.  It
    only emits JSON (never a stream of business data) because all six exposed
    tools are bounded, read-only fact queries.
    """

    started_at = time.monotonic()
    if not _accepts_streamable_mcp(request.headers.get("accept")):
        return _transport_error(
            status_code=406,
            code=-32000,
            message="MCP Accept 必须同时允许 application/json 与 text/event-stream。",
        )
    if not _is_json_content_type(request.headers.get("content-type")):
        return _transport_error(
            status_code=415,
            code=-32000,
            message="MCP 请求 Content-Type 必须是 application/json。",
        )
    try:
        payload: object = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _transport_error(
            status_code=400,
            code=-32700,
            message="MCP JSON 请求无法解析。",
        )
    request_id = payload.get("id") if isinstance(payload, dict) else None
    response_session_id: str | None = None
    try:
        method = payload.get("method") if isinstance(payload, dict) else None
        _require_protocol_version(
            mcp_protocol_version,
            initializing=method == "initialize",
        )
        scope = resolve_mcp_access_scope(authorization)
        if method == "initialize":
            if mcp_session_id:
                raise McpSessionError("initialize 不接受已有 MCP 会话。", status_code=400)
            status_code, body = handle_mcp_request(payload, authorization, scope=scope)
            response_session_id = mcp_session_store.open(scope)
        else:
            mcp_session_store.require(mcp_session_id, scope)
            response_session_id = mcp_session_id
            status_code, body = handle_mcp_request(payload, authorization, scope=scope)
        reliability_governor.record_request(
            "mcp_read", succeeded=True, duration_ms=_elapsed_ms(started_at)
        )
        headers = _response_headers(response_session_id)
        if body is None:
            return Response(status_code=status_code, headers=headers)
        return JSONResponse(status_code=status_code, content=body, headers=headers)
    except McpSessionError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": str(exc)},
            },
            headers=_response_headers(response_session_id),
        )
    except McpContextError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=context_error_response(exc, request_id),
            headers=_response_headers(response_session_id),
        )
    except McpToolError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return JSONResponse(
            status_code=400,
            content=tool_error_response(exc, request_id),
            headers=_response_headers(response_session_id),
        )
    except McpProtocolError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return JSONResponse(
            status_code=400,
            content=protocol_error_response(exc, request_id),
            headers=_response_headers(response_session_id),
        )
    except RateLimitExceeded as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return JSONResponse(
            status_code=429,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32003, "message": str(exc)},
            },
            headers={**_response_headers(response_session_id), "Retry-After": str(exc.retry_after_seconds)},
        )
    except ReliabilityBackendUnavailable:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return JSONResponse(
            status_code=503,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32004, "message": "MCP 只读保护暂时不可用，请稍后重试。"},
            },
            headers=_response_headers(response_session_id),
        )


@router.get("")
async def mcp_get(
    request: Request,
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias=MCP_SESSION_HEADER),
    mcp_protocol_version: str | None = Header(default=None, alias=MCP_PROTOCOL_HEADER),
) -> Response:
    """Open a bounded, authenticated Streamable-HTTP SSE endpoint.

    The read-only Mall catalog has no server-initiated business notifications,
    so the endpoint sends one protocol-neutral readiness comment and closes.
    Tool calls continue to return JSON from ``POST /mcp``.  It still matters
    that GET enforces the same opaque-session, per-request authorization and
    negotiated protocol version as POST: a guessed session can never become a
    data stream.
    """

    started_at = time.monotonic()
    if not _accepts_sse(request.headers.get("accept")):
        return _transport_error(
            status_code=406,
            code=-32000,
            message="MCP GET Accept 必须允许 text/event-stream。",
        )
    response_session_id: str | None = None
    try:
        _require_protocol_version(mcp_protocol_version, initializing=False)
        scope = resolve_mcp_access_scope(authorization)
        mcp_session_store.require(mcp_session_id, scope)
        response_session_id = mcp_session_id
        reliability_governor.check_rate_limit(
            actor_scope=f"{scope.subject_kind}:{scope.principal_fingerprint}",
            role="operations_analysis" if scope.subject_kind == "operator" else "unified_after_sales",
            action="mcp_read",
        )
        reliability_governor.record_request(
            "mcp_read", succeeded=True, duration_ms=_elapsed_ms(started_at)
        )
        return StreamingResponse(
            _mcp_ready_stream(),
            media_type="text/event-stream",
            headers=_response_headers(response_session_id),
        )
    except McpSessionError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return _mcp_error_response(exc.status_code, -32001, str(exc), response_session_id)
    except McpContextError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return _mcp_error_response(exc.status_code, -32001, str(exc), response_session_id)
    except McpProtocolError as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return _mcp_error_response(400, exc.code, str(exc), response_session_id)
    except RateLimitExceeded as exc:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        response = _mcp_error_response(429, -32003, str(exc), response_session_id)
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response
    except ReliabilityBackendUnavailable:
        reliability_governor.record_request(
            "mcp_read", succeeded=False, duration_ms=_elapsed_ms(started_at)
        )
        return _mcp_error_response(
            503,
            -32004,
            "MCP 只读保护暂时不可用，请稍后重试。",
            response_session_id,
        )


@router.delete("")
def mcp_delete(
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias=MCP_SESSION_HEADER),
    mcp_protocol_version: str | None = Header(default=None, alias=MCP_PROTOCOL_HEADER),
) -> Response:
    """Allow a client to explicitly end its opaque MCP transport session."""

    try:
        _require_protocol_version(mcp_protocol_version, initializing=False)
        scope = resolve_mcp_access_scope(authorization)
        mcp_session_store.close(mcp_session_id, scope)
        return Response(status_code=204, headers=_MCP_HEADERS)
    except McpSessionError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": str(exc)}},
            headers=_MCP_HEADERS,
        )
    except McpProtocolError as exc:
        return JSONResponse(
            status_code=400,
            content=protocol_error_response(exc),
            headers=_MCP_HEADERS,
        )
    except McpContextError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=context_error_response(exc),
            headers=_MCP_HEADERS,
        )


def _accepts_streamable_mcp(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    accepted = {
        part.split(";", 1)[0].strip().lower()
        for part in value.split(",")
        if part.strip()
    }
    return _MCP_ACCEPT_TYPES.issubset(accepted)


def _accepts_sse(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return "text/event-stream" in {
        part.split(";", 1)[0].strip().lower()
        for part in value.split(",")
        if part.strip()
    }


def _is_json_content_type(value: str | None) -> bool:
    return isinstance(value, str) and value.split(";", 1)[0].strip().lower() == "application/json"


def _require_protocol_version(value: str | None, *, initializing: bool) -> None:
    """Enforce the negotiated protocol version without trusting a session alone.

    An initializing client may omit the header because the JSON-RPC
    ``initialize`` parameters are the negotiation source.  Once initialized,
    every POST, GET and DELETE must state the version it is speaking.  A
    mismatched version fails before any catalog/tool code can execute.
    """

    if value is None or not value.strip():
        if initializing:
            return
        raise McpProtocolError("MCP 请求缺少协议版本头。", code=-32602)
    if value.strip() != MCP_PROTOCOL_VERSION:
        raise McpProtocolError("不支持的 MCP 协议版本。", code=-32602)


def _response_headers(session_id: str | None = None) -> dict[str, str]:
    headers = dict(_MCP_HEADERS)
    if session_id:
        headers[MCP_SESSION_HEADER] = session_id
    return headers


def _mcp_ready_stream():
    """Yield no business data; this server has no outbound MCP notifications."""

    yield b": mall-readonly-after-sales stream established\r\n\r\n"


def _mcp_error_response(
    status_code: int,
    code: int,
    message: str,
    session_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}},
        headers=_response_headers(session_id),
    )


def _transport_error(*, status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}},
        headers=_MCP_HEADERS,
    )


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))
