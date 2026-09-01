"""Deterministic offline critic for Build 19 handoff contracts.

This module deliberately has no HTTP client, model call, database access, or
write path. It accepts synthetic handoffs and allow-listed trace metadata only.
"""

from typing import Any

from app.schemas.operations import CaseHandoffView


_BANNED_KEYS = {
    "authorization",
    "token",
    "member_id",
    "member_username",
    "order_sn",
    "phone",
    "address",
    "raw_message",
    "prompt",
    "rag_context",
    "tool_result",
}
_ALLOWED_TRACE_KEYS = {
    "flow",
    "event",
    "step",
    "tool_name",
    "diagnosis_category",
    "evidence_status",
    "handoff",
}


def evaluate_handoff_contract(
    case_payload: dict[str, Any],
    trace_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a private report without mutating inputs or calling services."""
    violations: list[str] = []
    if not isinstance(case_payload, dict):
        violations.append("case_not_object")
        case_payload = {}
    if _find_banned_key(case_payload):
        violations.append("sensitive_case_field")
    try:
        CaseHandoffView.model_validate(case_payload, strict=True, extra="forbid")
    except Exception:
        violations.append("case_schema_invalid")

    if trace_metadata is not None:
        if not isinstance(trace_metadata, dict) or set(trace_metadata) - _ALLOWED_TRACE_KEYS:
            violations.append("trace_not_allow_listed")
        elif _find_banned_key(trace_metadata):
            violations.append("sensitive_trace_field")
    return {
        "mode": "offline_build19_critic",
        "passed": not violations,
        "violations": violations,
        "recommendations": [
            "为失败字段增加隔离合同测试。" if violations else "保留当前角色边界回归用例。"
        ],
    }


def _find_banned_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key.lower() in _BANNED_KEYS or _find_banned_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_find_banned_key(item) for item in value)
    return False
