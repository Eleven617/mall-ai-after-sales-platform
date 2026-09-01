import unittest

from app.schemas.conversation import ConversationState
from app.schemas.tool import ToolCall
from app.services.conversation_state import (
    ConversationManager,
    get_conversation_manager,
    get_conversation_state,
    pop_pending_tool_call,
    record_assistant_message,
    record_user_message,
    resolve_pending_tool_call,
    save_pending_tool_call,
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

    def test_fills_order_sn_after_missing_information_prompt(self) -> None:
        save_pending_tool_call(
            "session-a",
            ToolCall(name="order_service", arguments={}),
        )

        tool_call = pop_pending_tool_call("session-a", "订单号是 202607240001")

        self.assertIsNotNone(tool_call)
        self.assertEqual("order_service", tool_call.name)
        self.assertEqual("202607240001", tool_call.arguments["order_sn"])
        state = get_conversation_state("session-a")
        self.assertIsNone(state.pending_tool_call)
        self.assertEqual("202607240001", state.facts["order_sn"])

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

    def test_redis_adapter_serializes_state_and_sets_ttl(self) -> None:
        fake_redis = FakeRedis()
        store = RedisConversationStore(
            "redis://unused",
            "mall-ai:conversation",
            redis_client=fake_redis,
        )
        state = ConversationState(session_id="session-a", facts={"order_sn": "202607240001"})

        store.save(state, ttl_seconds=600)
        loaded = store.load("session-a")

        self.assertEqual("202607240001", loaded.facts["order_sn"])
        self.assertEqual(600, fake_redis.ttls["mall-ai:conversation:session-a"])

    def test_labeled_order_number_wins_over_phone_number(self) -> None:
        save_pending_tool_call(
            "session-a",
            ToolCall(name="logistics_service", arguments={}),
        )

        resolution = resolve_pending_tool_call(
            "session-a",
            "我的手机号是 13812345678，订单号：202607240001",
        )

        self.assertIsNotNone(resolution.tool_call)
        self.assertEqual(
            "202607240001",
            resolution.tool_call.arguments["order_sn"],
        )

    def test_multiple_unlabeled_order_numbers_require_clarification(self) -> None:
        save_pending_tool_call(
            "session-a",
            ToolCall(name="logistics_service", arguments={}),
        )

        resolution = resolve_pending_tool_call(
            "session-a",
            "202607240001 或者 202607240002 都有问题",
        )

        self.assertTrue(resolution.has_pending)
        self.assertIsNotNone(resolution.tool_call)
        self.assertEqual("logistics_service", resolution.tool_call.name)
        self.assertEqual({}, resolution.tool_call.arguments)
        self.assertIn("多个", resolution.clarification)
        self.assertIsNotNone(get_conversation_state("session-a").pending_tool_call)


if __name__ == "__main__":
    unittest.main()
