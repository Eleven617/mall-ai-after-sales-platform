"""A hybrid LangGraph lab: a model chooses actions, the graph controls execution.

The default demo uses a scripted provider so it is deterministic and free.
DeepSeekJsonDecisionProvider exists only to show where a real model fits; it is
never called unless a caller explicitly constructs it with an API key.
"""
from __future__ import annotations

import json
import os
import operator
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from typing_extensions import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


MAX_AGENT_DECISIONS = 5
ActionName = Literal[
    "lookup_order",
    "load_logistics",
    "retrieve_policy",
    "prepare_handoff",
    "finish",
]


class AgentDecision(BaseModel):
    """The only shape a model is allowed to use when choosing the next node."""

    next_action: ActionName
    rationale: str


class AgentGraphState(TypedDict, total=False):
    order_sn: str
    user_question: str
    order_found: bool
    order_status: str
    logistics_status: str
    policy_evidence: str
    recommended_action: str
    next_action: ActionName
    agent_decision_count: int
    decision_trace: Annotated[list[str], operator.add]
    confirmation: dict[str, Any]
    final_status: str
    tool_error: str


class DecisionProvider(Protocol):
    """A replaceable model boundary; graph nodes never trust its output directly."""

    def decide(self, state: dict[str, Any]) -> dict[str, Any]: ...


class ScriptedDecisionProvider:
    """Deterministic stand-in for tests and the default no-cost demonstration."""

    def __init__(self, actions: Sequence[str]) -> None:
        self._actions = iter(actions)

    def decide(self, _: dict[str, Any]) -> dict[str, Any]:
        action = next(self._actions, "finish")
        return {
            "next_action": action,
            "rationale": "scripted lab decision",
        }


class DeepSeekJsonDecisionProvider:
    """Optional live provider. Tests do not instantiate or call this class."""

    def __init__(self, api_key: str, *, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an order-exception routing model. Return JSON only: "
                            '{"next_action":"...","rationale":"..."}. '
                            "Choose exactly one next action. Allowed values are lookup_order, "
                            "load_logistics, retrieve_policy, prepare_handoff, finish. "
                            "Use only verified facts in the supplied state. If order_found is "
                            "missing, first choose lookup_order. If order_found is false, finish. "
                            "If an order is verified but logistics_status is missing, choose "
                            "load_logistics. If logistics has had no update for 48 hours and "
                            "policy_evidence is missing, choose retrieve_policy. Choose "
                            "prepare_handoff only when a verified order, abnormal logistics, and "
                            "relevant policy evidence are all present. Otherwise finish. Never "
                            "claim a write operation occurred."
                        ),
                    },
                    {"role": "user", "content": json.dumps(state, ensure_ascii=False)},
                ],
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Model returned no textual routing decision.")
        return json.loads(_strip_json_fence(content))


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


