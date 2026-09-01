import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.services.llm_observability import capture_llm_metrics
from app.services.llm_service import LLMServiceError, generate_text, generate_with_tools


class _FakeResponse:
    status_code = 200
    request = httpx.Request("POST", "https://example.invalid")

    def raise_for_status(self) -> None:
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


class LLMServiceObservabilityTests(unittest.TestCase):
    def test_success_records_latency_attempts_and_usage_without_prompt(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-chat",
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
            deepseek_model="deepseek-chat",
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
            deepseek_model="deepseek-chat",
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

    def test_tool_planning_defaults_to_deterministic_temperature(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_api_key="test-key",
            deepseek_model="deepseek-chat",
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
        self.assertEqual(0, post.call_args.kwargs["json"]["temperature"])


if __name__ == "__main__":
    unittest.main()
