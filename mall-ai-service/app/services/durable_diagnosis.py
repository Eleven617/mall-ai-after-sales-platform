"""Privacy-safe durable interruption for the read-only diagnosis graph.

The normal diagnosis graph deliberately keeps the rich request state in memory:
it can contain the customer's message, Java bearer token, raw tool responses and
RAG content.  This module never checkpoints that state.  It stores only a
small allow-listed waiting state and uses an opaque, one-request resume handle
to pass the customer's newly supplied identifier into ``interrupt()``.

As a result a service restart can recover *what is waiting* without turning a
LangGraph checkpoint into a second conversation-history or sensitive-data store.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.schemas.diagnosis import DiagnosisResult
from app.schemas.tool import ToolCall
from app.services.fact_presentation_service import (
    build_verified_facts,
    render_verified_facts_summary,
)
from app.services.identifier_extraction import extract_order_sn, extract_sku_id
from app.services.mall_client import MallApiClientError, MallOrderNotAccessibleError
from app.services.tool_context import ToolExecutionContext
from app.services.tool_registry import ToolInputError, ToolNotFoundError
from app.services.trace_service import record_trace


DIAGNOSIS_CHECKPOINT_SCHEMA_VERSION = "diagnosis-resume-v1"
DIAGNOSIS_CHECKPOINT_FLOW = "read_only_diagnosis"
_WAITING_FIELD_BY_TOOL: dict[str, Literal["order_sn", "sku_id"]] = {
    "order_service": "order_sn",
    "logistics_service": "order_sn",
    "inventory_service": "sku_id",
}
_PENDING_CANCEL_MESSAGES = {
    "取消",
    "取消查询",
    "取消当前查询",
    "不查了",
    "先不查了",
}
_PROHIBITED_STATE_KEYS = {
    "authorization",
    "bearer",
    "token",
    "user_message",
    "message",
    "messages",
    "order_sn",
    "tracking_no",
    "tool_context",
    "tool_result",
    "tool_results",
    "rag_context",
    "rag_sources",
    "retrieved_context",
    "prompt",
}


class DiagnosisCheckpointError(RuntimeError):
    """Raised when a durable checkpoint cannot be used safely."""


class DiagnosisCheckpointStorageError(DiagnosisCheckpointError):
    """Raised when the configured durable checkpoint store is unavailable."""


class ResumableDiagnosisState(BaseModel):
    """The complete allow-listed state permitted in a durable checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["diagnosis-resume-v1"]
    flow: Literal["read_only_diagnosis"]
    owner_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    waiting_for: Literal["order_sn", "sku_id"]
    tool_name: Literal["order_service", "logistics_service", "inventory_service"]
    continuation_mode: Literal["single_read", "order_then_logistics"] = "single_read"
    status: Literal["awaiting_input", "completed"] = "awaiting_input"
    created_at: float
    expires_at: float
    resume_count: int = Field(default=0, ge=0, le=3)
    completed_at: float | None = None


class DurableDiagnosisGraphState(TypedDict, total=False):
    """LangGraph state intentionally mirrors only ``ResumableDiagnosisState``."""

    schema_version: str
    flow: str
    owner_fingerprint: str
    waiting_for: str
    tool_name: str
    continuation_mode: str
    status: str
    created_at: float
    expires_at: float
    resume_count: int
    completed_at: float | None


@dataclass(frozen=True)
class DurableDiagnosisStart:
    pending: bool
    status: Literal["started", "already_pending", "unavailable"]


@dataclass(frozen=True)
class DurableDiagnosisResume:
    """Result of inspecting, cancelling or resuming a pending diagnosis."""

    status: Literal[
        "not_found",
        "awaiting_input",
        "resumed",
        "cancelled",
        "completed",
        "expired",
        "incompatible",
        "busy",
        "unavailable",
    ]
    answer: str
    tool_call: ToolCall | None = None
    tool_result: dict[str, Any] | None = None
    tool_results: list[tuple[ToolCall, dict[str, Any]]] = field(default_factory=list)
    diagnosis: DiagnosisResult | None = None


CallTool = Callable[[ToolCall, ToolExecutionContext | None], dict[str, Any]]


