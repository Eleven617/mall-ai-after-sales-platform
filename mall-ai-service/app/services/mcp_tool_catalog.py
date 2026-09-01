"""The complete, deliberately small read-only MCP tool catalog.

Every tool reaches the same Java-backed clients that the application uses.
No tool accepts a member/operator/role parameter, and the catalog has no
generic proxy, filesystem, network, SQL, write, refund, or fulfillment tool.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.after_sales_application import AfterSalesApplicationType
from app.schemas.mcp import (
    CheckAfterSalesReadinessArguments,
    GetAfterSalesStatusArguments,
    GetCaseHandoffSummaryArguments,
    GetLogisticsStatusArguments,
    GetOrderSummaryArguments,
    SearchAfterSalesPolicyArguments,
)
from app.services.mall_client import (
    MallApiClientError,
    check_after_sales_eligibility,
    get_order_snapshot,
    list_my_after_sales_applications,
)
from app.services.mcp_context_resolver import McpAccessScope
from app.services.operations_client import OperationsApiError, get_case_handoff
from app.services.rag_service import answer_after_sales_question


class McpToolError(RuntimeError):
    def __init__(self, message: str, *, code: str = "tool_execution_failed") -> None:
        super().__init__(message)
        self.code = code


ModelT = TypeVar("ModelT", bound=BaseModel)

_CUSTOMER_TOOL_NAMES = (
    "get_order_summary",
    "get_logistics_status",
    "get_after_sales_status",
    "check_after_sales_readiness",
    "search_after_sales_policy",
)
_OPERATIONS_TOOL_NAMES = ("get_case_handoff_summary",)


def list_mcp_tools(scope: McpAccessScope) -> list[dict[str, Any]]:
    names = _CUSTOMER_TOOL_NAMES if scope.subject_kind == "member" else _OPERATIONS_TOOL_NAMES
    return [_TOOL_DEFINITIONS[name] for name in names]


def execute_mcp_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    scope: McpAccessScope,
) -> dict[str, Any]:
    allowed = set(scope.capabilities)
    if name not in allowed:
        # Do not reveal whether a forbidden tool exists for this caller.
        raise McpToolError("当前身份不可调用该只读工具。", code="tool_not_allowed")
    definition = _TOOL_EXECUTORS.get(name)
    if definition is None:
        raise McpToolError("未注册的 MCP 工具。", code="tool_not_found")
    argument_model, executor = definition
    parsed = _validate_arguments(argument_model, arguments)
    try:
        return executor(parsed, scope)
    except McpToolError:
        raise
    except (MallApiClientError, OperationsApiError) as exc:
        raise McpToolError("只读业务事实暂时不可用，请稍后重试。") from exc
    except Exception as exc:
        raise McpToolError("只读工具执行失败。") from exc


def _validate_arguments(model: type[ModelT], arguments: dict[str, Any]) -> ModelT:
    if not isinstance(arguments, dict):
        raise McpToolError("MCP 工具参数必须是对象。", code="invalid_arguments")
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        raise McpToolError("MCP 工具参数不符合只读契约。", code="invalid_arguments") from exc


def _get_order_summary(args: GetOrderSummaryArguments, scope: McpAccessScope) -> dict[str, Any]:
    snapshot = get_order_snapshot(args.order_ref, scope.authorization)
    return {
        "source": "java_order_fact",
        "queriedAt": _now(),
        "order": {
            "orderRef": snapshot.get("order_sn"),
            "status": snapshot.get("status"),
            "items": _safe_order_items(snapshot.get("order_items")),
        },
    }


def _get_logistics_status(args: GetLogisticsStatusArguments, scope: McpAccessScope) -> dict[str, Any]:
    snapshot = get_order_snapshot(args.order_ref, scope.authorization)
    return {
        "source": "java_logistics_fact",
        "queriedAt": _now(),
        "logistics": {
            "orderRef": snapshot.get("order_sn"),
            "company": snapshot.get("delivery_company"),
            "trackingNo": snapshot.get("tracking_no"),
            "orderStatus": snapshot.get("status"),
        },
    }


def _get_after_sales_status(
    args: GetAfterSalesStatusArguments,
    scope: McpAccessScope,
) -> dict[str, Any]:
    applications = list_my_after_sales_applications(scope.authorization)
    matches = [
        item
        for item in applications
        if (args.application_ref is None or item.application_id == args.application_ref)
        and (args.order_ref is None or item.order_sn == args.order_ref)
    ]
    if not matches:
        raise McpToolError("未找到当前身份可见的售后状态。", code="not_found")
    return {
        "source": "java_after_sales_fact",
        "queriedAt": _now(),
        "applications": [
            {
                "applicationRef": item.application_id,
                "orderRef": item.order_sn,
                "applicationType": item.application_type,
                "status": item.status,
                "statusLabel": item.status_label,
                "fulfillmentStatus": item.fulfillment_status,
                "fulfillmentStatusLabel": item.fulfillment_status_label,
                "updatedAt": item.updated_at,
            }
            for item in matches[:10]
        ],
    }


def _check_after_sales_readiness(
    args: CheckAfterSalesReadinessArguments,
    scope: McpAccessScope,
) -> dict[str, Any]:
    # The order lookup is both a fact source and the ownership guard.  A caller
    # cannot use ``itemRef`` alone to probe a different member's order item.
    snapshot = get_order_snapshot(args.order_ref, scope.authorization)
    items = _safe_order_items(snapshot.get("order_items"))
    if args.item_ref is not None and all(item["itemRef"] != args.item_ref for item in items):
        raise McpToolError("未找到当前订单中的商品项。", code="not_found")

    readiness = []
    for application_type in _AFTER_SALES_TYPES:
        eligibility = check_after_sales_eligibility(
            args.order_ref,
            application_type,
            scope.authorization,
            order_item_id=args.item_ref,
        )
        readiness.append(
            {
                "applicationType": eligibility.application_type,
                "eligible": eligibility.eligible,
                "decision": eligibility.decision,
                "requiresProductSelection": eligibility.requires_product_selection,
                "message": eligibility.message,
            }
        )
    return {
        "source": "java_after_sales_eligibility",
        "queriedAt": _now(),
        "orderRef": snapshot.get("order_sn"),
        "itemRef": args.item_ref,
        "readiness": readiness,
    }


def _search_after_sales_policy(
    args: SearchAfterSalesPolicyArguments,
    _scope: McpAccessScope,
) -> dict[str, Any]:
    result = answer_after_sales_question(args.query)
    return {
        "source": "reviewed_policy_rag",
        "queriedAt": _now(),
        "answer": result.answer,
        "noEvidence": result.no_evidence,
        "retrievalUnavailable": result.retrieval_unavailable,
        "evidenceVerificationUnavailable": result.evidence_verification_unavailable,
        "sources": [
            {
                "documentName": source.document_name,
                "sectionPath": source.section_path,
            }
            for source in result.sources
        ],
    }


def _get_case_handoff_summary(
    args: GetCaseHandoffSummaryArguments,
    scope: McpAccessScope,
) -> dict[str, Any]:
    case = get_case_handoff(args.case_id, scope.authorization)
    return {
        "source": "java_minimal_case_handoff",
        "queriedAt": _now(),
        "case": {
            "caseId": case.case_id,
            "sourceFlow": case.source_flow,
            "diagnosisCategory": case.diagnosis_category,
            "evidenceStatus": case.evidence_status,
            "handoffReason": case.handoff_reason,
            "requiresHumanReview": case.requires_human_review,
            "caseStatus": case.case_status,
            "createdAt": case.created_at.isoformat() if case.created_at else None,
            "updatedAt": case.updated_at.isoformat() if case.updated_at else None,
        },
    }


def _safe_order_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        item_id = item.get("order_item_id")
        if not isinstance(item_id, int) or item_id <= 0:
            continue
        items.append(
            {
                "itemRef": item_id,
                "productName": item.get("product_name"),
                "productAttr": item.get("product_attr"),
                "quantity": item.get("product_quantity"),
            }
        )
    return items


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_AFTER_SALES_TYPES: tuple[AfterSalesApplicationType, ...] = (
    "cancel_refund",
    "return_refund",
    "exchange",
    "repair",
)

_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "get_order_summary": {
        "name": "get_order_summary",
        "description": "读取当前登录会员自己订单的最小摘要。",
        "inputSchema": GetOrderSummaryArguments.model_json_schema(by_alias=True),
    },
    "get_logistics_status": {
        "name": "get_logistics_status",
        "description": "读取当前登录会员自己订单的最小物流摘要。",
        "inputSchema": GetLogisticsStatusArguments.model_json_schema(by_alias=True),
    },
    "get_after_sales_status": {
        "name": "get_after_sales_status",
        "description": "读取当前登录会员自己的售后状态摘要。",
        "inputSchema": GetAfterSalesStatusArguments.model_json_schema(by_alias=True),
    },
    "check_after_sales_readiness": {
        "name": "check_after_sales_readiness",
        "description": "只读检查当前订单各类售后申请的 Java 权威资格摘要。",
        "inputSchema": CheckAfterSalesReadinessArguments.model_json_schema(by_alias=True),
    },
    "search_after_sales_policy": {
        "name": "search_after_sales_policy",
        "description": "检索审核过的静态售后政策并返回核验后的摘要和来源。",
        "inputSchema": SearchAfterSalesPolicyArguments.model_json_schema(by_alias=True),
    },
    "get_case_handoff_summary": {
        "name": "get_case_handoff_summary",
        "description": "运营身份只读读取最小化人工转接摘要。",
        "inputSchema": GetCaseHandoffSummaryArguments.model_json_schema(by_alias=True),
    },
}

_TOOL_EXECUTORS: dict[str, tuple[type[BaseModel], Callable[[Any, McpAccessScope], dict[str, Any]]]] = {
    "get_order_summary": (GetOrderSummaryArguments, _get_order_summary),
    "get_logistics_status": (GetLogisticsStatusArguments, _get_logistics_status),
    "get_after_sales_status": (GetAfterSalesStatusArguments, _get_after_sales_status),
    "check_after_sales_readiness": (CheckAfterSalesReadinessArguments, _check_after_sales_readiness),
    "search_after_sales_policy": (SearchAfterSalesPolicyArguments, _search_after_sales_policy),
    "get_case_handoff_summary": (GetCaseHandoffSummaryArguments, _get_case_handoff_summary),
}
