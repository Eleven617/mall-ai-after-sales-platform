"""统一图的检查点工厂；身份由调用方验证，凭证不进入图配置。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from langsmith import tracing_context

from app.config import settings

TASK_GRAPH_VERSION = "task-v1"
CONVERSATION_GRAPH_VERSION = "conversation-v1"


def invoke_graph(graph, input_value, config):
    # 只使用项目已有脱敏审计；第三方 tracing 不接收请求内异常或依赖。
    with tracing_context(enabled=False):
        return graph.invoke(input_value, config, durability="sync")


class SafeSaver(BaseCheckpointSaver):
    """错误文本不进入持久化；元数据仅接受服务端闭集。"""
    def __init__(self, delegate):
        super().__init__(serde=delegate.serde)
        self.delegate = delegate
        self._deleted_sessions = set()

    def tombstone_session(self, session_ref):
        if hasattr(self.delegate, "db"):
            collection = self.delegate.db["orchestration_tombstones_v1"]
            collection.create_index("expires_at", expireAfterSeconds=0)
            collection.replace_one({"_id": session_ref}, {"_id": session_ref,
                "expires_at": datetime.now(timezone.utc)+timedelta(seconds=settings.conversation_ttl_seconds)}, upsert=True)
        self._deleted_sessions.add(session_ref)

    def _check_active(self, config):
        session_ref = config.get("metadata", {}).get("session_ref")
        if not session_ref:
            return
        deleted = session_ref in self._deleted_sessions
        if not deleted and hasattr(self.delegate, "db"):
            deleted = self.delegate.db["orchestration_tombstones_v1"].find_one({"_id": session_ref}) is not None
        if deleted:
            raise ValueError("会话已删除，拒绝迟到的图写入")

    def get_tuple(self, config):
        return self.delegate.get_tuple(config)

    def list(self, config, *, filter=None, before=None, limit=None):
        return self.delegate.list(config, filter=filter, before=before, limit=limit)

    def put(self, config, checkpoint, metadata, new_versions):
        self._check_active(config)
        safe_metadata = {key: value for key, value in metadata.items()
                         if key in {"source", "step", "parents", "session_ref"}}
        return self.delegate.put(config, checkpoint, safe_metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):
        self._check_active(config)
        safe_writes = [(name, "graph_node_failed" if name == "__error__" else value) for name, value in writes]
        return self.delegate.put_writes(config, safe_writes, task_id, task_path)

    def delete_thread(self, thread_id):
        return self.delegate.delete_thread(thread_id)

    def get_next_version(self, current, channel):
        return self.delegate.get_next_version(current, channel)


def thread_config(kind: str, owner: str, reference: str) -> dict:
    if kind not in {TASK_GRAPH_VERSION, CONVERSATION_GRAPH_VERSION}:
        raise ValueError("不支持的图版本")
    digest = hashlib.sha256(f"{kind}:{owner}:{reference}".encode()).hexdigest()
    return {"configurable": {"thread_id": f"{kind}-{digest}"}, "recursion_limit": 160, "callbacks": []}


@lru_cache(maxsize=16)
def persistent_saver(url=None, database=None):
    # 只在首次真实使用时连接；导入模块和离线单测不会启动环境。
    from langgraph.checkpoint.mongodb import MongoDBSaver
    from pymongo import MongoClient
    client = MongoClient(url or settings.agent_task_mongo_url, serverSelectionTimeoutMS=1500)
    return SafeSaver(MongoDBSaver(
        client, db_name=database or settings.agent_task_mongo_database,
        checkpoint_collection_name="orchestration_checkpoints_v1",
        writes_collection_name="orchestration_writes_v1",
        ttl=max(settings.agent_task_ttl_seconds, settings.conversation_ttl_seconds),
    ))


def task_saver(store):
    from app.runtime.task_store import InMemoryTaskStore, MongoTaskStore
    if isinstance(store, InMemoryTaskStore):
        with store._write_lock:
            if not hasattr(store, "_graph_saver"):
                store._graph_saver = SafeSaver(InMemorySaver())
        return store._graph_saver
    if isinstance(store, MongoTaskStore):
        return persistent_saver(store._url, store._database)
    return persistent_saver()
