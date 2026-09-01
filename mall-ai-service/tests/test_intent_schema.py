import unittest

from pydantic import ValidationError

from app.schemas.intent import IntentResponse
from app.services.intent_service import (
    INTENT_SYSTEM_PROMPT,
    INTENT_PROMPT_VERSION,
    IntentServiceError,
    detect_intent,
)


class IntentSchemaTests(unittest.TestCase):
    def test_accepts_bounded_general_chat_scope(self) -> None:
        intent = IntentResponse.model_validate(
            {
                "intent": "general_chat",
                "route": "chat",
                "need_tool": False,
                "chat_scope": "out_of_scope",
            }
        )

        self.assertEqual("out_of_scope", intent.chat_scope)

    def test_rejects_general_chat_without_scope(self) -> None:
        with self.assertRaises(ValidationError):
            IntentResponse.model_validate(
                {
                    "intent": "general_chat",
                    "route": "chat",
                    "need_tool": False,
                }
            )

    def test_accepts_valid_logistics_tool_call(self) -> None:
        intent = IntentResponse.model_validate(
            {
                "intent": "query_logistics",
                "route": "tool_calling",
                "need_tool": True,
                "tool_call": {
                    "name": "logistics_service",
                    "arguments": {"order_sn": "202607240001"},
                },
            }
        )

        self.assertEqual("logistics_service", intent.tool_call.name)

    def test_complex_delivery_diagnosis_contract_uses_agent_not_one_shot_query(self) -> None:
        """Regression contract for the Build 21 durable diagnosis entry.

        This is an offline contract, not a claim that every live model answer
        will be perfect.  It preserves the route/Tool schema boundary and the
        semantic prompt rule that makes the durable interrupt reachable.
        """
        intent = IntentResponse.model_validate(
            {
                "intent": "query_logistics",
                "route": "agent",
                "need_tool": True,
                "tool_call": {"name": "analysis_agent", "arguments": {}},
            }
        )

        self.assertEqual("agent", intent.route)
        self.assertIn("订单为什么未按预期完成", INTENT_SYSTEM_PROMPT)

    def test_rejects_invented_tool_name(self) -> None:
        with self.assertRaises(ValidationError):
            IntentResponse.model_validate(
                {
                    "intent": "query_logistics",
                    "route": "tool_calling",
                    "need_tool": True,
                    "tool_call": {
                        "name": "delete_all_orders",
                        "arguments": {},
                    },
                }
            )

    def test_rejects_rag_route_with_tool_call(self) -> None:
        with self.assertRaises(ValidationError):
            IntentResponse.model_validate(
                {
                    "intent": "after_sales_policy",
                    "route": "rag",
                    "need_tool": False,
                    "tool_call": {
                        "name": "order_service",
                        "arguments": {},
                    },
                }
            )

    def test_accepts_missing_information_without_executing_tool(self) -> None:
        intent = IntentResponse.model_validate(
            {
                "intent": "query_order_status",
                "route": "ask_missing_info",
                "need_tool": False,
                "tool_call": {
                    "name": "order_service",
                    "arguments": {},
                },
            }
        )

        self.assertEqual("order_service", intent.tool_call.name)

    def test_accepts_unified_after_sales_flow_without_direct_tool_call(self) -> None:
        intent = IntentResponse.model_validate(
            {
                "intent": "apply_after_sales",
                "route": "after_sales_flow",
                "need_tool": False,
                "tool_call": None,
            }
        )

        self.assertEqual("after_sales_flow", intent.route)

    def test_rejects_unified_after_sales_flow_with_direct_tool_call(self) -> None:
        with self.assertRaises(ValidationError):
            IntentResponse.model_validate(
                {
                    "intent": "apply_after_sales",
                    "route": "after_sales_flow",
                    "need_tool": True,
                    "tool_call": {
                        "name": "order_service",
                        "arguments": {"order_sn": "202607240001"},
                    },
                }
            )

    def test_converts_invalid_model_output_to_safe_intent_error(self) -> None:
        from unittest.mock import patch

        with patch(
            "app.services.intent_service.generate_json",
            return_value={
                "intent": "query_logistics",
                "route": "tool_calling",
                "need_tool": True,
                "tool_call": {"name": "made_up_tool", "arguments": {}},
            },
        ):
            with self.assertRaises(IntentServiceError):
                detect_intent("查物流")

    def test_model_availability_error_does_not_blame_the_customer(self) -> None:
        from unittest.mock import patch

        from app.services.llm_service import LLMServiceError

        with patch(
            "app.services.intent_service.generate_json",
            side_effect=LLMServiceError("TLS connection interrupted"),
        ):
            with self.assertRaisesRegex(IntentServiceError, "智能客服服务暂时不可用"):
                detect_intent("商品质量问题退货，运费由谁承担？")

    def test_invalid_non_object_model_output_becomes_safe_intent_error(self) -> None:
        from unittest.mock import patch

        with patch("app.services.intent_service.generate_json", return_value=[]):
            with self.assertRaisesRegex(IntentServiceError, "智能客服服务暂时不可用"):
                detect_intent("申请退货")

    def test_intent_uses_one_schema_correction_before_safe_routing(self) -> None:
        from unittest.mock import patch

        responses = [
            {
                "intent": "apply_after_sales",
                "route": "after_sales_flow",
                "need_tool": "false",
            },
            {
                "intent": "apply_after_sales",
                "route": "after_sales_flow",
                "need_tool": False,
                "tool_call": None,
            },
        ]
        with patch(
            "app.services.intent_service.generate_json",
            side_effect=responses,
        ) as generate_json:
            intent = detect_intent("我想申请退货")

        self.assertEqual("apply_after_sales", intent.intent)
        self.assertEqual("after_sales_flow", intent.route)
        self.assertEqual(2, generate_json.call_count)
        self.assertIn('"validationErrors":["schema_invalid"]', generate_json.call_args_list[1].kwargs["message"])

    def test_all_after_sales_actions_are_closed_to_the_unified_flow(self) -> None:
        actions = (
            "after_sales_policy",
            "after_sales_eligibility",
            "apply_after_sales",
            "list_after_sales",
            "status_after_sales",
            "cancel_after_sales",
            "modify_after_sales",
            "follow_up_after_sales",
        )
        for action in actions:
            with self.subTest(action=action):
                intent = IntentResponse.model_validate(
                    {
                        "intent": action,
                        "route": "after_sales_flow",
                        "need_tool": False,
                        "tool_call": None,
                    }
                )
                self.assertEqual("after_sales_flow", intent.route)

    def test_intent_prompt_has_auditable_semantic_version(self) -> None:
        from unittest.mock import patch

        response = {
            "intent": "after_sales_policy",
            "route": "after_sales_flow",
            "need_tool": False,
            "tool_call": None,
        }
        with patch("app.services.intent_service.generate_json", return_value=response) as generate_json:
            detect_intent("质量问题退货运费谁承担？")

        system_prompt = generate_json.call_args.kwargs["system_prompt"]
        self.assertIn(f"intent_prompt_version={INTENT_PROMPT_VERSION}", system_prompt)

    def test_rejects_after_sales_intent_outside_unified_flow(self) -> None:
        with self.assertRaises(ValidationError):
            IntentResponse.model_validate(
                {
                    "intent": "after_sales_policy",
                    "route": "rag",
                    "need_tool": False,
                }
            )


if __name__ == "__main__":
    unittest.main()
