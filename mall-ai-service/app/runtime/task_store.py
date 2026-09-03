"""Owner-scoped persistence for Mall v3.0 task runtime records.

MongoDB is the production source of truth for safe task/plan/artifact/action
indexes. Redis remains deliberately outside this module: it is used for locks,
short-lived event fan-out and cache only. Unit tests inject the in-memory store
without silently exercising a database-shaped mock in production code.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings
from app.schemas.agent_task import (
    ActionProposal,
    AgentTask,
    AgentTaskEvent,
    ContextPack,
    TaskArtifact,
    TaskPlan,
)


class TaskStoreError(RuntimeError):
    pass


class TaskStoreUnavailable(TaskStoreError):
    pass


class TaskStoreAccessDenied(TaskStoreError):
    """Returned for both missing and non-owned tasks to avoid enumeration."""


class TaskRecordBundle(BaseModel):
    """All persisted records for one owner-scoped task.

    No field may contain a raw customer message, Java credential, full order
    number or unprojected tool/RAG output. Action arguments are limited to
    opaque references and are validated before the runtime saves them.
    """

    model_config = ConfigDict(extra="forbid")

    task: AgentTask
    plans: list[TaskPlan] = Field(default_factory=list, max_length=100)
    artifacts: list[TaskArtifact] = Field(default_factory=list, max_length=128)
    context_packs: list[ContextPack] = Field(default_factory=list, max_length=100)
    action_proposal: ActionProposal | None = None
    action_arguments: dict[str, dict[str, Any]] = Field(default_factory=dict, max_length=8)
    memory_hints: list[str] = Field(default_factory=list, max_length=32)
    events: list[AgentTaskEvent] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def validate_cross_record_bindings(self) -> "TaskRecordBundle":
        """Fail closed when a persisted record mixes task/version/owner data.

        Pydantic validates each record's shape, but a compromised or stale
        Mongo document could still combine a valid artifact from another task
        with a valid action proposal.  Cross-record binding is therefore a
        storage invariant, not something delegated to the model or browser.
        """

        task_id = self.task.task_id
        if any(plan.task_id != task_id for plan in self.plans):
            raise ValueError("计划与任务绑定不一致")
        if any(artifact.task_id != task_id for artifact in self.artifacts):
            raise ValueError("Artifact 与任务绑定不一致")
        if any(pack.task_id != task_id for pack in self.context_packs):
            raise ValueError("Context Pack 与任务绑定不一致")
        if self.action_proposal is not None:
            if self.action_proposal.task_id != task_id:
                raise ValueError("行动提案与任务绑定不一致")
            pending_statuses = {"awaiting_confirmation", "confirmed", "unknown"}
            if self.action_proposal.confirmation_status in pending_statuses:
                if self.task.pending_action_ref != self.action_proposal.proposal_id:
                    raise ValueError("任务待确认引用与行动提案不一致")
            elif self.task.pending_action_ref is not None:
                raise ValueError("已结束的行动提案不能继续占用待确认引用")
            arguments = self.action_arguments.get(self.action_proposal.arguments_ref)
            if arguments is None:
                raise ValueError("行动提案参数引用已失效")
            canonical = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if hashlib.sha256(canonical).hexdigest() != self.action_proposal.content_hash:
                raise ValueError("行动提案内容哈希不匹配")
        elif self.task.pending_action_ref is not None:
            raise ValueError("任务存在无主待确认引用")
        if len({plan.version for plan in self.plans}) != len(self.plans):
            raise ValueError("计划版本重复")
        if self.plans and self.plans[-1].version != self.task.plan_version:
            raise ValueError("任务计划版本未指向最新计划")
        artifact_refs = {artifact.reference for artifact in self.artifacts}
        if any(reference not in artifact_refs for reference in self.task.artifact_refs):
            raise ValueError("任务引用了不存在的 Artifact")
        for arguments in self.action_arguments.values():
            assert_safe_action_arguments(arguments, allow_generated_idempotency_key=True)
        return self

    def latest_plan(self) -> TaskPlan | None:
        return self.plans[-1] if self.plans else None

    def latest_context_pack(self) -> ContextPack | None:
        return self.context_packs[-1] if self.context_packs else None


class TaskStore(Protocol):
    def save(self, bundle: TaskRecordBundle) -> None: ...

    def load_owned(self, task_ref: str, owner_ref: str) -> TaskRecordBundle: ...

    def list_owned(self, owner_ref: str, session_ref: str | None = None) -> list[TaskRecordBundle]: ...


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._items: dict[str, TaskRecordBundle] = {}

    def save(self, bundle: TaskRecordBundle) -> None:
        self._items[bundle.task.task_ref] = copy.deepcopy(bundle)

    def load_owned(self, task_ref: str, owner_ref: str) -> TaskRecordBundle:
        bundle = self._items.get(task_ref)
        if bundle is None or bundle.task.owner_ref != owner_ref:
            raise TaskStoreAccessDenied("任务不存在或不属于当前用户。")
        if bundle.task.expires_at <= time.time():
            self._items.pop(task_ref, None)
            raise TaskStoreAccessDenied("任务不存在或已过期。")
        return copy.deepcopy(bundle)

    def list_owned(self, owner_ref: str, session_ref: str | None = None) -> list[TaskRecordBundle]:
        now = time.time()
        result: list[TaskRecordBundle] = []
        for task_ref, bundle in list(self._items.items()):
            if bundle.task.expires_at <= now:
                self._items.pop(task_ref, None)
                continue
            if bundle.task.owner_ref != owner_ref:
                continue
            if session_ref is not None and bundle.task.session_ref != session_ref:
                continue
            result.append(copy.deepcopy(bundle))
        return sorted(result, key=lambda item: item.task.updated_at, reverse=True)


class MongoTaskStore:
    """Mongo-backed safe task store used by Docker/local integration runs."""

    def __init__(self, url: str, database: str, collection: str) -> None:
        self._url = url
        self._database = database
        self._collection_name = collection
        self._collection = None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            from pymongo import MongoClient
            from pymongo.errors import PyMongoError
        except ImportError as exc:  # pragma: no cover - dependency issue is surfaced in Docker/CI
            raise TaskStoreUnavailable("任务存储依赖不可用。") from exc
        try:
            client = MongoClient(self._url, serverSelectionTimeoutMS=1500)
            collection = client[self._database][self._collection_name]
            collection.create_index([("task.task_ref", 1)], unique=True)
            collection.create_index([("task.owner_ref", 1), ("task.updated_at", -1)])
            collection.create_index("task.expires_at", expireAfterSeconds=0)
        except PyMongoError as exc:
            raise TaskStoreUnavailable("任务存储暂时不可用。") from exc
        self._collection = collection
        return collection

    def save(self, bundle: TaskRecordBundle) -> None:
        try:
            collection = self._get_collection()
            collection.replace_one(
                {"task.task_ref": bundle.task.task_ref},
                bundle.model_dump(mode="json"),
                upsert=True,
            )
        except TaskStoreUnavailable:
            raise
        except Exception as exc:  # pragma: no cover - pymongo-specific types vary by installed version
            raise TaskStoreUnavailable("任务存储暂时不可用。") from exc

    def load_owned(self, task_ref: str, owner_ref: str) -> TaskRecordBundle:
        try:
            document = self._get_collection().find_one(
                {"task.task_ref": task_ref, "task.owner_ref": owner_ref},
                {"_id": 0},
            )
        except TaskStoreUnavailable:
            raise
        except Exception as exc:  # pragma: no cover
            raise TaskStoreUnavailable("任务存储暂时不可用。") from exc
        if not isinstance(document, dict):
            raise TaskStoreAccessDenied("任务不存在或不属于当前用户。")
        try:
            bundle = TaskRecordBundle.model_validate(document)
        except Exception as exc:
            raise TaskStoreUnavailable("任务存储记录无法安全读取。") from exc
        if bundle.task.expires_at <= time.time():
            raise TaskStoreAccessDenied("任务不存在或已过期。")
        return bundle

    def list_owned(self, owner_ref: str, session_ref: str | None = None) -> list[TaskRecordBundle]:
        query: dict[str, Any] = {"task.owner_ref": owner_ref, "task.expires_at": {"$gt": time.time()}}
        if session_ref is not None:
            query["task.session_ref"] = session_ref
        try:
            rows = list(
                self._get_collection().find(query, {"_id": 0}).sort("task.updated_at", -1)
            )
            return [TaskRecordBundle.model_validate(row) for row in rows]
        except TaskStoreUnavailable:
            raise
        except Exception as exc:  # pragma: no cover
            raise TaskStoreUnavailable("任务存储暂时不可用。") from exc


_store: TaskStore | None = None


def owner_ref_for_member(member_id: int) -> str:
    if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
        raise TaskStoreAccessDenied("当前身份无法创建任务。")
    return "owner-" + hashlib.sha256(f"mall-v3-owner:{member_id}".encode("utf-8")).hexdigest()[:24]


def session_ref_for_session(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128:
        raise TaskStoreAccessDenied("会话标识不合法。")
    return "session-" + hashlib.sha256(
        f"mall-v3-session:{session_id}".encode("utf-8")
    ).hexdigest()[:24]


def assert_safe_action_arguments(
    arguments: Mapping[str, Any],
    *,
    allow_generated_idempotency_key: bool = False,
) -> None:
    """Keep action arguments opaque and free of raw identifiers.

    ``idempotencyKey`` is deliberately exceptional: it may only be accepted
    when the Runtime has generated it server-side.  Model supplied values are
    rejected by default, while the generated value is validated as a fixed
    lower-case hex token rather than being mistaken for a customer order
    number by the generic long-number guard.
    """

    if not isinstance(arguments, Mapping) or len(arguments) > 8:
        raise TaskStoreError("行动参数不合法。")
    forbidden_keys = {"authorization", "token", "password", "order_sn", "orderSn", "address", "phone"}
    for key, value in arguments.items():
        if key == "idempotencyKey":
            if (
                not allow_generated_idempotency_key
                or not isinstance(value, str)
                or len(value) != 32
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise TaskStoreError("幂等键必须由服务端生成。")
            continue
        if key in forbidden_keys or not isinstance(key, str) or len(key) > 64:
            raise TaskStoreError("行动参数包含禁止字段。")
        _assert_safe_action_value(value)


def _assert_safe_action_value(value: Any) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in ("bearer ", "token=", "password")):
            raise TaskStoreError("行动参数包含禁止内容。")
        if re_contains_long_number(value):
            raise TaskStoreError("行动参数必须使用 opaque reference。")
        return
    if isinstance(value, (bool, int, float)) or value is None:
        return
    if isinstance(value, list):
        for item in value:
            _assert_safe_action_value(item)
        return
    if isinstance(value, Mapping):
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str) or nested_key in {"order_sn", "token", "authorization", "idempotencyKey"}:
                raise TaskStoreError("行动参数包含禁止字段。")
            _assert_safe_action_value(nested_value)
        return
    raise TaskStoreError("行动参数类型不支持。")


def re_contains_long_number(value: str) -> bool:
    import re

    return bool(re.search(r"(?<!\d)\d{6,}(?!\d)", value))


def get_task_store() -> TaskStore:
    global _store
    if _store is not None:
        return _store
    backend = settings.agent_task_store_backend.strip().lower()
    if backend == "mongo":
        _store = MongoTaskStore(
            settings.agent_task_mongo_url,
            settings.agent_task_mongo_database,
            settings.agent_task_mongo_collection,
        )
    elif backend == "memory":
        _store = InMemoryTaskStore()
    else:
        raise TaskStoreUnavailable("AGENT_TASK_STORE_BACKEND 只能是 mongo 或 memory。")
    return _store


def set_task_store_for_tests(store: TaskStore | None) -> None:
    global _store
    _store = store
