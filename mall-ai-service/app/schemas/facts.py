"""Trusted fact cards shared by the baseline Agent and diagnosis graph."""

from typing import Literal

from pydantic import BaseModel, Field


VerifiedFactSource = Literal[
    "order_service",
    "logistics_service",
    "inventory_service",
    "rag_search",
]


class VerifiedFactField(BaseModel):
    """一个由服务端原始工具结果生成、可直接展示的事实字段。"""

    label: str
    value: str


class VerifiedFactCard(BaseModel):
    """前端用于展示可信业务数据的信息卡，模型不参与字段值生成。"""

    source: VerifiedFactSource
    title: str
    fields: list[VerifiedFactField] = Field(default_factory=list)
