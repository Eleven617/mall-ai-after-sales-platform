"""Render business facts from tool results without asking an LLM to restate them."""

from collections.abc import Iterable
from typing import Any

from app.schemas.agent import VerifiedFactCard, VerifiedFactField


ToolResult = tuple[str, dict[str, Any]]


def build_verified_facts(tool_results: Iterable[ToolResult]) -> list[VerifiedFactCard]:
    """Expose only allow-listed, user-safe fields from trusted tool results."""
    cards: list[VerifiedFactCard] = []
    for tool_name, result in tool_results:
        if not isinstance(result, dict) or result.get("error"):
            continue
        card = _build_fact_card(tool_name, result)
        if card is not None:
            cards.append(card)
    return cards


def render_verified_facts_summary(facts: list[VerifiedFactCard]) -> str:
    """Create the user-facing factual answer entirely on the server."""
    if not facts:
        return "查询完成，但暂未获得可展示的系统结果。"

    lines = ["已完成系统查询，以下核心信息以业务系统返回为准："]
    for card in facts:
        lines.append(f"【{card.title}】")
        lines.extend(f"{field.label}：{field.value}" for field in card.fields)
    return "\n".join(lines)


def _build_fact_card(tool_name: str, result: dict[str, Any]) -> VerifiedFactCard | None:
    if tool_name == "order_service":
        fields = _fields(
            ("订单号", result.get("order_sn")),
            ("订单状态", result.get("status")),
            ("商品", result.get("product_names")),
            ("物流公司", result.get("delivery_company")),
            ("运单号", result.get("tracking_no")),
        )
        return _card(tool_name, "订单信息（商城系统）", fields)

    if tool_name == "logistics_service":
        fields = _fields(
            ("订单号", result.get("order_sn")),
            ("物流状态", result.get("order_status")),
            ("物流公司", result.get("company")),
            ("运单号", result.get("tracking_no")),
            ("商品", result.get("product_names")),
        )
        return _card(tool_name, "物流信息（商城系统）", fields)

    if tool_name == "inventory_service":
        fields = _fields(
            ("SKU", result.get("sku_id")),
            ("可售库存", _with_unit(result.get("available_stock"), "件")),
            ("预占库存", _with_unit(result.get("reserved_stock"), "件")),
            ("仓库", result.get("warehouse")),
            ("库存状态", result.get("status")),
        )
        # 当前库存工具仍是本地演示数据，卡片上必须避免暗示其已真实接入。
        return _card(tool_name, "库存信息（当前演示数据）", fields)

    if tool_name == "rag_search":
        source_labels = _rag_source_labels(result.get("sources"))
        fields = _fields(
            ("检索到的政策来源数量", len(source_labels) if source_labels else None),
            ("政策来源", source_labels),
        )
        return _card(tool_name, "售后政策来源（知识库）", fields)

    return None


def _card(
    source: str,
    title: str,
    fields: list[VerifiedFactField],
) -> VerifiedFactCard | None:
    if not fields:
        return None
    return VerifiedFactCard(source=source, title=title, fields=fields)


def _fields(*pairs: tuple[str, Any]) -> list[VerifiedFactField]:
    fields: list[VerifiedFactField] = []
    for label, value in pairs:
        text = _display_text(value)
        if text is not None:
            fields.append(VerifiedFactField(label=label, value=text))
    return fields


def _display_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        parts = [_display_text(item) for item in value]
        text = "、".join(part for part in parts if part)
        return text or None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _with_unit(value: Any, unit: str) -> str | None:
    text = _display_text(value)
    return f"{text}{unit}" if text is not None else None


def _rag_source_labels(sources: Any) -> list[str]:
    if not isinstance(sources, list):
        return []

    labels: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        document_name = _display_text(source.get("document_name"))
        section_path = _display_text(source.get("section_path"))
        if document_name and section_path:
            labels.append(f"{document_name}：{section_path}")
        elif document_name or section_path:
            labels.append(document_name or section_path or "")
    return labels
