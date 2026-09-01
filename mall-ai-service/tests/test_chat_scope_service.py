import unittest
from unittest.mock import patch

from app.schemas.customer_service import CustomerServiceRequest, CustomerServiceResponse
from app.schemas.intent import IntentResponse
from app.services.conversation_state import reset_conversation_state_for_tests
from app.services.customer_service import handle_customer_message
from app.services.durable_diagnosis import (
    DurableDiagnosisManager,
    SanitizedMemorySaver,
    set_durable_diagnosis_manager_for_tests,
)
from app.services.intent_service import IntentServiceError
from app.services.tool_context import ToolExecutionContext


class ChatScopeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_conversation_state_for_tests()
        set_durable_diagnosis_manager_for_tests(
            DurableDiagnosisManager(SanitizedMemorySaver(), ttl_seconds=600)
        )

    def tearDown(self) -> None:
        set_durable_diagnosis_manager_for_tests(None)

    def test_out_of_scope_chat_uses_reviewed_template_without_second_llm_call(self) -> None:
        with (
            patch(
                "app.services.customer_service.detect_intent",
                return_value=IntentResponse(
                    intent="general_chat",
                    route="chat",
                    need_tool=False,
                    chat_scope="out_of_scope",
                ),
            ),
            patch("app.services.chat_service.generate_text") as free_form_generate,
        ):
            response = handle_customer_message(
                CustomerServiceRequest(
                    session_id="scope-test",
                    message="帮我写 Python",
                ),
                ToolExecutionContext(),
            )

        self.assertIn("商城订单、物流、退换货和售后政策", response.answer)
        free_form_generate.assert_not_called()

    def test_internal_chat_scope_is_not_present_in_public_projection(self) -> None:
        from app.schemas.customer_service import to_public_customer_service_response

        internal = IntentResponse(
            intent="general_chat",
            route="chat",
            need_tool=False,
            chat_scope="capability",
        )
        response = CustomerServiceResponse(
            message="你好",
            answer="您好，我可以协助商城售后问题。",
            intent=internal,
        )
        public = to_public_customer_service_response(response)
        self.assertNotIn("chat_scope", public.model_dump())
        self.assertNotIn("intent", public.model_dump())

    def test_unavailable_intent_model_returns_controlled_service_reply(self) -> None:
        with (
            patch(
                "app.services.customer_service.detect_intent",
                side_effect=IntentServiceError("智能客服服务暂时不可用，请稍后再试。"),
            ),
        ):
            response = handle_customer_message(
                CustomerServiceRequest(
                    session_id="scope-model-down",
                    message="量子力学是什么？",
                ),
                ToolExecutionContext(),
            )

        self.assertEqual("智能客服暂不可用，请稍后重试或联系人工客服。", response.answer)


if __name__ == "__main__":
    unittest.main()
