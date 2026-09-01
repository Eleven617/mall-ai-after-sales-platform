"""工具注册中心 — 所有工具的注册、查询和 Schema 定义"""
from collections.abc import Callable

from app.schemas.tool import ToolCall
from app.services.business_tools import query_inventory, query_logistics, query_order_status
from app.services.rag_service import answer_after_sales_question
from app.services.skill_catalog import SkillPolicyError, assert_tool_allowed_for_skill
from app.services.tool_context import ToolExecutionContext


ToolFunction = Callable[[dict, ToolExecutionContext], dict]


def _call_rag(args: dict, context: ToolExecutionContext) -> dict:
    result = answer_after_sales_question(args.get("query", ""))
    return {
        "answer": result.answer,
        "sources": [source.model_dump() for source in result.sources],
        "no_evidence": result.no_evidence,
        "retrieval_unavailable": result.retrieval_unavailable,
        "evidence_verification_unavailable": result.evidence_verification_unavailable,
        "answer_generation_unavailable": result.answer_generation_unavailable,
    }


TOOLS: dict[str, ToolFunction] = {
    "order_service": query_order_status,
    "logistics_service": query_logistics,
    "inventory_service": query_inventory,
    "rag_search": _call_rag,
}

_REQUIRED_FIELD_BY_TOOL = {
    "order_service": "order_sn",
    "logistics_service": "order_sn",
    "inventory_service": "sku_id",
    "rag_search": "query",
}

# ── 工具的 JSON Schema（给原生 Function Calling 用的）──

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "order_service",
            "description": "查询当前登录用户的订单状态、物流信息和商品名称",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_sn": {
                        "type": "string",
                        "description": "用户可见的订单编号",
                    },
                },
                "required": ["order_sn"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "logistics_service",
            "description": "查询当前登录用户订单的物流公司、运单号和订单状态",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_sn": {
                        "type": "string",
                        "description": "用户可见的订单编号",
                    },
                },
                "required": ["order_sn"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inventory_service",
            "description": "查询商品库存，包括可用库存、预占库存、所在仓库",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {
                        "type": "string",
                        "description": "SKU编码，格式如 SKU10001",
                    },
                },
                "required": ["sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "搜索售后服务政策知识库，查询退货、退款、换货、运费等政策",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要查询的问题，如 '退货的运费谁出'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


class ToolNotFoundError(RuntimeError):
    pass


class ToolInputError(ValueError):
    """模型返回的工具参数不满足服务端业务契约。"""


class ToolAccessDeniedError(PermissionError):
    """The selected server-owned role/Skill cannot call this tool."""


def call_tool(
    tool_call: ToolCall,
    context: ToolExecutionContext | None = None,
) -> dict:
    """执行工具"""
    tool = TOOLS.get(tool_call.name)
    if tool is None:
        raise ToolNotFoundError(f"工具未注册：{tool_call.name}")
    effective_context = context or ToolExecutionContext()
    if effective_context.skill_id is not None:
        try:
            assert_tool_allowed_for_skill(
                effective_context.actor_role,
                effective_context.skill_id,
                tool_call.name,
            )
        except SkillPolicyError as exc:
            raise ToolAccessDeniedError("当前受控能力不允许调用该工具。") from exc
    _validate_tool_arguments(tool_call)
    return tool(tool_call.arguments, effective_context)


def get_tool_schemas() -> list[dict]:
    """返回用于原生 Function Calling 的工具 Schema 列表"""
    return TOOL_SCHEMAS


def get_missing_required_field(tool_call: ToolCall) -> str | None:
    """Return the required field that still prevents tool execution."""
    required_field = _REQUIRED_FIELD_BY_TOOL.get(tool_call.name)
    if required_field is None:
        return None

    value = tool_call.arguments.get(required_field)
    if not isinstance(value, str) or not value.strip():
        return required_field
    return None


def _validate_tool_arguments(tool_call: ToolCall) -> None:
    """把 Schema 中的 required 变成真实的服务端执行校验。"""
    required_field = get_missing_required_field(tool_call)
    if required_field is None:
        return

    value = tool_call.arguments.get(required_field)
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"{tool_call.name} 缺少有效参数：{required_field}")
