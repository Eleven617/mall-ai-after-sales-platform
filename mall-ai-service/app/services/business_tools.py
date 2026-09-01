from app.services.mall_client import get_order_snapshot
from app.services.tool_context import ToolExecutionContext


def query_order_status(arguments: dict, context: ToolExecutionContext) -> dict:
    """通过 Java 服务查询当前用户自己的订单，不返回模拟数据。"""
    order_sn = arguments["order_sn"]
    return get_order_snapshot(order_sn, context.authorization)


def query_logistics(arguments: dict, context: ToolExecutionContext) -> dict:
    """物流信息复用受授权的订单摘要，避免额外暴露物流数据库。"""
    snapshot = get_order_snapshot(arguments["order_sn"], context.authorization)
    return {
        "order_sn": snapshot["order_sn"],
        "company": snapshot["delivery_company"],
        "tracking_no": snapshot["tracking_no"],
        "order_status": snapshot["status"],
        "product_names": snapshot["product_names"],
    }


def query_inventory(arguments: dict, context: ToolExecutionContext) -> dict:
    """库存工具暂保留为本地演示数据，后续接入 Java 商品库存服务。"""
    sku_id = arguments["sku_id"]
    return {
        "sku_id": sku_id,
        "available_stock": 86,
        "reserved_stock": 14,
        "warehouse": "华东仓",
        "status": "in_stock",
    }