class SanitizedMemorySaver(InMemorySaver):
    """A LangGraph saver that never persists a raw ``Command(resume=...)``.

    LangGraph holds the resume payload in request memory long enough for the
    interrupted node to run.  Dropping the special ``__resume__`` write keeps
    a raw order number out of the stored checkpoint.  If a process crashes in
    that tiny interval, the safe outcome is that the customer supplies the
    identifier again; no business write exists in this workflow.
    """

    def __init__(self) -> None:
        super().__init__()
        self._resume_locks: dict[str, threading.Lock] = {}
        self._resume_locks_guard = threading.Lock()

    def put(self, config: dict[str, Any], checkpoint: Any, metadata: Any, new_versions: Any) -> dict[str, Any]:
        _assert_safe_checkpoint_payload(checkpoint)
        _assert_safe_checkpoint_payload(metadata)
        return super().put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        # ``__resume__`` can contain the message/order number supplied by the
        # customer.  It is intentionally request-memory only.
        safe_writes = [write for write in writes if write[0] != "__resume__"]
        _assert_safe_checkpoint_payload(safe_writes)
        super().put_writes(config, safe_writes, task_id, task_path)

    def acquire_resume_lock(self, thread_id: str, ttl_seconds: int) -> str | None:
        del ttl_seconds  # In-memory locks are released in the request finally block.
        with self._resume_locks_guard:
            lock = self._resume_locks.setdefault(thread_id, threading.Lock())
        if not lock.acquire(blocking=False):
            return None
        return thread_id

    def release_resume_lock(self, thread_id: str, token: str) -> None:
        if token != thread_id:
            return
        with self._resume_locks_guard:
            lock = self._resume_locks.get(thread_id)
        if lock and lock.locked():
            lock.release()


