import base64
import json
import unittest

from app.schemas.tool import ToolCall
from app.services.durable_diagnosis import (
    DurableDiagnosisManager,
    RedisSanitizedCheckpointer,
    SanitizedMemorySaver,
    build_diagnosis_thread_id,
)
from app.services.tool_context import ToolExecutionContext


class FakeRedis:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def get(self, key: str) -> str | None:
        if self.fail:
            raise RuntimeError("redis unavailable")
        return self.records.get(key)

    def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        if self.fail:
            raise RuntimeError("redis unavailable")
        if nx and key in self.records:
            return False
        self.records[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, key: str) -> int:
        if self.fail:
            raise RuntimeError("redis unavailable")
        existed = key in self.records
        self.records.pop(key, None)
        self.ttls.pop(key, None)
        return int(existed)


class DurableDiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = [1000.0]
        self.redis = FakeRedis()

    def _manager(self, saver) -> DurableDiagnosisManager:
        return DurableDiagnosisManager(
            saver,
            ttl_seconds=120,
            lock_seconds=20,
            now=lambda: self.now[0],
        )

    def _redis_saver(self) -> RedisSanitizedCheckpointer:
        return RedisSanitizedCheckpointer(
            "redis://unused",
            "test:durable-diagnosis",
            120,
            redis_client=self.redis,
        )

    def test_redis_checkpoint_survives_new_manager_and_never_persists_resume_input(self) -> None:
        session_id = "conversation-v1-safe-session"
        member_id = 17
        first_manager = self._manager(self._redis_saver())

        started = first_manager.begin(
            session_id=session_id,
            member_id=member_id,
            pending_tool_call=ToolCall(name="logistics_service", arguments={}),
        )

        self.assertTrue(started.pending)
        thread_id = build_diagnosis_thread_id(session_id, member_id)
        self.assertEqual(120, self.redis.ttls[f"test:durable-diagnosis:{thread_id}"])

        calls: list[ToolCall] = []
        second_manager = self._manager(self._redis_saver())
        resumed = second_manager.resume_or_inspect(
            session_id=session_id,
            member_id=member_id,
            message="订单号是 202607240001",
            tool_context=ToolExecutionContext(
                authorization="Bearer synthetic-customer-token",
                member_id=member_id,
            ),
            call_tool_fn=lambda call, _context: calls.append(call)
            or {
                "order_sn": call.arguments["order_sn"],
                "order_status": "运输中",
            },
        )

        self.assertEqual("resumed", resumed.status)
        self.assertEqual(1, len(calls))
        self.assertEqual("202607240001", calls[0].arguments["order_sn"])
        self.assertNotIn("202607240001", _decoded_checkpoint_text(self.redis, thread_id))
        self.assertNotIn("synthetic-customer-token", _decoded_checkpoint_text(self.redis, thread_id))
        self.assertNotIn("Bearer", _decoded_checkpoint_text(self.redis, thread_id))

    def test_wrong_owner_cannot_resume_another_members_checkpoint(self) -> None:
        manager = self._manager(SanitizedMemorySaver())
        manager.begin(
            session_id="same-public-conversation",
            member_id=31,
            pending_tool_call=ToolCall(name="order_service", arguments={}),
        )
        calls: list[ToolCall] = []

        result = manager.resume_or_inspect(
            session_id="same-public-conversation",
            member_id=32,
            message="订单号 202607240001",
            tool_context=ToolExecutionContext(authorization="Bearer other", member_id=32),
            call_tool_fn=lambda call, _context: calls.append(call) or {},
        )

        self.assertIsNone(result)
        self.assertEqual([], calls)

    def test_expired_and_cancelled_checkpoints_never_execute_tools(self) -> None:
        manager = self._manager(SanitizedMemorySaver())
        manager.begin(
            session_id="expire-me",
            member_id=1,
            pending_tool_call=ToolCall(name="order_service", arguments={}),
        )
        self.now[0] += 121
        calls: list[ToolCall] = []
        expired = manager.resume_or_inspect(
            session_id="expire-me",
            member_id=1,
            message="订单号 202607240001",
            tool_context=ToolExecutionContext(authorization="Bearer test", member_id=1),
            call_tool_fn=lambda call, _context: calls.append(call) or {},
        )
        self.assertEqual("expired", expired.status)
        self.assertEqual([], calls)

        manager.begin(
            session_id="cancel-me",
            member_id=1,
            pending_tool_call=ToolCall(name="inventory_service", arguments={}),
        )
        cancelled = manager.resume_or_inspect(
            session_id="cancel-me",
            member_id=1,
            message="取消查询",
            tool_context=ToolExecutionContext(authorization="Bearer test", member_id=1),
            call_tool_fn=lambda call, _context: calls.append(call) or {},
        )
        self.assertEqual("cancelled", cancelled.status)
        self.assertEqual([], calls)

    def test_ambiguous_identifier_remains_interrupted_without_tool_execution(self) -> None:
        manager = self._manager(SanitizedMemorySaver())
        manager.begin(
            session_id="ambiguous",
            member_id=1,
            pending_tool_call=ToolCall(name="logistics_service", arguments={}),
        )
        calls: list[ToolCall] = []

        result = manager.resume_or_inspect(
            session_id="ambiguous",
            member_id=1,
            message="202607240001 或 202607240002",
            tool_context=ToolExecutionContext(authorization="Bearer test", member_id=1),
            call_tool_fn=lambda call, _context: calls.append(call) or {},
        )

        self.assertEqual("awaiting_input", result.status)
        self.assertIn("多个", result.answer)
        self.assertEqual([], calls)

    def test_duplicate_resume_is_explainable_and_does_not_repeat_read(self) -> None:
        manager = self._manager(SanitizedMemorySaver())
        manager.begin(
            session_id="duplicate",
            member_id=1,
            pending_tool_call=ToolCall(name="inventory_service", arguments={}),
        )
        calls: list[ToolCall] = []
        context = ToolExecutionContext(authorization="Bearer test", member_id=1)
        first = manager.resume_or_inspect(
            session_id="duplicate",
            member_id=1,
            message="SKU10001",
            tool_context=context,
            call_tool_fn=lambda call, _context: calls.append(call) or {"sku_id": "SKU10001"},
        )
        second = manager.resume_or_inspect(
            session_id="duplicate",
            member_id=1,
            message="SKU10001",
            tool_context=context,
            call_tool_fn=lambda call, _context: calls.append(call) or {"sku_id": "SKU10001"},
        )

        self.assertEqual("resumed", first.status)
        self.assertEqual("completed", second.status)
        self.assertEqual(1, len(calls))

    def test_incompatible_version_is_deleted_and_never_resumed(self) -> None:
        saver = SanitizedMemorySaver()
        manager = self._manager(saver)
        session_id = "old-version"
        member_id = 1
        manager.begin(
            session_id=session_id,
            member_id=member_id,
            pending_tool_call=ToolCall(name="order_service", arguments={}),
        )
        thread_id = build_diagnosis_thread_id(session_id, member_id)
        checkpoint = saver.get({"configurable": {"thread_id": thread_id}})
        version = checkpoint["channel_versions"]["schema_version"]
        saver.blobs[(thread_id, "", "schema_version", version)] = saver.serde.dumps_typed(
            "diagnosis-resume-v0"
        )
        calls: list[ToolCall] = []

        result = manager.resume_or_inspect(
            session_id=session_id,
            member_id=member_id,
            message="订单号 202607240001",
            tool_context=ToolExecutionContext(authorization="Bearer test", member_id=1),
            call_tool_fn=lambda call, _context: calls.append(call) or {},
        )

        self.assertEqual("incompatible", result.status)
        self.assertEqual([], calls)
        self.assertIsNone(saver.get({"configurable": {"thread_id": thread_id}}))

    def test_concurrent_resume_lock_returns_busy_without_an_extra_tool_read(self) -> None:
        saver = SanitizedMemorySaver()
        manager = self._manager(saver)
        session_id = "locked"
        member_id = 1
        manager.begin(
            session_id=session_id,
            member_id=member_id,
            pending_tool_call=ToolCall(name="order_service", arguments={}),
        )
        thread_id = build_diagnosis_thread_id(session_id, member_id)
        lock = saver.acquire_resume_lock(thread_id, 20)
        calls: list[ToolCall] = []
        try:
            result = manager.resume_or_inspect(
                session_id=session_id,
                member_id=member_id,
                message="订单号 202607240001",
                tool_context=ToolExecutionContext(authorization="Bearer test", member_id=1),
                call_tool_fn=lambda call, _context: calls.append(call) or {},
            )
        finally:
            saver.release_resume_lock(thread_id, lock)

        self.assertEqual("busy", result.status)
        self.assertEqual([], calls)

    def test_redis_failure_fails_closed_before_a_new_pending_state_is_created(self) -> None:
        self.redis.fail = True
        manager = self._manager(self._redis_saver())

        result = manager.begin(
            session_id="redis-down",
            member_id=1,
            pending_tool_call=ToolCall(name="order_service", arguments={}),
        )

        self.assertFalse(result.pending)
        self.assertEqual("unavailable", result.status)


def _decoded_checkpoint_text(redis: FakeRedis, thread_id: str) -> str:
    raw = redis.records[f"test:durable-diagnosis:{thread_id}"]
    payload = json.loads(raw)
    decoded: list[str] = [raw]

    def visit(value):
        if isinstance(value, dict):
            if set(value) == {"tag", "data"}:
                try:
                    decoded.append(base64.b64decode(value["data"]).decode("utf-8", errors="ignore"))
                except (TypeError, ValueError):
                    pass
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return "\n".join(decoded)


if __name__ == "__main__":
    unittest.main()
