"""A deterministic LangGraph lab for an order-exception handoff flow.

This is deliberately a small, isolated learning graph.  Production business
authority, authentication and real service calls remain in the mall project.
"""
from __future__ import annotations

import json
from typing import Any

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class OrderExceptionState(TypedDict, total=False):
    """All data that may move between graph nodes for one diagnostic case."""

    order_sn: str
    user_question: str
    order_found: bool
    order_status: str
    logistics_status: str
    policy_evidence: str
    recommended_action: str
    confirmation: dict[str, Any]
    final_status: str


# These records stand in for real Java tools only inside this lab.
DEMO_ORDERS: dict[str, dict[str, str]] = {
    "ORD-DELAY-001": {
        "order_status": "已发货",
        "logistics_status": "48 小时未更新",
    },
    "ORD-NORMAL-002": {
        "order_status": "已发货",
        "logistics_status": "运输中，最近 2 小时有更新",
    },
}


def lookup_order(state: OrderExceptionState) -> dict[str, Any]:
    """Node 1: get a minimal, deterministic order snapshot."""

    snapshot = DEMO_ORDERS.get(state["order_sn"])
    if snapshot is None:
        return {
            "order_found": False,
            "final_status": "order_not_found_or_not_authorized",
            "recommended_action": "请核对订单号，或由人工客服继续核验。",
        }
    return {
        "order_found": True,
        "order_status": snapshot["order_status"],
        "logistics_status": snapshot["logistics_status"],
    }


def route_after_order(state: OrderExceptionState) -> str:
    """Conditional edge: order missing must not continue to logistics/policy."""

    return "load_logistics" if state["order_found"] else "finish"


def load_logistics(state: OrderExceptionState) -> dict[str, str]:
    """Node 2: in real code this would call a Java logistics tool."""

    return {"logistics_status": state["logistics_status"]}


def route_after_logistics(state: OrderExceptionState) -> str:
    """Conditional edge selected from a verified logistics observation."""

    if "未更新" in state["logistics_status"]:
        return "retrieve_policy"
    return "finish"


def retrieve_policy(_: OrderExceptionState) -> dict[str, str]:
    """Node 3: a fixed policy stub so the lab does not call an LLM/RAG service."""

    return {
        "policy_evidence": "演示政策：物流长时间无更新时，可发起人工物流异常核验。",
    }


def prepare_handoff(state: OrderExceptionState) -> dict[str, str]:
    """Node 4: create a proposed next action, but do not execute a write."""

    return {
        "recommended_action": (
            f"订单 {state['order_sn']} 的物流状态为“{state['logistics_status']}”。"
            "建议生成物流异常人工交接草稿。"
        )
    }


def wait_for_human_confirmation(state: OrderExceptionState) -> dict[str, Any]:
    """Node 5: pause the graph and resume this exact thread after confirmation."""

    decision = interrupt(
        {
            "kind": "confirm_handoff",
            "order_sn": state["order_sn"],
            "recommended_action": state["recommended_action"],
            "question": "是否确认生成物流异常人工交接草稿？",
        }
    )
    approved = isinstance(decision, dict) and decision.get("approved") is True
    return {
        "confirmation": decision if isinstance(decision, dict) else {"approved": False},
        "final_status": "handoff_draft_created" if approved else "handoff_cancelled",
    }


def finish(_: OrderExceptionState) -> dict[str, str]:
    """Terminal node for branches that do not require a human confirmation."""

    return {}


def build_graph(*, checkpointer: InMemorySaver | None = None):
    """Build and compile the state graph with a memory checkpointer."""

    graph = StateGraph(OrderExceptionState)
    graph.add_node("lookup_order", lookup_order)
    graph.add_node("load_logistics", load_logistics)
    graph.add_node("retrieve_policy", retrieve_policy)
    graph.add_node("prepare_handoff", prepare_handoff)
    graph.add_node("wait_for_human_confirmation", wait_for_human_confirmation)
    graph.add_node("finish", finish)

    graph.add_edge(START, "lookup_order")
    graph.add_conditional_edges(
        "lookup_order",
        route_after_order,
        {"load_logistics": "load_logistics", "finish": "finish"},
    )
    graph.add_conditional_edges(
        "load_logistics",
        route_after_logistics,
        {"retrieve_policy": "retrieve_policy", "finish": "finish"},
    )
    graph.add_edge("retrieve_policy", "prepare_handoff")
    graph.add_edge("prepare_handoff", "wait_for_human_confirmation")
    graph.add_edge("wait_for_human_confirmation", END)
    graph.add_edge("finish", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _print_state(label: str, state: dict[str, Any]) -> None:
    """Make the paused/resumed state readable from a terminal."""

    print(f"\n--- {label} ---")
    print(json.dumps(state, ensure_ascii=False, indent=2, default=str))


def run_demo() -> None:
    """Run one pause/resume case with a single stable LangGraph thread id."""

    app = build_graph()
    config = {"configurable": {"thread_id": "demo-order-delay-001"}}

    paused = app.invoke(
        {
            "order_sn": "ORD-DELAY-001",
            "user_question": "订单为什么一直没到？",
        },
        config,
    )
    _print_state("第一次执行：图在人工确认节点暂停", paused)

    resumed = app.invoke(Command(resume={"approved": True}), config)
    _print_state("第二次执行：同一 thread_id 恢复后完成", resumed)


if __name__ == "__main__":
    run_demo()
