import unittest
import time

from app.schemas.conversation import ConversationState
from app.schemas.task_orchestration import TaskSnapshot
from app.services.conversation_state import (
    ConversationManager,
    get_conversation_manager,
    get_conversation_state,
    record_assistant_message,
    record_user_message,
    set_conversation_manager_for_tests,
)
from app.services.conversation_store import (
    InMemoryConversationStore,
    RedisConversationStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.records.get(key)

    def set(self, key: str, value: str, ex: int) -> None:
        self.records[key] = value
        self.ttls[key] = ex

    def delete(self, key: str) -> None:
        self.records.pop(key, None)
        self.ttls.pop(key, None)


class ConversationStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryConversationStore()
        self.manager = ConversationManager(
            self.store,
            ttl_seconds=600,
            recent_message_limit=2,
            context_token_budget=1000,
            summarizer=lambda summary, messages: (
                f"{summary}|" + ",".join(message.content for message in messages)
            ).strip("|"),
        )
        set_conversation_manager_for_tests(self.manager)

    def tearDown(self) -> None:
        set_conversation_manager_for_tests(None)

    def test_compacts_old_messages_without_losing_structured_facts(self) -> None:
        record_user_message("session-a", "我要查询订单 202607240001")
        record_assistant_message("session-a", "请告诉我具体想查询什么。")
        record_user_message("session-a", "我要查物流。")

        state = get_conversation_state("session-a")

        self.assertLessEqual(len(state.recent_messages), 2)
        self.assertIn("我要查询订单", state.summary)
        self.assertEqual("202607240001", state.facts["order_sn"])

    def test_sessions_are_isolated(self) -> None:
        record_user_message("session-a", "订单号 202607240001")
        record_user_message("session-b", "订单号 202607240002")

        self.assertEqual(
            "202607240001",
            get_conversation_state("session-a").facts["order_sn"],
        )
        self.assertEqual(
            "202607240002",
            get_conversation_state("session-b").facts["order_sn"],
        )

    def test_redis_adapter_serializes_task_state_and_sets_ttl(self) -> None:
        fake_redis = FakeRedis()
        store = RedisConversationStore(
            "redis://unused",
            "mall-ai:conversation",
            redis_client=fake_redis,
        )
        state = ConversationState(
            session_id="session-a",
            facts={"order_sn": "202607240001"},
            active_task=_task_snapshot(),
        )

        store.save(state, ttl_seconds=600)
        loaded = store.load("session-a")

        self.assertEqual("202607240001", loaded.facts["order_sn"])
        self.assertEqual("order_diagnosis", loaded.active_task.kind)
        self.assertEqual(600, fake_redis.ttls["mall-ai:conversation:session-a"])

    def test_model_context_has_task_summary_but_not_raw_customer_history_or_ids(self) -> None:
        state = ConversationState(
            session_id="session-a",
            facts={"order_sn": "202607240001"},
            active_task=_task_snapshot(),
        )
        self.manager.save_state(state)
        record_user_message("session-a", "订单号 202607240001 一直没有到")
        record_assistant_message("session-a", "请补充必要信息。")

        context = get_conversation_manager().model_context("session-a")
        rendered = context.model_dump_json()

        self.assertEqual([], context.recent_messages)
        self.assertEqual("订单与物流异常诊断", context.active_task.goal_summary)
        self.assertNotIn("202607240001", rendered)
        self.assertNotIn("task_id", rendered)
        self.assertNotIn("owner_fingerprint", rendered)
        self.assertNotIn("一直没有到", rendered)


def _task_snapshot() -> TaskSnapshot:
    return TaskSnapshot(
        task_id="a" * 32,
        owner_fingerprint="b" * 64,
        session_fingerprint="c" * 64,
        kind="order_diagnosis",
        status="waiting_input",
        goal_summary="订单与物流异常诊断",
        known_slots={"awaiting_input": "订单号", "tool_kind": "logistics_service"},
        pending_question="还可继续：补充订单号后核验物流。",
        next_agent_hint="收到相关标识后继续只读核验。",
        expires_at=time.time() + 600,
    )


if __name__ == "__main__":
    unittest.main()