def build_agent_graph(
    provider: DecisionProvider,
    *,
    checkpointer: InMemorySaver | None = None,
):
    """Build a hybrid graph where the provider proposes, but graph code enforces."""

    def decide_next_action(state: AgentGraphState) -> dict[str, Any]:
        decision_count = state.get("agent_decision_count", 0)
        if decision_count >= MAX_AGENT_DECISIONS:
            return {
                "next_action": "finish",
                "final_status": "agent_step_limit_reached",
                "decision_trace": ["graph blocked further model decisions at step limit"],
            }

        try:
            raw_decision = provider.decide(_model_visible_state(state))
            decision = AgentDecision.model_validate(raw_decision)
        except (ValidationError, ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
            return {
                "next_action": "finish",
                "final_status": "invalid_or_unavailable_model_decision",
                "decision_trace": [f"model decision blocked: {type(exc).__name__}"],
            }

        return {
            "next_action": decision.next_action,
            "agent_decision_count": decision_count + 1,
            "decision_trace": [f"model proposed {decision.next_action}: {decision.rationale}"],
        }

    def lookup_order(state: AgentGraphState) -> dict[str, Any]:
        snapshot = DEMO_ORDERS.get(state["order_sn"])
        if snapshot is None:
            return {
                "order_found": False,
                "final_status": "order_not_found_or_not_authorized",
            }
        return {
            "order_found": True,
            "order_status": snapshot["order_status"],
        }

    def load_logistics(state: AgentGraphState) -> dict[str, str]:
        if not state.get("order_found"):
            return {"tool_error": "order_must_be_verified_before_logistics"}
        snapshot = DEMO_ORDERS.get(state["order_sn"])
        if snapshot is None:
            return {"tool_error": "verified_order_snapshot_unavailable"}
        return {"logistics_status": snapshot["logistics_status"]}

    def retrieve_policy(state: AgentGraphState) -> dict[str, str]:
        if "未更新" not in state.get("logistics_status", ""):
            return {"tool_error": "policy_not_needed_for_current_logistics_state"}
        return {
            "policy_evidence": "演示政策：物流长时间无更新时，可发起人工物流异常核验。",
        }

    def prepare_handoff(state: AgentGraphState) -> dict[str, str]:
        ready = (
            state.get("order_found") is True
            and "未更新" in state.get("logistics_status", "")
            and bool(state.get("policy_evidence"))
        )
        if not ready:
            return {"final_status": "handoff_precondition_missing"}
        return {
            "recommended_action": (
                f"订单 {state['order_sn']} 的物流状态为“{state['logistics_status']}”。"
                "建议生成物流异常人工交接草稿。"
            )
        }

    def wait_for_human_confirmation(state: AgentGraphState) -> dict[str, Any]:
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

    def finish(_: AgentGraphState) -> dict[str, str]:
        return {}

    def route_after_decision(state: AgentGraphState) -> ActionName:
        return state["next_action"]

    def route_after_order_lookup(state: AgentGraphState) -> str:
        return "agent_decide" if state.get("order_found") else "finish"

    def route_after_handoff_preparation(state: AgentGraphState) -> str:
        return "wait_for_human_confirmation" if state.get("recommended_action") else "finish"

    graph = StateGraph(AgentGraphState)
    graph.add_node("agent_decide", decide_next_action)
    graph.add_node("lookup_order", lookup_order)
    graph.add_node("load_logistics", load_logistics)
    graph.add_node("retrieve_policy", retrieve_policy)
    graph.add_node("prepare_handoff", prepare_handoff)
    graph.add_node("wait_for_human_confirmation", wait_for_human_confirmation)
    graph.add_node("finish", finish)

    graph.add_edge(START, "agent_decide")
    graph.add_conditional_edges(
        "agent_decide",
        route_after_decision,
        {
            "lookup_order": "lookup_order",
            "load_logistics": "load_logistics",
            "retrieve_policy": "retrieve_policy",
            "prepare_handoff": "prepare_handoff",
            "finish": "finish",
        },
    )
    graph.add_conditional_edges(
        "lookup_order",
        route_after_order_lookup,
        {"agent_decide": "agent_decide", "finish": "finish"},
    )
    graph.add_edge("load_logistics", "agent_decide")
    graph.add_edge("retrieve_policy", "agent_decide")
    graph.add_conditional_edges(
        "prepare_handoff",
        route_after_handoff_preparation,
        {
            "wait_for_human_confirmation": "wait_for_human_confirmation",
            "finish": "finish",
        },
    )
    graph.add_edge("wait_for_human_confirmation", END)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _model_visible_state(state: AgentGraphState) -> dict[str, Any]:
    """Pass the model only allow-listed diagnostic facts, never credentials or raw traces."""

    fields = (
        "order_sn",
        "user_question",
        "order_found",
        "order_status",
        "logistics_status",
        "policy_evidence",
        "tool_error",
    )
    return {field: state[field] for field in fields if field in state}


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def run_demo() -> None:
    """Run a no-cost scripted Agent path, then resume its human-confirmation pause."""

    provider = ScriptedDecisionProvider(
        ["lookup_order", "load_logistics", "retrieve_policy", "prepare_handoff"]
    )
    app = build_agent_graph(provider)
    config = {"configurable": {"thread_id": "agent-demo-delay-001"}}
    paused = app.invoke(
        {"order_sn": "ORD-DELAY-001", "user_question": "订单为什么一直没到？"},
        config,
    )
    print(json.dumps(paused, ensure_ascii=False, indent=2, default=str))
    resumed = app.invoke(Command(resume={"approved": True}), config)
    print(json.dumps(resumed, ensure_ascii=False, indent=2, default=str))


def run_live_demo() -> None:
    """Run the same graph with DeepSeek routing decisions, only when explicitly enabled."""

    project_env = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(project_env)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for the live LangGraph demo.")

    provider = DeepSeekJsonDecisionProvider(
        api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    )
    app = build_agent_graph(provider)
    config = {"configurable": {"thread_id": "agent-live-delay-001"}}
    paused = app.invoke(
        {"order_sn": "ORD-DELAY-001", "user_question": "订单为什么一直没有送到？"},
        config,
    )
    print(json.dumps(paused, ensure_ascii=False, indent=2, default=str))
    resumed = app.invoke(Command(resume={"approved": True}), config)
    print(json.dumps(resumed, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    if os.getenv("LANGGRAPH_LIVE_DEMO") == "1":
        run_live_demo()
    else:
        run_demo()
