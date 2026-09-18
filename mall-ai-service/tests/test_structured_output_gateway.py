import unittest
from typing import Literal
from unittest.mock import patch

from pydantic import BaseModel

from app.services.llm_service import LLMServiceError, _extract_json_object, generate_json
from app.services.structured_output_gateway import (
    StructuredOutputError,
    StructuredOutputMode,
    generate_structured_output,
)


class _ToolDecision(BaseModel):
    name: Literal["order_service", "logistics_service"]
    order_sn: str


class _DecisionContract(BaseModel):
    intent: Literal["query_order_status", "query_logistics"]
    need_tool: bool
    tool: _ToolDecision


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class StructuredOutputGatewayTests(unittest.TestCase):
    def test_executor_decision_accepts_only_declared_camel_case_wire_aliases(self) -> None:
        from app.schemas.agent_task import ExecutorDecision

        decision = ExecutorDecision.model_validate(
            {
                "decision": "propose_action",
                "reasonSummary": "基于已核验事实形成待确认草案。",
                "actionSkill": "create_after_sales_draft",
                "actionArguments": {"orderFactRef": "fact-order-abcdefgh"},
            },
            strict=True,
            extra="forbid",
        )

        self.assertEqual("propose_action", decision.decision)
        self.assertEqual("create_after_sales_draft", decision.action_skill)
        with self.assertRaises(Exception):
            ExecutorDecision.model_validate(
                {
                    "decision": "finish",
                    "reasonSummary": "完成。",
                    "untrustedExtra": True,
                },
                strict=True,
                extra="forbid",
            )

    def test_json_object_parser_accepts_one_bounded_presentation_prefix(self) -> None:
        parsed = _extract_json_object(
            {"choices": [{"message": {"content": 'JSON: {"ok": true}'}}]}
        )
        self.assertEqual({"ok": True}, parsed)
        with self.assertRaises(LLMServiceError):
            _extract_json_object(
                {"choices": [{"message": {"content": "x" * 241 + ' {"ok": true}'}}]}
            )

    def test_gateway_appends_schema_and_returns_strictly_valid_model(self) -> None:
        captured: dict = {}

        def fake_json_generator(**kwargs):
            captured.update(kwargs)
            return {
                "intent": "query_logistics",
                "need_tool": True,
                "tool": {
                    "name": "logistics_service",
                    "order_sn": "202607240001",
                },
            }

        result = generate_structured_output(
            message="查订单 202607240001 的物流",
            system_prompt="你是意图识别助手。",
            response_model=_DecisionContract,
            mode=StructuredOutputMode.JSON_OBJECT,
            json_generator=fake_json_generator,
        )

        self.assertEqual("query_logistics", result.value.intent)
        self.assertEqual(StructuredOutputMode.JSON_OBJECT, result.mode)
        self.assertEqual("json_object", captured["output_mode"])
        self.assertIn("JSON Schema", captured["system_prompt"])
        self.assertIn("logistics_service", captured["system_prompt"])

    def test_gateway_rejects_unexpected_provider_fields(self) -> None:
        def fake_json_generator(**_kwargs):
            return {
                "intent": "query_logistics",
                "need_tool": True,
                "tool": {
                    "name": "logistics_service",
                    "order_sn": "202607240001",
                },
                "debug": "模型不应传给业务层的字段",
            }

        with self.assertRaises(StructuredOutputError):
            generate_structured_output(
                message="查物流",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=fake_json_generator,
            )

    def test_gateway_rejects_unexpected_nested_provider_fields(self) -> None:
        def fake_json_generator(**_kwargs):
            return {
                "intent": "query_logistics",
                "need_tool": True,
                "tool": {
                    "name": "logistics_service",
                    "order_sn": "202607240001",
                    "member_id": "模型无权传入的内部字段",
                },
            }

        with self.assertRaises(StructuredOutputError):
            generate_structured_output(
                message="查物流",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=fake_json_generator,
            )

    def test_gateway_rejects_wrong_scalar_types_without_coercion(self) -> None:
        def fake_json_generator(**_kwargs):
            return {
                "intent": "query_logistics",
                "need_tool": "true",
                "tool": {
                    "name": "logistics_service",
                    "order_sn": 202607240001,
                },
            }

        with self.assertRaises(StructuredOutputError):
            generate_structured_output(
                message="查物流",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=fake_json_generator,
            )

    def test_gateway_rejects_an_undeclared_enum_value(self) -> None:
        def fake_json_generator(**_kwargs):
            return {
                "intent": "query_logistics",
                "need_tool": True,
                "tool": {
                    "name": "delete_all_orders",
                    "order_sn": "202607240001",
                },
            }

        with self.assertRaises(StructuredOutputError):
            generate_structured_output(
                message="查物流",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=fake_json_generator,
            )

    def test_gateway_corrects_once_with_allowlisted_error_codes_only(self) -> None:
        calls: list[dict] = []

        def fake_json_generator(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {
                    "intent": "query_logistics",
                    "need_tool": "true",
                    "tool": {"name": "logistics_service", "order_sn": "202607240001"},
                    "debug": "untrusted candidate text must not be echoed",
                }
            return {
                "intent": "query_logistics",
                "need_tool": True,
                "tool": {"name": "logistics_service", "order_sn": "202607240001"},
            }

        result = generate_structured_output(
            message="查订单 202607240001 的物流",
            system_prompt="识别意图",
            response_model=_DecisionContract,
            json_generator=fake_json_generator,
            correction_context={
                "allowed_enum_values": ["query_logistics"],
                "schema_version": "v1",
            },
        )

        self.assertEqual("query_logistics", result.value.intent)
        self.assertEqual(2, len(calls))
        correction_message = calls[1]["message"]
        self.assertNotIn("查订单 202607240001 的物流", correction_message)
        self.assertIn('"validationErrors":["schema_invalid"]', correction_message)
        self.assertIn('"safeContext"', correction_message)
        self.assertNotIn("untrusted candidate text", correction_message)
        self.assertIn("受限校正", calls[1]["system_prompt"])

    def test_gateway_blocks_after_one_unsuccessful_protocol_correction(self) -> None:
        calls: list[dict] = []

        def always_invalid(**kwargs):
            calls.append(kwargs)
            return {
                "intent": "query_logistics",
                "need_tool": "still-invalid",
                "tool": {"name": "logistics_service", "order_sn": "hidden"},
            }

        with self.assertRaises(StructuredOutputError) as raised:
            generate_structured_output(
                message="查物流",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=always_invalid,
                correction_context={"schema_version": "v1"},
            )
        self.assertEqual(2, len(calls))
        self.assertTrue(raised.exception.correction_attempted)
        self.assertIn(raised.exception.validation_codes[0], {"correction_schema_invalid", "schema_invalid"})

    def test_gateway_does_not_resend_raw_input_when_no_safe_correction_context_exists(self) -> None:
        calls: list[dict] = []

        def malformed(**kwargs):
            calls.append(kwargs)
            return {
                "intent": "query_logistics",
                "need_tool": "true",
                "tool": {"name": "logistics_service", "order_sn": "202607240001"},
            }

        with self.assertRaises(StructuredOutputError) as raised:
            generate_structured_output(
                message="客户原话不能进入校正请求",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=malformed,
            )

        self.assertEqual(1, len(calls))
        self.assertFalse(raised.exception.correction_attempted)
        self.assertEqual(("schema_invalid",), raised.exception.validation_codes)

    def test_gateway_does_not_retry_a_provider_connectivity_failure(self) -> None:
        calls = 0

        def unavailable(**_kwargs):
            nonlocal calls
            calls += 1
            raise LLMServiceError("network unavailable", category="network")

        with self.assertRaises(StructuredOutputError) as raised:
            generate_structured_output(
                message="查物流",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=unavailable,
            )

        self.assertEqual(1, calls)
        self.assertFalse(raised.exception.correction_attempted)
        self.assertEqual(("network",), raised.exception.validation_codes)
        self.assertIn("failure_stage", raised.exception.diagnostics)
        self.assertEqual("http", raised.exception.diagnostics["failure_stage"])

    def test_gateway_exposes_only_safe_schema_failure_diagnostics(self) -> None:
        def malformed(**_kwargs):
            return {
                "intent": "query_logistics",
                "need_tool": "wrong-type",
                "tool": {"name": "logistics_service", "order_sn": "hidden"},
            }

        with self.assertRaises(StructuredOutputError) as raised:
            generate_structured_output(
                message="private customer message",
                system_prompt="识别意图",
                response_model=_DecisionContract,
                json_generator=malformed,
            )

        diagnostics = raised.exception.diagnostics
        self.assertEqual("schema_validate", diagnostics["failure_stage"])
        self.assertFalse(diagnostics["correction_attempted"])
        self.assertNotIn("private customer message", str(diagnostics))
        self.assertNotIn("hidden", str(diagnostics))

    def test_json_object_mode_adds_provider_request_flag(self) -> None:
        captured: dict = {}

        def fake_post(_url, _headers, payload):
            captured["payload"] = payload
            return _FakeResponse('{"ok": true}')

        fake_settings = type(
            "Settings",
            (),
            {
                "deepseek_api_key": "unit-test-key",
                "deepseek_base_url": "https://example.invalid",
                "deepseek_model": "unit-test-model",
            },
        )()
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch("app.services.llm_service._post_with_retry", side_effect=fake_post),
        ):
            value = generate_json(
                message="hello",
                system_prompt="return json",
                output_mode="json_object",
            )

        self.assertEqual({"ok": True}, value)
        self.assertEqual(
            {"type": "json_object"},
            captured["payload"]["response_format"],
        )

    def test_prompt_json_mode_preserves_existing_request_shape(self) -> None:
        captured: dict = {}

        def fake_post(_url, _headers, payload):
            captured["payload"] = payload
            return _FakeResponse('{"ok": true}')

        fake_settings = type(
            "Settings",
            (),
            {
                "deepseek_api_key": "unit-test-key",
                "deepseek_base_url": "https://example.invalid",
                "deepseek_model": "unit-test-model",
            },
        )()
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch("app.services.llm_service._post_with_retry", side_effect=fake_post),
        ):
            generate_json(message="hello", system_prompt="return json")

        self.assertNotIn("response_format", captured["payload"])

    def test_unknown_json_delivery_mode_fails_before_provider_call(self) -> None:
        with self.assertRaises(LLMServiceError):
            generate_json(
                message="hello",
                system_prompt="return json",
                output_mode="made_up_mode",
            )


if __name__ == "__main__":
    unittest.main()
