"""会话安全记忆的唯一写入路径，交接只读取该投影。"""
from __future__ import annotations

import time
import hashlib
import re
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from app.runtime.graph_checkpoint import CONVERSATION_GRAPH_VERSION, SafeSaver, persistent_saver, thread_config
from app.services.handoff_safe_context import fragments
from app.services.reliability_service import reliability_governor


class MemoryState(TypedDict, total=False):
    graph_version: str
    fragments: list[dict]
    omitted: bool
    revision: int
    expires_at: float
    deleted: bool


class ConversationMemory:
    def __init__(self, *, durable=False, ttl=86400, saver=None):
        self.ttl = ttl
        self._saver = saver if saver is not None else (None if durable else SafeSaver(InMemorySaver()))
        self.durable = durable

    @property
    def saver(self):
        if self._saver is None:
            self._saver = persistent_saver() if self.durable else SafeSaver(InMemorySaver())
        return self._saver

    def graph(self):
        builder = StateGraph(MemoryState)
        builder.add_node("remember", lambda state: {})
        builder.add_edge(START, "remember")
        builder.add_edge("remember", END)
        return builder.compile(checkpointer=self.saver, name="ConversationMemory")

    def config(self, session):
        return thread_config(CONVERSATION_GRAPH_VERSION, "scoped-session", session)

    def read(self, session):
        value = self.graph().get_state(self.config(session)).values or {}
        if value.get("deleted") or value.get("expires_at", 0) <= time.time():
            return {"fragments": [], "omitted": False, "revision": value.get("revision", 0), "deleted": value.get("deleted", False)}
        if value.get("graph_version") != CONVERSATION_GRAPH_VERSION:
            raise ValueError("会话记忆版本不兼容")
        return value

    def append(self, session, role, content, *, task_ref=None):
        safe, omitted = fragments(content, role)
        self.append_safe(session, safe, omitted, task_ref=task_ref)

    def append_safe(self, session, safe, omitted=False, *, task_ref=None):
        if task_ref is not None and not re.fullmatch(r"taskref-[a-z0-9]+", task_ref):
            raise ValueError("事项记忆引用不合法")
        # 仅迁移已审核的词汇投影；不能借迁移把旧原文导入新存储。
        reviewed = []
        for item in safe:
            role = "user" if item.get("kind") == "customer_statement" else "assistant"
            checked, rejected = fragments(item.get("text", ""), role)
            reviewed.extend(checked)
            omitted |= rejected
        with reliability_governor.lock(scope="safe-memory:"+session, kind="session"):
            graph, config = self.graph(), self.config(session)
            previous = self.read(session)
            if previous.get("deleted"):
                raise ValueError("会话已删除，不能重新写入")
            sequence = previous.get("revision", 0) + 1
            for item in reviewed:
                item["sequence"] = sequence
                item["task_ref"] = task_ref
            graph.update_state(config, {
                "graph_version": CONVERSATION_GRAPH_VERSION,
                "fragments": (previous.get("fragments", []) + reviewed)[-8:],
                "omitted": previous.get("omitted", False) or omitted or len(previous.get("fragments", [])+reviewed)>8,
                "revision": sequence, "expires_at": time.time()+self.ttl, "deleted": False,
            }, as_node="remember")

    def delete(self, session):
        with reliability_governor.lock(scope="safe-memory:"+session, kind="session"):
            config = self.config(session)
            session_ref = hashlib.sha256(session.encode()).hexdigest()
            self.saver.tombstone_session(session_ref)
            turn_threads = {item.config["configurable"]["thread_id"] for item in self.saver.list(None, filter={"session_ref": session_ref})}
            for thread in turn_threads:
                self.saver.delete_thread(thread)
            self.saver.delete_thread(config["configurable"]["thread_id"])
            # 空白墓碑覆盖所有旧历史，防仍在运行的请求把删除会话复活。
            self.graph().update_state(config, {"graph_version": CONVERSATION_GRAPH_VERSION,
                "fragments": [], "omitted": True, "revision": 0, "deleted": True,
                "expires_at": time.time()+self.ttl}, as_node="remember")
