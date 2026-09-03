from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.tool import ToolCall

IntentName = Literal[
    "query_order_status",
    "query_logistics",
    "query_inventory",
    "after_sales_policy",
    "after_sales_eligibility",
    "apply_after_sales",
    "list_after_sales",
    "status_after_sales",
    "cancel_after_sales",
    "modify_after_sales",
    "follow_up_after_sales",
    "product_question",
    "business_analysis",
    "general_chat",
    "continue_tool_call",
    "unknown",
]
IntentRoute = Literal[
    "chat",
    "rag",
    "tool_calling",
    "agent",
    "ask_missing_info",
    "after_sales_flow",
]
IntentToolName = Literal[
    "order_service",
    "logistics_service",
    "inventory_service",
    "analysis_agent",
]
ChatScope = Literal["greeting", "capability", "out_of_scope"]
AFTER_SALES_INTENTS = {
    "after_sales_policy",
    "after_sales_eligibility",
    "apply_after_sales",
    "list_after_sales",
    "status_after_sales",
    "cancel_after_sales",
    "modify_after_sales",
    "follow_up_after_sales",
}
AFTER_SALES_FLOW_INTENTS = AFTER_SALES_INTENTS - {"after_sales_policy"}


class IntentToolCall(ToolCall):
    """意图识别阶段允许模型选择的工具白名单。"""

    name: IntentToolName


class IntentRequest(BaseModel):
    message: str = Field(min_length=1, examples=["我的订单为什么还没发货？"])


class IntentResponse(BaseModel):
    intent: IntentName
    route: IntentRoute
    need_tool: bool
    tool_call: IntentToolCall | None = None
    reply: str | None = None
    # Internal-only; the public customer DTO never serializes this field.
    chat_scope: ChatScope | None = None
    source: str = "llm"

    @model_validator(mode="after")
    def validate_route_contract(self) -> "IntentResponse":
        """把 Prompt 中的路由规则变成程序可执行的校验。"""
        if self.route == "tool_calling":
            if not self.need_tool or self.tool_call is None:
                raise ValueError("tool_calling 路由必须携带工具调用")

        if self.route == "ask_missing_info":
            if self.need_tool or self.tool_call is None:
                raise ValueError("缺参追问必须保留待执行工具，但不能立即执行")

        if self.route == "agent":
            if (
                not self.need_tool
                or self.tool_call is None
                or self.tool_call.name != "analysis_agent"
            ):
                raise ValueError("agent 路由必须使用 analysis_agent")

        if self.route in {"chat", "rag"}:
            if self.need_tool or self.tool_call is not None:
                raise ValueError(f"{self.route} 路由不能携带工具调用")

        if self.route == "after_sales_flow":
            if self.need_tool or self.tool_call is not None:
                raise ValueError(f"{self.route} 路由不能直接调用工具")

        # A policy consultation is a read-only evidence lookup.  It bypasses
        # the business workflow so it can be a one-turn detour without
        # allowing any Java write.  Every other after-sales intent remains
        # closed to the unified flow; a valid-looking model JSON may not turn
        # an application, cancellation, modification or follow-up into a
        # legacy direct-tool call.
        if self.intent == "after_sales_policy" and self.route != "rag":
            raise ValueError("售后政策咨询必须进入只读 RAG 路由")
        if self.intent in AFTER_SALES_FLOW_INTENTS and self.route != "after_sales_flow":
            raise ValueError("售后业务 intent 必须进入统一售后流程")

        if self.intent == "general_chat":
            if self.route != "chat" or self.chat_scope is None:
                raise ValueError("general_chat must carry a bounded chat_scope")
        elif self.chat_scope is not None:
            raise ValueError("chat_scope is only valid for general_chat")

        return self
