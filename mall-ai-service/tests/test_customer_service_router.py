import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.agent import VerifiedFactCard, VerifiedFactField
from app.schemas.authentication import MemberProfile
from app.schemas.conversation_history import (
    ConversationHistoryDetail,
    ConversationHistoryMessage,
    ConversationHistorySummary,
)
from app.schemas.customer_service import CustomerServiceResponse
from app.schemas.diagnosis import DiagnosisHandoff, DiagnosisPolicySource, DiagnosisResult
from app.schemas.intent import IntentResponse
from app.schemas.rag import RagSource
from app.services.conversation_history_client import (
    ConversationHistoryError,
    _history_message,
)
from app.services.conversation_state import (
    get_conversation_state,
    reset_conversation_state_for_tests,
)


CONVERSATION_A = "11111111-1111-4111-8111-111111111111"
CONVERSATION_B = "22222222-2222-4222-8222-222222222222"


class CustomerServiceRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_conversation_state_for_tests()

    def test_forwards_bearer_token_and_persists_only_public_exchange(self) -> None:
        with (
            patch("app.routers.customer_service.get_current_member") as get_current_member,
            patch("app.routers.customer_service.get_customer_conversation") as get_conversation,
            patch("app.routers.customer_service.handle_customer_message") as handle_message,
            patch("app.routers.customer_service.append_customer_conversation_exchange") as append_exchange,
        ):
            get_current_member.return_value = MemberProfile(member_id=1, username="test")
            get_conversation.return_value = history(CONVERSATION_A)
            handle_message.return_value = internal_response()

            response = TestClient(app).post(
                "/customer-service",
                headers={"Authorization": "Bearer user-token"},
                json={"session_id": CONVERSATION_A, "message": "查订单 202607240001"},
            )

        self.assertEqual(200, response.status_code)
        context = handle_message.call_args.args[1]
        self.assertEqual("Bearer user-token", context.authorization)
        self.assertEqual(1, context.member_id)
        self.assertNotEqual(CONVERSATION_A, handle_message.call_args.args[0].session_id)
        append_kwargs = append_exchange.call_args.kwargs
        self.assertEqual(CONVERSATION_A, append_kwargs["conversation_id"])
        self.assertEqual("订单与物流咨询", append_kwargs["title"])
        persisted_public = append_kwargs["public_response"].model_dump()
        self.assertNotIn("intent", persisted_public)
        self.assertNotIn("tool_result", persisted_public)
        self.assertNotIn("rag_context", persisted_public)
        self.assertEqual("订单查询完成。", append_kwargs["assistant_message"])

    def test_same_public_conversation_is_scoped_to_verified_member(self) -> None:
        with (
            patch("app.routers.customer_service.get_current_member") as get_current_member,
            patch("app.routers.customer_service.get_customer_conversation") as get_conversation,
            patch("app.routers.customer_service.handle_customer_message") as handle_message,
            patch("app.routers.customer_service.append_customer_conversation_exchange"),
        ):
            handle_message.return_value = internal_response()
            get_conversation.return_value = history(CONVERSATION_A)
            request = {"session_id": CONVERSATION_A, "message": "你好"}

            get_current_member.return_value = MemberProfile(member_id=1, username="test")
            TestClient(app).post(
                "/customer-service", headers={"Authorization": "Bearer user-a"}, json=request
            )
            first_state_key = handle_message.call_args.args[0].session_id

            get_current_member.return_value = MemberProfile(member_id=3, username="windy")
            TestClient(app).post(
                "/customer-service", headers={"Authorization": "Bearer user-b"}, json=request
            )
            second_state_key = handle_message.call_args.args[0].session_id

        self.assertNotEqual(first_state_key, second_state_key)
        self.assertNotEqual(CONVERSATION_A, first_state_key)

    def test_restores_only_safe_transcript_context_when_short_term_cache_is_empty(self) -> None:
        transcript = history(
            CONVERSATION_A,
            messages=[
                history_message("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "user", "我想查物流"),
                history_message("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "assistant", "请提供订单号"),
            ],
        )
        with (
            patch("app.routers.customer_service.get_current_member") as get_current_member,
            patch("app.routers.customer_service.get_customer_conversation", return_value=transcript),
            patch("app.routers.customer_service.handle_customer_message") as handle_message,
            patch("app.routers.customer_service.append_customer_conversation_exchange"),
        ):
            get_current_member.return_value = MemberProfile(member_id=1, username="test")
            handle_message.return_value = internal_response()
            response = TestClient(app).post(
                "/customer-service",
                headers={"Authorization": "Bearer user-token"},
                json={"session_id": CONVERSATION_A, "message": "订单号 202607240001"},
            )

        self.assertEqual(200, response.status_code)
        state = get_conversation_state(handle_message.call_args.args[0].session_id)
        self.assertEqual(["我想查物流", "请提供订单号"], [item.content for item in state.recent_messages])
        self.assertIsNone(state.pending_after_sales_draft)
        self.assertIsNone(state.pending_after_sales_proposal)

    def test_rejects_foreign_or_missing_history_before_agent_execution(self) -> None:
        with (
            patch("app.routers.customer_service.get_current_member") as get_current_member,
            patch(
                "app.routers.customer_service.get_customer_conversation",
                side_effect=ConversationHistoryError("无权访问", status_code=403),
            ),
            patch("app.routers.customer_service.handle_customer_message") as handle_message,
        ):
            get_current_member.return_value = MemberProfile(member_id=3, username="windy")
            response = TestClient(app).post(
                "/customer-service",
                headers={"Authorization": "Bearer user-b"},
                json={"session_id": CONVERSATION_A, "message": "查订单"},
            )

        self.assertEqual(403, response.status_code)
        handle_message.assert_not_called()

    def test_history_append_failure_does_not_rewrite_a_completed_customer_reply(self) -> None:
        with (
            patch("app.routers.customer_service.get_current_member") as get_current_member,
            patch("app.routers.customer_service.get_customer_conversation", return_value=history(CONVERSATION_A)),
            patch("app.routers.customer_service.handle_customer_message", return_value=internal_response()),
            patch(
                "app.routers.customer_service.append_customer_conversation_exchange",
                side_effect=ConversationHistoryError("temporarily unavailable", status_code=503),
            ),
        ):
            get_current_member.return_value = MemberProfile(member_id=1, username="test")
            response = TestClient(app).post(
                "/customer-service",
                headers={"Authorization": "Bearer user-token"},
                json={"session_id": CONVERSATION_A, "message": "查询订单"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("订单查询完成。", response.json()["answer"])

    def test_serializes_only_customer_safe_response_fields(self) -> None:
        with patch("app.routers.customer_service.handle_customer_message") as handle_message:
            handle_message.return_value = detailed_internal_response()
            response = TestClient(app).post(
                "/customer-service",
                json={"session_id": "anonymous-session", "message": "查物流"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("订单正在运输中。", payload["answer"])
        self.assertEqual("delivery_in_transit", payload["diagnosis"]["category"])
        for internal_field in (
            "message",
            "intent",
            "tool_result",
            "rag_context",
            "rag_sources",
            "policy_sources",
        ):
            self.assertNotIn(internal_field, payload)
        self.assertNotIn("verified_source_types", payload["diagnosis"])
        self.assertNotIn("policy_sources", payload["diagnosis"])
        self.assertNotIn("verified_facts", payload["diagnosis"])
        self.assertNotIn("chunk_id", response.text)
        self.assertNotIn("distance", response.text)
        self.assertNotIn("internal_order_id", response.text)

    def test_member_history_routes_validate_identity_and_forward_owner_token(self) -> None:
        with (
            patch("app.routers.customer_service.get_current_member") as get_current_member,
            patch("app.routers.customer_service.create_customer_conversation") as create_conversation,
            patch("app.routers.customer_service.list_customer_conversations") as list_conversations,
            patch("app.routers.customer_service.get_customer_conversation") as get_conversation,
            patch("app.routers.customer_service.delete_customer_conversation") as delete_conversation,
            patch("app.routers.customer_service.clear_durable_diagnosis"),
            patch("app.routers.customer_service.feedback_governance_store.delete_session_data") as delete_feedback,
        ):
            get_current_member.return_value = MemberProfile(member_id=1, username="test")
            create_conversation.return_value = history(CONVERSATION_A).conversation
            list_conversations.return_value = [history(CONVERSATION_A).conversation]
            get_conversation.return_value = history(CONVERSATION_A)

            created = TestClient(app).post(
                f"/customer-service/conversations/{CONVERSATION_A}",
                headers={"Authorization": "Bearer user-token"},
            )
            listed = TestClient(app).get(
                "/customer-service/conversations", headers={"Authorization": "Bearer user-token"}
            )
            opened = TestClient(app).get(
                f"/customer-service/conversations/{CONVERSATION_A}",
                headers={"Authorization": "Bearer user-token"},
            )
            deleted = TestClient(app).delete(
                f"/customer-service/conversations/{CONVERSATION_A}",
                headers={"Authorization": "Bearer user-token"},
            )

        self.assertEqual(200, created.status_code)
        self.assertEqual(200, listed.status_code)
        self.assertEqual(200, opened.status_code)
        self.assertEqual(204, deleted.status_code)
        create_conversation.assert_called_once_with(CONVERSATION_A, "Bearer user-token")
        list_conversations.assert_called_once_with("Bearer user-token")
        get_conversation.assert_called_with(CONVERSATION_A, "Bearer user-token")
        delete_conversation.assert_called_once_with(CONVERSATION_A, "Bearer user-token")
        delete_feedback.assert_called_once_with(
            member_id=1,
            session_id=delete_feedback.call_args.kwargs["session_id"],
        )
        self.assertNotEqual(CONVERSATION_A, delete_feedback.call_args.kwargs["session_id"])

    def test_history_client_discards_java_only_association_fields(self) -> None:
        message = _history_message(
            {
                "messageId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "conversationId": CONVERSATION_A,
                "sequenceNo": 2,
                "role": "assistant",
                "content": "请提供订单号。",
                "publicResponseJson": '{"answer":"请提供订单号。"}',
                "createdAt": "2026-08-19T12:00:00",
            }
        )

        self.assertEqual("assistant", message.role)
        self.assertEqual("请提供订单号。", message.public_response.answer)
        self.assertFalse(hasattr(message, "conversation_id"))


def history(
    conversation_id: str,
    messages: list[ConversationHistoryMessage] | None = None,
) -> ConversationHistoryDetail:
    summary = ConversationHistorySummary(
        conversation_id=conversation_id,
        title="订单与物流咨询",
        message_count=len(messages or []),
    )
    return ConversationHistoryDetail(conversation=summary, messages=messages or [])


def history_message(message_id: str, role: str, content: str) -> ConversationHistoryMessage:
    return ConversationHistoryMessage(message_id=message_id, role=role, content=content)


def internal_response() -> CustomerServiceResponse:
    return CustomerServiceResponse(
        message="查订单 202607240001",
        answer="订单查询完成。",
        intent=IntentResponse(
            intent="query_order_status",
            route="tool_calling",
            need_tool=True,
            tool_call={"name": "order_service", "arguments": {"order_sn": "202607240001"}},
        ),
        tool_result={"internal_order_id": 991},
        rag_context=["内部检索文本"],
        verified_facts=[
            VerifiedFactCard(
                source="order_service",
                title="订单信息（商城系统）",
                fields=[VerifiedFactField(label="订单状态", value="已发货")],
            )
        ],
    )


def detailed_internal_response() -> CustomerServiceResponse:
    return CustomerServiceResponse(
        message="查询订单 202607240001 的物流",
        answer="订单正在运输中。",
        intent=IntentResponse(
            intent="query_logistics",
            route="tool_calling",
            need_tool=True,
            tool_call={"name": "logistics_service", "arguments": {"order_sn": "202607240001"}},
        ),
        tool_result={"internal_order_id": 991, "tracking_no": "TEST-001"},
        rag_context=["原始检索文本不应发送到浏览器。"],
        rag_sources=[
            RagSource(
                chunk_id="policy-transport-001",
                document_name="售后政策知识库",
                section_path="售后政策知识库 > 退货运费",
                distance=0.18,
            )
        ],
        verified_facts=[
            VerifiedFactCard(
                source="logistics_service",
                title="物流信息（商城系统）",
                fields=[VerifiedFactField(label="物流状态", value="运输中")],
            )
        ],
        diagnosis=DiagnosisResult(
            category="delivery_in_transit",
            evidence_status="complete",
            verified_facts=[
                VerifiedFactCard(
                    source="logistics_service",
                    title="内部重复事实卡",
                    fields=[VerifiedFactField(label="物流状态", value="运输中")],
                )
            ],
            policy_sources=[
                DiagnosisPolicySource(
                    document_name="售后政策知识库",
                    section_path="售后政策知识库 > 退货运费",
                )
            ],
            allowed_next_steps=["continue_after_sales", "contact_human"],
            handoff=DiagnosisHandoff(
                reason="manual_review",
                summary="请联系人工客服继续处理。",
                verified_source_types=["logistics_service"],
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
