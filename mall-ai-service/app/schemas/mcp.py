"""Strict, read-only Model Context Protocol request contracts.

The MCP endpoint is an interoperability adapter, not an authorization system.
It deliberately has no write-operation model and rejects fields that could
pretend to expand a caller's data scope.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictMcpModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class McpClientInfo(StrictMcpModel):
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)


class McpInitializeParams(StrictMcpModel):
    protocol_version: str = Field(alias="protocolVersion", min_length=1, max_length=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    client_info: McpClientInfo = Field(alias="clientInfo")


class McpToolCallParams(StrictMcpModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpJsonRpcRequest(StrictMcpModel):
    jsonrpc: Literal["2.0"]
    id: str | int | None = None
    method: str = Field(min_length=1, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_scope_or_write_shaped_parameters(self) -> "McpJsonRpcRequest":
        """Reject parameters that try to turn a read-only adapter into a proxy.

        Tool-specific Pydantic models already reject unknown arguments.  This
        extra guard deliberately runs before method dispatch so `initialize`
        capabilities, an unknown method, or a future generic parameter cannot
        smuggle an identity, a privileged endpoint, or a write intent into the
        MCP transport.  It validates *field names* only: a customer's policy
        question may naturally contain a URL-like string, but it can never
        supply a `url`, `memberId`, or `write` parameter to this server.
        """

        _validate_mcp_parameter_tree(self.params)
        if _contains_forbidden_mcp_parameter_name(self.params):
            raise ValueError("MCP 参数不得声明身份范围、外部地址或写操作。")
        return self


_FORBIDDEN_MCP_PARAMETER_NAMES = {
    "memberid",
    "operatorid",
    "role",
    "roles",
    "permission",
    "permissions",
    "servicekey",
    "apikey",
    "apikeyid",
    "authorization",
    "token",
    "sql",
    "querysql",
    "filepath",
    "filename",
    "path",
    "url",
    "uri",
    "endpoint",
    "write",
    "writeoperation",
    "writeop",
    "create",
    "cancel",
    "modify",
    "refund",
    "fulfillment",
}

_MCP_MAX_PARAMETER_DEPTH = 8
_MCP_MAX_PARAMETER_NODES = 128


def _validate_mcp_parameter_tree(value: object) -> None:
    """Bound JSON-RPC parameter traversal before method dispatch.

    MCP only needs a small initialize declaration or one narrow read-tool
    argument.  A bounded walk avoids accepting deeply nested or deliberately
    huge transport metadata that is neither needed by this server nor safe to
    recurse through.  The limits apply to field structure, never to a policy
    question's text value.
    """

    nodes_seen = 0

    def walk(current: object, depth: int) -> None:
        nonlocal nodes_seen
        nodes_seen += 1
        if nodes_seen > _MCP_MAX_PARAMETER_NODES:
            raise ValueError("MCP 参数结构过大。")
        if depth > _MCP_MAX_PARAMETER_DEPTH:
            raise ValueError("MCP 参数嵌套层级过深。")
        if isinstance(current, dict):
            for child in current.values():
                walk(child, depth + 1)
        elif isinstance(current, list):
            for child in current:
                walk(child, depth + 1)

    walk(value, 0)


def _contains_forbidden_mcp_parameter_name(value: object) -> bool:
    """Scan nested parameter keys without inspecting customer text values."""

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(char for char in str(key).lower() if char.isalnum())
            if normalized in _FORBIDDEN_MCP_PARAMETER_NAMES:
                return True
            if _contains_forbidden_mcp_parameter_name(child):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_mcp_parameter_name(item) for item in value)
    return False


class GetOrderSummaryArguments(StrictMcpModel):
    order_ref: str = Field(alias="orderRef", min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class GetLogisticsStatusArguments(StrictMcpModel):
    order_ref: str = Field(alias="orderRef", min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class GetAfterSalesStatusArguments(StrictMcpModel):
    application_ref: int | None = Field(default=None, alias="applicationRef", gt=0)
    order_ref: str | None = Field(
        default=None,
        alias="orderRef",
        min_length=4,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )

    @model_validator(mode="after")
    def require_one_reference(self) -> "GetAfterSalesStatusArguments":
        if self.application_ref is None and self.order_ref is None:
            raise ValueError("applicationRef 或 orderRef 必须提供一个")
        return self


class CheckAfterSalesReadinessArguments(StrictMcpModel):
    order_ref: str = Field(alias="orderRef", min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    item_ref: int | None = Field(default=None, alias="itemRef", gt=0)


class SearchAfterSalesPolicyArguments(StrictMcpModel):
    query: str = Field(min_length=1, max_length=500)


class GetCaseHandoffSummaryArguments(StrictMcpModel):
    case_id: str = Field(alias="caseId", min_length=36, max_length=36, pattern=r"^[a-f0-9-]{36}$")