class RedisSanitizedCheckpointer(SanitizedMemorySaver):
    """Redis-backed persistence for the small, already-sanitized LangGraph state.

    LangGraph's stock Redis saver is not bundled with this project and normally
    expects Redis modules that the local demo does not run.  This adapter keeps
    the proven LangGraph checkpoint protocol while persisting only the safe
    in-memory saver representation as bounded JSON in ordinary Redis.
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str,
        ttl_seconds: int,
        *,
        redis_client: Any | None = None,
    ) -> None:
        super().__init__()
        if redis_client is None:
            try:
                from redis import Redis
            except ImportError as exc:  # pragma: no cover - requirements protects this
                raise DiagnosisCheckpointStorageError("未安装 Redis 客户端。") from exc
            redis_client = Redis.from_url(redis_url, decode_responses=True)
        self._client = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._ttl_seconds = ttl_seconds
        self._loaded_threads: set[str] = set()

    def get_tuple(self, config: dict[str, Any]):  # type: ignore[override]
        self._load_thread(_thread_id_from_config(config))
        return super().get_tuple(config)

    def put(self, config: dict[str, Any], checkpoint: Any, metadata: Any, new_versions: Any) -> dict[str, Any]:
        thread_id = _thread_id_from_config(config)
        self._load_thread(thread_id)
        saved = super().put(config, checkpoint, metadata, new_versions)
        self._persist_thread(thread_id)
        return saved

    def put_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = _thread_id_from_config(config)
        self._load_thread(thread_id)
        super().put_writes(config, writes, task_id, task_path)
        self._persist_thread(thread_id)

    def delete_thread(self, thread_id: str) -> None:
        # Deletion must also work for an incompatible/corrupt record.  Do not
        # load it first: a malformed payload is precisely the case where the
        # safe action is to discard the whole owner-bound thread.
        super().delete_thread(thread_id)
        try:
            self._client.delete(self._key(thread_id))
            self._client.delete(self._lock_key(thread_id))
        except Exception as exc:
            raise DiagnosisCheckpointStorageError("诊断进度暂时无法清理。") from exc
        self._loaded_threads.add(thread_id)

    def acquire_resume_lock(self, thread_id: str, ttl_seconds: int) -> str | None:
        token = secrets.token_urlsafe(18)
        try:
            acquired = self._client.set(
                self._lock_key(thread_id), token, nx=True, ex=max(1, ttl_seconds)
            )
        except Exception as exc:
            raise DiagnosisCheckpointStorageError("诊断进度暂时不可用。") from exc
        return token if acquired else None

    def release_resume_lock(self, thread_id: str, token: str) -> None:
        try:
            # A token check avoids deleting a lock that expired and was acquired
            # by a later recovery request.  The short lock only protects a
            # read-only step; an expired lock fails closed to a retry prompt.
            if self._client.get(self._lock_key(thread_id)) == token:
                self._client.delete(self._lock_key(thread_id))
        except Exception:
            # TTL eventually releases a lock even if Redis briefly disappears.
            return

    def raw_record_for_tests(self, thread_id: str) -> str | None:
        """Expose the serialized safe record only to focused unit tests."""
        try:
            return self._client.get(self._key(thread_id))
        except Exception as exc:  # pragma: no cover - test helper fallback
            raise DiagnosisCheckpointStorageError("诊断进度暂时不可用。") from exc

    def _load_thread(self, thread_id: str) -> None:
        if thread_id in self._loaded_threads:
            return
        try:
            raw = self._client.get(self._key(thread_id))
        except Exception as exc:
            raise DiagnosisCheckpointStorageError("诊断进度暂时不可用。") from exc
        if raw:
            try:
                payload = json.loads(raw)
                self._restore_thread(thread_id, payload)
            except (TypeError, ValueError, KeyError, UnicodeError) as exc:
                raise DiagnosisCheckpointError("诊断进度版本不兼容或数据不安全。") from exc
        self._loaded_threads.add(thread_id)

    def _persist_thread(self, thread_id: str) -> None:
        payload = self._dump_thread(thread_id)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > settings.diagnosis_checkpoint_max_bytes:
            raise DiagnosisCheckpointStorageError("诊断进度超出安全容量限制。")
        try:
            self._client.set(self._key(thread_id), encoded, ex=self._ttl_seconds)
        except Exception as exc:
            raise DiagnosisCheckpointStorageError("诊断进度暂时无法保存。") from exc

    def _dump_thread(self, thread_id: str) -> dict[str, Any]:
        storage_payload: dict[str, Any] = {}
        for namespace, checkpoints in self.storage.get(thread_id, {}).items():
            storage_payload[namespace] = {
                checkpoint_id: {
                    "checkpoint": _pack_typed(checkpoint),
                    "metadata": _pack_typed(metadata),
                    "parent": parent,
                }
                for checkpoint_id, (checkpoint, metadata, parent) in checkpoints.items()
            }

        writes_payload: list[dict[str, Any]] = []
        for (stored_thread, namespace, checkpoint_id), entries in self.writes.items():
            if stored_thread != thread_id:
                continue
            writes_payload.append(
                {
                    "namespace": namespace,
                    "checkpoint_id": checkpoint_id,
                    "entries": [
                        {
                            "task_key": task_key,
                            "index": index,
                            "task_id": task_id,
                            "channel": channel,
                            "value": _pack_typed(value),
                            "task_path": task_path,
                        }
                        for (task_key, index), (task_id, channel, value, task_path) in entries.items()
                    ],
                }
            )

        blobs_payload: list[dict[str, Any]] = []
        for (stored_thread, namespace, channel, version), value in self.blobs.items():
            if stored_thread != thread_id:
                continue
            blobs_payload.append(
                {
                    "namespace": namespace,
                    "channel": channel,
                    "version": version,
                    "value": _pack_typed(value),
                }
            )

        return {
            "format": "langgraph-sanitized-memory-v1",
            "storage": storage_payload,
            "writes": writes_payload,
            "blobs": blobs_payload,
        }

    def _restore_thread(self, thread_id: str, payload: dict[str, Any]) -> None:
        if payload.get("format") != "langgraph-sanitized-memory-v1":
            raise ValueError("unsupported checkpoint format")

        restored_storage: defaultdict[str, dict[str, Any]] = defaultdict(dict)
        for namespace, checkpoints in payload.get("storage", {}).items():
            if not isinstance(namespace, str) or not isinstance(checkpoints, dict):
                raise ValueError("invalid checkpoint storage")
            for checkpoint_id, entry in checkpoints.items():
                if not isinstance(checkpoint_id, str) or not isinstance(entry, dict):
                    raise ValueError("invalid checkpoint entry")
                restored_storage[namespace][checkpoint_id] = (
                    _unpack_typed(entry["checkpoint"]),
                    _unpack_typed(entry["metadata"]),
                    entry.get("parent"),
                )
        self.storage[thread_id] = restored_storage

        for record in payload.get("writes", []):
            if not isinstance(record, dict):
                raise ValueError("invalid checkpoint writes")
            namespace = record["namespace"]
            checkpoint_id = record["checkpoint_id"]
            if not isinstance(namespace, str) or not isinstance(checkpoint_id, str):
                raise ValueError("invalid checkpoint write key")
            entries: dict[tuple[str, int], tuple[str, str, tuple[str, bytes], str]] = {}
            for entry in record.get("entries", []):
                if not isinstance(entry, dict):
                    raise ValueError("invalid checkpoint write")
                task_key = entry["task_key"]
                index = entry["index"]
                task_id = entry["task_id"]
                channel = entry["channel"]
                task_path = entry["task_path"]
                if not (
                    isinstance(task_key, str)
                    and isinstance(index, int)
                    and isinstance(task_id, str)
                    and isinstance(channel, str)
                    and isinstance(task_path, str)
                ):
                    raise ValueError("invalid checkpoint write fields")
                entries[(task_key, index)] = (
                    task_id,
                    channel,
                    _unpack_typed(entry["value"]),
                    task_path,
                )
            self.writes[(thread_id, namespace, checkpoint_id)] = entries

        for record in payload.get("blobs", []):
            if not isinstance(record, dict):
                raise ValueError("invalid checkpoint blob")
            namespace = record["namespace"]
            channel = record["channel"]
            version = record["version"]
            if not isinstance(namespace, str) or not isinstance(channel, str):
                raise ValueError("invalid checkpoint blob fields")
            self.blobs[(thread_id, namespace, channel, version)] = _unpack_typed(
                record["value"]
            )

    def _key(self, thread_id: str) -> str:
        return f"{self._key_prefix}:{thread_id}"

    def _lock_key(self, thread_id: str) -> str:
        return f"{self._key_prefix}:lock:{thread_id}"


class DurableDiagnosisManager:
    """Owns the safe lifecycle around a LangGraph interrupt/checkpoint."""

    def __init__(
        self,
        checkpointer: SanitizedMemorySaver,
        *,
        ttl_seconds: int = settings.diagnosis_checkpoint_ttl_seconds,
        lock_seconds: int = settings.diagnosis_checkpoint_lock_seconds,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._checkpointer = checkpointer
        self._ttl_seconds = ttl_seconds
        self._lock_seconds = lock_seconds
        self._now = now

    def begin(
        self,
        *,
        session_id: str,
        member_id: int | None,
        pending_tool_call: ToolCall,
        continuation_mode: Literal["single_read", "order_then_logistics"] = "single_read",
    ) -> DurableDiagnosisStart:
        waiting_for = _WAITING_FIELD_BY_TOOL.get(pending_tool_call.name)
        if waiting_for is None:
            raise DiagnosisCheckpointError("该诊断等待状态不能安全持久化。")
        thread_id = build_diagnosis_thread_id(session_id, member_id)
        owner_fingerprint = build_owner_fingerprint(member_id)
        try:
            try:
                existing = self._load_state(thread_id)
            except DiagnosisCheckpointError:
                # A stale schema/corrupt safe record must not be interpreted as
                # a live task.  Remove it before creating a fresh, versioned
                # checkpoint for the new diagnosis request.
                self._checkpointer.delete_thread(thread_id)
                existing = None
            if existing is not None and existing.status == "awaiting_input":
                return DurableDiagnosisStart(pending=True, status="already_pending")
            if existing is not None:
                self._checkpointer.delete_thread(thread_id)

            now = self._now()
            state = ResumableDiagnosisState(
                schema_version=DIAGNOSIS_CHECKPOINT_SCHEMA_VERSION,
                flow=DIAGNOSIS_CHECKPOINT_FLOW,
                owner_fingerprint=owner_fingerprint,
                waiting_for=waiting_for,
                tool_name=pending_tool_call.name,
                continuation_mode=continuation_mode,
                created_at=now,
                expires_at=now + self._ttl_seconds,
            )
            graph, _ = self._build_graph({}, None, None)
            graph.invoke(state.model_dump(), _graph_config(thread_id))
            saved = self._load_state(thread_id)
            if saved is None or saved.status != "awaiting_input":
                raise DiagnosisCheckpointError("诊断进度未能安全进入等待状态。")
        except DiagnosisCheckpointStorageError:
            return DurableDiagnosisStart(pending=False, status="unavailable")

        record_trace(
            "diagnosis_checkpoint",
            "interrupt_persisted",
            session_id,
            node="await_human_input",
        )
        return DurableDiagnosisStart(pending=True, status="started")

    def resume_or_inspect(
        self,
        *,
        session_id: str,
        member_id: int | None,
        message: str,
        tool_context: ToolExecutionContext,
        call_tool_fn: CallTool,
    ) -> DurableDiagnosisResume | None:
        thread_id = build_diagnosis_thread_id(session_id, member_id)
        try:
            state = self._load_state(thread_id)
        except DiagnosisCheckpointStorageError:
            return DurableDiagnosisResume(
                status="unavailable",
                answer="诊断进度暂时不可用，请稍后重试；系统未执行任何查询或写操作。",
            )
        except DiagnosisCheckpointError:
            return self._discard_incompatible(thread_id)
        if state is None:
            return None
        if state.owner_fingerprint != build_owner_fingerprint(member_id):
            # This should be unreachable because the thread ID is owner-bound,
            # but validates the stored contract before any resume is attempted.
            return DurableDiagnosisResume(
                status="not_found",
                answer="",
            )
        if state.schema_version != DIAGNOSIS_CHECKPOINT_SCHEMA_VERSION:
            return self._discard_incompatible(thread_id)
        if state.expires_at <= self._now():
            return self._discard_expired(thread_id)
        if state.status == "completed":
            return DurableDiagnosisResume(
                status="completed",
                answer="本次诊断已恢复完成，请查看上一条查询结果；未重复执行查询。",
            )

        normalized = _normalize_cancel_message(message)
        if normalized in _PENDING_CANCEL_MESSAGES:
            try:
                self._checkpointer.delete_thread(thread_id)
            except DiagnosisCheckpointStorageError:
                return DurableDiagnosisResume(
                    status="unavailable",
                    answer="诊断进度暂时不可用，请稍后重试；系统未执行任何查询或写操作。",
                )
            record_trace("diagnosis_checkpoint", "cancelled", session_id, node="await_human_input")
            return DurableDiagnosisResume(
                status="cancelled",
                answer="已取消当前可恢复诊断，未执行任何查询或写操作。",
            )

        value, clarification = _resolve_waiting_identifier(state.waiting_for, message)
        if clarification is not None:
            return DurableDiagnosisResume(
                status="awaiting_input",
                answer=clarification,
                tool_call=ToolCall(name=state.tool_name, arguments={}),
            )
        if value is None:
            return DurableDiagnosisResume(
                status="awaiting_input",
                answer=_waiting_prompt(state.waiting_for),
                tool_call=ToolCall(name=state.tool_name, arguments={}),
            )

        try:
            lock_token = self._checkpointer.acquire_resume_lock(thread_id, self._lock_seconds)
        except DiagnosisCheckpointStorageError:
            return DurableDiagnosisResume(
                status="unavailable",
                answer="诊断进度暂时不可用，请稍后重试；系统未执行任何查询或写操作。",
            )
        if lock_token is None:
            return DurableDiagnosisResume(
                status="busy",
                answer="当前诊断正在恢复，请稍候后查看结果；系统未重复执行查询。",
            )

        execution: dict[str, DurableDiagnosisResume] = {}
        resume_ref = secrets.token_urlsafe(24)
        try:
            # Reload after acquiring the lock so a simultaneous request cannot
            # resurrect a completed/cancelled checkpoint.
            latest = self._load_state(thread_id)
            if latest is None or latest.status != "awaiting_input":
                return DurableDiagnosisResume(
                    status="completed",
                    answer="本次诊断已恢复完成，请查看上一条查询结果；未重复执行查询。",
                )
            graph, holder = self._build_graph(
                {resume_ref: message},
                tool_context,
                call_tool_fn,
            )
            graph.invoke(Command(resume=resume_ref), _graph_config(thread_id))
            result = holder.get("result")
            if result is None:
                return DurableDiagnosisResume(
                    status="unavailable",
                    answer="诊断恢复未完成，请重新提供所需信息后再试；系统未执行写操作。",
                )
            execution["result"] = result
        except DiagnosisCheckpointStorageError:
            return DurableDiagnosisResume(
                status="unavailable",
                answer="诊断进度暂时不可用，请稍后重试；系统未执行任何查询或写操作。",
            )
        finally:
            self._checkpointer.release_resume_lock(thread_id, lock_token)

        result = execution["result"]
        record_trace(
            "diagnosis_checkpoint",
            "resumed",
            session_id,
            node="resume_read_only_tool",
            tool_name=result.tool_call.name if result.tool_call else None,
        )
        return result

    def clear_for_session(self, session_id: str, member_id: int | None) -> None:
        """Delete only this owner-bound diagnosis checkpoint, e.g. on chat deletion."""
        self._checkpointer.delete_thread(build_diagnosis_thread_id(session_id, member_id))

    def _load_state(self, thread_id: str) -> ResumableDiagnosisState | None:
        checkpoint = self._checkpointer.get(_graph_config(thread_id))
        if checkpoint is None:
            return None
        values = checkpoint.get("channel_values", {})
        raw_state = {
            field: values.get(field)
            for field in ResumableDiagnosisState.model_fields
            if field in values
        }
        if not raw_state:
            return None
        try:
            return ResumableDiagnosisState.model_validate(raw_state)
        except ValidationError as exc:
            raise DiagnosisCheckpointError("诊断进度版本不兼容。") from exc

    def _discard_expired(self, thread_id: str) -> DurableDiagnosisResume:
        try:
            self._checkpointer.delete_thread(thread_id)
        except DiagnosisCheckpointStorageError:
            return DurableDiagnosisResume(
                status="unavailable",
                answer="诊断进度暂时不可用，请稍后重试；系统未执行任何查询或写操作。",
            )
        return DurableDiagnosisResume(
            status="expired",
            answer="此前等待的诊断已过期，请重新描述问题后再试；系统未执行写操作。",
        )

    def _discard_incompatible(self, thread_id: str) -> DurableDiagnosisResume:
        try:
            self._checkpointer.delete_thread(thread_id)
        except DiagnosisCheckpointStorageError:
            return DurableDiagnosisResume(
                status="unavailable",
                answer="诊断进度暂时不可用，请稍后重试；系统未执行任何查询或写操作。",
            )
        return DurableDiagnosisResume(
            status="incompatible",
            answer="此前诊断进度无法安全恢复，请重新描述问题后再试；系统未执行写操作。",
        )

    def _build_graph(
        self,
        resume_messages: dict[str, str],
        tool_context: ToolExecutionContext | None,
        call_tool_fn: CallTool | None,
    ) -> tuple[Any, dict[str, DurableDiagnosisResume]]:
        holder: dict[str, DurableDiagnosisResume] = {}

        def await_human_input(state: DurableDiagnosisGraphState) -> dict[str, Any]:
            # No tool or other effect occurs before interrupt: LangGraph will
            # re-run this node on Command(resume=...), so this ordering matters.
            resume_ref = interrupt(_safe_interrupt_payload(state))
            message = resume_messages.pop(str(resume_ref), None)
            if message is None or tool_context is None or call_tool_fn is None:
                holder["result"] = DurableDiagnosisResume(
                    status="unavailable",
                    answer="诊断恢复未完成，请重新提供所需信息后再试；系统未执行写操作。",
                )
            else:
                holder["result"] = _execute_resumed_read_only_tool(
                    state=state,
                    message=message,
                    tool_context=tool_context,
                    call_tool_fn=call_tool_fn,
                )
            return {
                "status": "completed",
                "resume_count": min(int(state.get("resume_count", 0)) + 1, 3),
                "completed_at": self._now(),
            }

        builder = StateGraph(DurableDiagnosisGraphState)
        builder.add_node("await_human_input", await_human_input)
        builder.add_edge(START, "await_human_input")
        builder.add_edge("await_human_input", END)
        return builder.compile(checkpointer=self._checkpointer), holder


def build_diagnosis_thread_id(session_id: str, member_id: int | None) -> str:
    """Create a server-derived opaque thread ID, never a browser supplied ID."""
    owner_scope = _owner_scope(member_id)
    material = f"diagnosis-thread-v1\0{owner_scope}\0{session_id}".encode("utf-8")
    digest = hmac.new(
        settings.diagnosis_checkpoint_secret.encode("utf-8"), material, hashlib.sha256
    ).hexdigest()
    return f"diagnosis-thread-v1-{digest}"


def build_owner_fingerprint(member_id: int | None) -> str:
    material = f"diagnosis-owner-v1\0{_owner_scope(member_id)}".encode("utf-8")
    return hmac.new(
        settings.diagnosis_checkpoint_secret.encode("utf-8"), material, hashlib.sha256
    ).hexdigest()


def get_durable_diagnosis_manager() -> DurableDiagnosisManager:
    global _manager
    if _manager is None:
        backend = settings.diagnosis_checkpoint_backend.strip().lower()
        if backend == "redis":
            saver: SanitizedMemorySaver = RedisSanitizedCheckpointer(
                settings.redis_url,
                settings.diagnosis_checkpoint_key_prefix,
                settings.diagnosis_checkpoint_ttl_seconds,
            )
        elif backend == "memory":
            saver = SanitizedMemorySaver()
        else:
            raise DiagnosisCheckpointError(
                "DIAGNOSIS_CHECKPOINT_BACKEND 只能是 memory 或 redis。"
            )
        _manager = DurableDiagnosisManager(saver)
    return _manager


def set_durable_diagnosis_manager_for_tests(
    manager: DurableDiagnosisManager | None,
) -> None:
    global _manager
    _manager = manager


def begin_durable_diagnosis(
    *,
    session_id: str,
    member_id: int | None,
    pending_tool_call: ToolCall,
    continuation_mode: Literal["single_read", "order_then_logistics"] = "single_read",
) -> DurableDiagnosisStart:
    return get_durable_diagnosis_manager().begin(
        session_id=session_id,
        member_id=member_id,
        pending_tool_call=pending_tool_call,
        continuation_mode=continuation_mode,
    )


def resume_durable_diagnosis(
    *,
    session_id: str,
    member_id: int | None,
    message: str,
    tool_context: ToolExecutionContext,
    call_tool_fn: CallTool,
) -> DurableDiagnosisResume | None:
    return get_durable_diagnosis_manager().resume_or_inspect(
        session_id=session_id,
        member_id=member_id,
        message=message,
        tool_context=tool_context,
        call_tool_fn=call_tool_fn,
    )


def clear_durable_diagnosis(
    session_id: str,
    member_id: int | None,
) -> None:
    get_durable_diagnosis_manager().clear_for_session(session_id, member_id)


def _execute_resumed_read_only_tool(
    *,
    state: DurableDiagnosisGraphState,
    message: str,
    tool_context: ToolExecutionContext,
    call_tool_fn: CallTool,
) -> DurableDiagnosisResume:
    waiting_for = state.get("waiting_for")
    tool_name = state.get("tool_name")
    if waiting_for not in {"order_sn", "sku_id"} or tool_name not in _WAITING_FIELD_BY_TOOL:
        return DurableDiagnosisResume(
            status="unavailable",
            answer="诊断进度无法安全恢复，请重新描述问题后再试；系统未执行写操作。",
        )
    value, clarification = _resolve_waiting_identifier(waiting_for, message)
    if value is None or clarification is not None:
        # This can only happen if the caller bypassed the public resolver.  It
        # still must not trigger a tool call or persist the raw message.
        return DurableDiagnosisResume(
            status="awaiting_input",
            answer=clarification or _waiting_prompt(waiting_for),
            tool_call=ToolCall(name=tool_name, arguments={}),
        )
    call = ToolCall(name=tool_name, arguments={waiting_for: value})
    try:
        result = call_tool_fn(call, tool_context)
    except MallOrderNotAccessibleError:
        return DurableDiagnosisResume(
            status="resumed",
            answer="未找到当前账号可查询的订单，请核对订单号后重试。",
            tool_call=call,
        )
    except ToolNotFoundError:
        return DurableDiagnosisResume(
            status="resumed",
            answer="当前查询工具暂不可用，请稍后重试；未执行任何写操作。",
            tool_call=call,
        )
    except ToolInputError:
        return DurableDiagnosisResume(
            status="resumed",
            answer="查询参数不完整或格式不正确，请重新提供所需信息。",
            tool_call=call,
        )
    except MallApiClientError as exc:
        return DurableDiagnosisResume(
            status="resumed",
            answer=str(exc),
            tool_call=call,
        )
    except Exception:
        return DurableDiagnosisResume(
            status="resumed",
            answer="查询暂时执行失败，请稍后重试；未执行任何写操作。",
            tool_call=call,
        )

    tool_results = [(call, result)]
    if _is_tool_error(result):
        return DurableDiagnosisResume(
            status="resumed",
            answer="订单查询未完成，请稍后重试或联系人工客服；未执行任何写操作。",
            tool_call=call,
            tool_result=result,
            tool_results=tool_results,
        )

    # A complex order-exception route has already been selected by the bounded
    # intent model.  Its factual threshold is therefore explicit: verify the
    # order first, then its logistics using the identifier held only in this
    # request.  This remains a fixed read-only continuation, not a new LLM
    # decision or a persistent raw tool trace.
    if (
        state.get("continuation_mode") == "order_then_logistics"
        and call.name == "order_service"
    ):
        logistics_call = ToolCall(
            name="logistics_service",
            arguments={"order_sn": value},
        )
        try:
            logistics_result = call_tool_fn(logistics_call, tool_context)
        except MallOrderNotAccessibleError:
            return DurableDiagnosisResume(
                status="resumed",
                answer="未找到当前账号可查询的订单，请核对订单号后重试。",
                tool_call=call,
                tool_result=result,
                tool_results=tool_results,
            )
        except ToolNotFoundError:
            return DurableDiagnosisResume(
                status="resumed",
                answer="物流查询工具暂不可用，请稍后重试；未执行任何写操作。",
                tool_call=call,
                tool_result=result,
                tool_results=tool_results,
            )
        except ToolInputError:
            return DurableDiagnosisResume(
                status="resumed",
                answer="物流查询参数不完整，请重新提供订单号。",
                tool_call=call,
                tool_result=result,
                tool_results=tool_results,
            )
        except MallApiClientError as exc:
            return DurableDiagnosisResume(
                status="resumed",
                answer=str(exc),
                tool_call=call,
                tool_result=result,
                tool_results=tool_results,
            )
        except Exception:
            return DurableDiagnosisResume(
                status="resumed",
                answer="物流查询暂时执行失败，请稍后重试；未执行任何写操作。",
                tool_call=call,
                tool_result=result,
                tool_results=tool_results,
            )

        tool_results.append((logistics_call, logistics_result))
        if _is_tool_error(logistics_result):
            return DurableDiagnosisResume(
                status="resumed",
                answer="订单已核验，但物流查询未完成；系统未给出售后或政策结论。",
                tool_call=call,
                tool_result=result,
                tool_results=tool_results,
            )
        diagnosis = _build_resumed_order_diagnosis(tool_results)
        return DurableDiagnosisResume(
            status="resumed",
            answer=_render_resumed_order_diagnosis(diagnosis),
            tool_call=call,
            tool_result=result,
            tool_results=tool_results,
            diagnosis=diagnosis,
        )

    return DurableDiagnosisResume(
        status="resumed",
        answer="",
        tool_call=call,
        tool_result=result,
        tool_results=tool_results,
    )


def _build_resumed_order_diagnosis(
    tool_results: list[tuple[ToolCall, dict[str, Any]]],
) -> DiagnosisResult:
    facts = build_verified_facts(
        [(tool_call.name, result) for tool_call, result in tool_results]
    )
    logistics = next(
        (result for call, result in tool_results if call.name == "logistics_service"),
        {},
    )
    status = str(logistics.get("order_status", ""))
    if any(marker in status for marker in ("异常", "退回", "失败", "拒收")):
        category = "delivery_exception"
    elif any(marker in status for marker in ("运输中", "派送", "已发货", "配送")):
        category = "delivery_in_transit"
    else:
        category = "order_state_review"
    return DiagnosisResult(
        category=category,
        evidence_status="partial",
        verified_facts=facts,
        allowed_next_steps=["continue_after_sales", "contact_human"],
    )


def _render_resumed_order_diagnosis(diagnosis: DiagnosisResult) -> str:
    category_label = {
        "delivery_in_transit": "当前物流仍在运输或派送中",
        "delivery_exception": "当前物流存在异常状态",
        "order_state_review": "已完成订单与物流状态核验",
    }.get(diagnosis.category, "已完成订单与物流状态核验")
    return (
        f"{render_verified_facts_summary(diagnosis.verified_facts)}\n"
        f"当前判断：{category_label}。如需办理售后，可以继续进入受控售后流程；系统不会直接提交。"
    )


def _is_tool_error(result: Any) -> bool:
    return isinstance(result, dict) and bool(result.get("error"))


def _safe_interrupt_payload(state: DurableDiagnosisGraphState) -> dict[str, Any]:
    waiting_for = state.get("waiting_for")
    return {
        "kind": f"awaiting_{waiting_for}",
        "label": _waiting_label(waiting_for),
        "resume_behavior": "continue_read_only_diagnosis",
        "writes_allowed": False,
    }


def _resolve_waiting_identifier(
    waiting_for: str,
    message: str,
) -> tuple[str | None, str | None]:
    if waiting_for == "order_sn":
        resolution = extract_order_sn(message)
        if resolution.ambiguous:
            return None, "检测到多个可能的订单编号，请明确回复“订单号：xxxxxxxx”。"
        if not resolution.value:
            return None, _waiting_prompt("order_sn")
        return resolution.value, None
    if waiting_for == "sku_id":
        resolution = extract_sku_id(message)
        if resolution.ambiguous:
            return None, "检测到多个 SKU，请明确说明需要查询的一个 SKU 编码。"
        if not resolution.value:
            return None, _waiting_prompt("sku_id")
        return resolution.value, None
    return None, "请重新描述需要查询的信息。"


def _waiting_label(waiting_for: str | None) -> str:
    return "订单号" if waiting_for == "order_sn" else "SKU 编码"


def _waiting_prompt(waiting_for: str) -> str:
    if waiting_for == "order_sn":
        return "请提供订单号；收到后会在当前会话继续只读诊断，不会创建售后单、退款或修改订单。"
    return "请提供 SKU 编码；收到后会在当前会话继续只读诊断，不会创建售后单、退款或修改订单。"


def _owner_scope(member_id: int | None) -> str:
    if member_id is None:
        return "anonymous"
    if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
        raise DiagnosisCheckpointError("会员身份范围不合法。")
    return f"member:{member_id}"


def _graph_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _thread_id_from_config(config: dict[str, Any]) -> str:
    try:
        thread_id = config["configurable"]["thread_id"]
    except (KeyError, TypeError) as exc:
        raise DiagnosisCheckpointError("LangGraph checkpoint 缺少 thread_id。") from exc
    if not isinstance(thread_id, str) or not thread_id.startswith("diagnosis-thread-v1-"):
        raise DiagnosisCheckpointError("LangGraph checkpoint thread_id 不合法。")
    return thread_id


def _normalize_cancel_message(message: str) -> str:
    return message.strip().rstrip("。！？!?").replace(" ", "")


def _pack_typed(value: tuple[str, bytes]) -> dict[str, str]:
    tag, raw = value
    if not isinstance(tag, str) or not isinstance(raw, bytes):
        raise ValueError("invalid serialized checkpoint value")
    return {"tag": tag, "data": base64.b64encode(raw).decode("ascii")}


def _unpack_typed(value: Any) -> tuple[str, bytes]:
    if not isinstance(value, dict):
        raise ValueError("invalid serialized checkpoint value")
    tag = value.get("tag")
    encoded = value.get("data")
    if not isinstance(tag, str) or not isinstance(encoded, str):
        raise ValueError("invalid serialized checkpoint value")
    return tag, base64.b64decode(encoded.encode("ascii"), validate=True)


def _assert_safe_checkpoint_payload(value: Any, path: str = "root") -> None:
    """Fail closed if a future graph change tries to persist sensitive state."""
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized in _PROHIBITED_STATE_KEYS:
                raise DiagnosisCheckpointError(
                    f"诊断 checkpoint 包含禁止字段：{path}.{key}"
                )
            _assert_safe_checkpoint_payload(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple, deque, set)):
        for index, nested in enumerate(value):
            _assert_safe_checkpoint_payload(nested, f"{path}[{index}]")
        return
    if is_dataclass(value):
        _assert_safe_checkpoint_payload(asdict(value), path)
        return
    if hasattr(value, "model_dump") and callable(value.model_dump):
        _assert_safe_checkpoint_payload(value.model_dump(), path)
        return
    if isinstance(value, str) and "bearer " in value.lower():
        raise DiagnosisCheckpointError("诊断 checkpoint 包含禁止凭证内容。")


_manager: DurableDiagnosisManager | None = None
