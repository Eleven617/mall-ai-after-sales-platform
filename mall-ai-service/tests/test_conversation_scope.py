import unittest

from app.services.conversation_scope import build_conversation_state_key


class ConversationScopeTests(unittest.TestCase):
    def test_same_member_and_chat_id_are_resumable(self) -> None:
        first = build_conversation_state_key("chat-1", 1)
        second = build_conversation_state_key("chat-1", 1)
        self.assertEqual(first, second)

    def test_same_browser_chat_id_cannot_share_two_members_state(self) -> None:
        member_a = build_conversation_state_key("shared", 1)
        member_b = build_conversation_state_key("shared", 3)
        self.assertNotEqual(member_a, member_b)

    def test_anonymous_state_is_separate_from_member_state(self) -> None:
        self.assertNotEqual(
            build_conversation_state_key("chat-1", None),
            build_conversation_state_key("chat-1", 1),
        )


if __name__ == "__main__":
    unittest.main()
