import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.services.llm_observability import capture_llm_metrics
from app.services.provider_guard import provider_access_context
from app.services.llm_service import (
    LLMServiceError,
    _extract_response,
    generate_text,
    generate_with_tools,
)


class _FakeResponse:
    status_code = 200
    request = httpx.Request("POST", "https://example.invalid")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = self.request
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"synthetic status {self.status_code}",
                request=request,
                response=response,
            )
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
        }


class _InvalidContractResponse(_FakeResponse):
    def json(self) -> dict:
        return {
            "choices": [],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 0,
                "total_tokens": 12,
            },
        }


class _ThinkingToolResponse(_FakeResponse):
    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "synthetic private reasoning",
                        "tool_calls": [
                            {
                                "id": "call_provider_001",
                                "type": "function",
                                "function": {
                                    "name": "order_service",
                                    "arguments": '{"order_sn":"synthetic-order"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
        }


class _StatusResponse(_FakeResponse):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _MissingToolIdResponse(_FakeResponse):
    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "order_service",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        }


class LLMServiceObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._provider_grant = provider_access_context(
            mode="mock",
            release_id="fixture-release",
            batch_id="fixture-batch",
            ledger_path="C:/fixture/release.jsonl",
            runtime_commit="a" * 40,
            authorized=True,
            allow_mock=True,
        )
        self._provider_grant.__enter__()

    def tearDown(self) -> None:
        self._provider_grant.__exit__(None, None, None)

    def test_success_records_latency_attempts_and_usage_without_prompt(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch("app.services.llm_service.httpx.post", return_value=_FakeResponse()),
            capture_llm_metrics(max_attempts=1, timeout_seconds=1.0) as sink,
        ):
            self.assertEqual("ok", generate_text("private prompt"))

        self.assertEqual(1, len(sink.events))
        event = sink.events[0]
        self.assertEqual("succeeded", event.outcome)
        self.assertEqual(12, event.prompt_tokens)
        self.assertEqual(5, event.completion_tokens)
        self.assertEqual(17, event.total_tokens)
        self.assertGreaterEqual(event.elapsed_ms, 0)

    def test_network_failure_is_classified_and_retry_cap_is_applied(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch(
                "app.services.llm_service.httpx.post",
                side_effect=httpx.ConnectError("offline"),
            ) as post,
            capture_llm_metrics(max_attempts=1, timeout_seconds=1.0) as sink,
        ):
            with self.assertRaises(LLMServiceError) as raised:
                generate_text("private prompt")

        self.assertEqual("network", raised.exception.category)
        self.assertEqual(1, post.call_count)
        self.assertEqual("network", sink.events[0].failure_class)

    def test_invalid_model_contract_is_recorded_as_one_failed_call(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch(
                "app.services.llm_service.httpx.post",
                return_value=_InvalidContractResponse(),
            ),
            capture_llm_metrics(max_attempts=1, timeout_seconds=1.0) as sink,
        ):
            with self.assertRaises(LLMServiceError) as raised:
                generate_text("private prompt")

        self.assertEqual("invalid_response", raised.exception.category)
        self.assertEqual(1, len(sink.events))
        self.assertEqual("failed", sink.events[0].outcome)
        self.assertEqual("invalid_response", sink.events[0].failure_class)

    def test_tool_planning_uses_the_reviewed_high_reasoning_profile(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch("app.services.llm_service.httpx.post", return_value=_FakeResponse()) as post,
            capture_llm_metrics(max_attempts=1, timeout_seconds=1.0),
        ):
            response = generate_with_tools(
                messages=[{"role": "user", "content": "synthetic"}],
                tools=[],
            )

        self.assertEqual("ok", response.content)
        self.assertEqual(
            {"type": "enabled"},
            post.call_args.kwargs["json"]["thinking"],
        )
        self.assertEqual("high", post.call_args.kwargs["json"]["reasoning_effort"])
        self.assertNotIn("temperature", post.call_args.kwargs["json"])
        self.assertNotIn("tool_choice", post.call_args.kwargs["json"])

    def test_thinking_tool_response_preserves_transient_reasoning_and_call_id(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        with (
            patch("app.services.llm_service.settings", fake_settings),
            patch(
                "app.services.llm_service.httpx.post",
                return_value=_ThinkingToolResponse(),
            ),
            capture_llm_metrics(max_attempts=1, timeout_seconds=1.0),
        ):
            response = generate_with_tools(
                messages=[{"role": "user", "content": "synthetic"}],
                tools=[],
            )

        self.assertEqual("synthetic private reasoning", response.reasoning_content)
        self.assertEqual("call_provider_001", response.tool_calls[0]["id"])

    def test_auth_and_payment_provider_statuses_are_not_retried(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        for status in (401, 402, 403):
            with self.subTest(status=status), patch(
                "app.services.llm_service.settings", fake_settings
            ), patch(
                "app.services.llm_service.httpx.post",
                return_value=_StatusResponse(status),
            ) as post, capture_llm_metrics(max_attempts=3, timeout_seconds=1.0) as sink:
                with self.assertRaises(LLMServiceError) as raised:
                    generate_text("synthetic prompt")
            self.assertEqual("provider_http", raised.exception.category)
            self.assertEqual(1, post.call_count)
            self.assertEqual(1, sink.events[0].attempts)

    def test_retryable_status_and_timeout_observe_the_configured_cap(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        for status, category in ((429, "rate_limited"), (503, "provider_unavailable")):
            with self.subTest(status=status), patch(
                "app.services.llm_service.settings", fake_settings
            ), patch(
                "app.services.llm_service.httpx.post",
                return_value=_StatusResponse(status),
            ) as post, patch("app.services.llm_service.time.sleep"), capture_llm_metrics(
                max_attempts=2, timeout_seconds=1.0
            ) as sink:
                with self.assertRaises(LLMServiceError) as raised:
                    generate_text("synthetic prompt")
            self.assertEqual(category, raised.exception.category)
            self.assertEqual(2, post.call_count)
            self.assertEqual(2, sink.events[0].attempts)

    def test_missing_provider_tool_id_is_a_contract_failure(self) -> None:
        with self.assertRaises(LLMServiceError) as raised:
            _extract_response(_MissingToolIdResponse().json())
        self.assertEqual("invalid_response", raised.exception.category)

    def test_timeout_is_bounded_and_never_leaks_payload_content(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://example.invalid",
            deepseek_timeout_seconds=5.0,
        )
        with patch(
            "app.services.llm_service.settings", fake_settings
        ), patch(
            "app.services.llm_service.httpx.post",
            side_effect=httpx.ReadTimeout("synthetic timeout"),
        ) as post, patch("app.services.llm_service.time.sleep"), capture_llm_metrics(
            max_attempts=2, timeout_seconds=1.0
        ) as sink:
            with self.assertRaises(LLMServiceError) as raised:
                generate_text("private-order-and-token")
        self.assertEqual("timeout", raised.exception.category)
        self.assertEqual(2, post.call_count)
        self.assertEqual("timeout", sink.events[0].failure_class)


if __name__ == "__main__":
    unittest.main()
