"""Resolve an MCP caller from a server-validated credential only."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from app.services.mall_client import MallAuthenticationError, get_current_member
from app.services.operations_client import OperationsApiError, get_current_operator


McpSubjectKind = Literal["member", "operator"]


@dataclass(frozen=True)
class McpAccessScope:
    """Trusted runtime scope; it is never constructed from MCP parameters."""

    subject_kind: McpSubjectKind
    subject_id: int | None
    principal_fingerprint: str
    authorization: str
    capabilities: tuple[str, ...]


class McpContextError(RuntimeError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def resolve_mcp_access_scope(authorization: str | None) -> McpAccessScope:
    """Accept either a customer or dedicated operations credential.

    The subject kind is derived by the corresponding Java authority.  A caller
    cannot choose it in a JSON-RPC parameter or tool argument.
    """

    if not authorization or not authorization.startswith("Bearer "):
        raise McpContextError("MCP 调用需要有效登录凭证。", status_code=401)

    try:
        member = get_current_member(authorization)
        return McpAccessScope(
            subject_kind="member",
            subject_id=member.member_id,
            principal_fingerprint=_principal_fingerprint("member", str(member.member_id)),
            authorization=authorization,
            capabilities=(
                "get_order_summary",
                "get_logistics_status",
                "get_after_sales_status",
                "check_after_sales_readiness",
                "search_after_sales_policy",
            ),
        )
    except MallAuthenticationError as member_error:
        if member_error.status_code not in {401, 403}:
            raise McpContextError("MCP 身份服务暂时不可用。", status_code=503) from member_error

    try:
        operator = get_current_operator(authorization)
    except OperationsApiError as operator_error:
        if operator_error.status_code in {401, 403}:
            raise McpContextError("MCP 登录状态无效或无权访问。", status_code=401) from operator_error
        raise McpContextError("MCP 身份服务暂时不可用。", status_code=503) from operator_error

    return McpAccessScope(
        subject_kind="operator",
        subject_id=None,
        # Do not retain an operator's raw username in the runtime session or
        # rate-limit key.  The Java-backed /me response is still the authority;
        # this opaque value only binds an MCP protocol session to that subject.
        principal_fingerprint=_principal_fingerprint("operator", operator.username),
        authorization=authorization,
        capabilities=("get_case_handoff_summary",),
    )


def _principal_fingerprint(subject_kind: McpSubjectKind, identifier: str) -> str:
    """Build a stable, non-reversible-enough runtime subject reference.

    This is not an authorization credential and is never accepted from MCP
    parameters.  It exists so distinct authorized operators cannot share a
    Streamable-HTTP session merely because both have no numeric member id.
    """

    normalized = identifier.strip().casefold()
    material = f"mall-mcp:{subject_kind}:{normalized}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()
