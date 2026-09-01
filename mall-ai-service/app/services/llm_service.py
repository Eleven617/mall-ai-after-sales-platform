"""DeepSeek/OpenAI-compatible LLM boundary.

The customer path keeps its existing public behavior. Quality checkpoints can
temporarily collect latency, retry, and token metadata through the opt-in
context in ``llm_observability``; prompts and model output are never recorded.
"""
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

from app.config import settings
from app.services.llm_observability import (
    current_llm_call_policy,
    record_llm_metric,
)
from app.services.reliability_service import (
    DependencyCircuitOpen,
    reliability_governor,
)


_LOGGER = logging.getLogger("mall_ai.llm")
ResponseT = TypeVar("ResponseT")


class LLMServiceError(RuntimeError):
    """A provider or model-contract failure with a safe machine category."""

    def __init__(self, message: str, *, category: str = "unknown") -> None:
        super().__init__(message)
        self.category = category


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[dict] | None = None


def generate_text(
    message: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
) -> str:
    if not settings.deepseek_api_key:
        raise LLMServiceError(
            "Missing DEEPSEEK_API_KEY",
            category="missing_configuration",
        )

    url = f"{settings.deepseek_base_url}/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": temperature,
    }
    return _request_json("text", url, _headers(), payload, _extract_text)


def generate_with_tools(
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0,
) -> LLMResponse:
    """Request a bounded tool plan with deterministic sampling by default.

    Tool selection controls which read-only fact source is queried next.  It
    is therefore a planning contract rather than a creative response, so the
    safe default is zero temperature.  Callers that have an explicitly
    evaluated reason to vary sampling must opt in by passing a value here.
    """
    if not settings.deepseek_api_key:
        raise LLMServiceError(
            "Missing DEEPSEEK_API_KEY",
            category="missing_configuration",
        )

    url = f"{settings.deepseek_base_url}/v1/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": temperature,
    }
    result = _request_json("tools", url, _headers(), payload, _extract_response)
    _LOGGER.debug(
        "llm_tool_response has_content=%s tool_names=%s",
        bool(result.content),
        [tool_call.get("name") for tool_call in result.tool_calls or []],
    )
    return result


def generate_json(
    message: str,
    system_prompt: str,
    temperature: float = 0,
    output_mode: str = "prompt_json",
) -> dict:
    if output_mode not in {"prompt_json", "json_object"}:
        raise LLMServiceError(
            f"Unsupported JSON output mode: {output_mode}",
            category="invalid_response",
        )
    if not settings.deepseek_api_key:
        raise LLMServiceError(
            "Missing DEEPSEEK_API_KEY",
            category="missing_configuration",
        )

    url = f"{settings.deepseek_base_url}/v1/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "temperature": temperature,
    }
    if output_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}

    return _request_json("json", url, _headers(), payload, _extract_json_object)


def _request_json(
    operation: str,
    url: str,
    headers: dict,
    payload: dict,
    parser: Callable[[dict], ResponseT],
) -> ResponseT:
    """Make one logical request and emit only opted-in operational metrics."""
    started_at = time.monotonic()
    attempts = 1
    try:
        reliability_governor.ensure_dependency_available("llm")
        raw_response = _post_with_retry(url, headers, payload)
        # Keep compatibility with existing test seams that stub this private
        # helper with a response object instead of the new response/attempts
        # tuple.
        if isinstance(raw_response, tuple):
            response, attempts = raw_response
        else:
            response, attempts = raw_response, 1
        data = response.json()
        if not isinstance(data, dict):
            raise LLMServiceError(
                "Provider response JSON must be an object",
                category="invalid_response",
            )
        result = parser(data)
        usage = data.get("usage")
        usage_mapping = usage if isinstance(usage, dict) else {}
        record_llm_metric(
            operation=operation,
            outcome="succeeded",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=attempts,
            prompt_tokens=_usage_int(usage_mapping, "prompt_tokens"),
            completion_tokens=_usage_int(usage_mapping, "completion_tokens"),
            total_tokens=_usage_int(usage_mapping, "total_tokens"),
        )
        reliability_governor.record_dependency_success(
            "llm", duration_ms=_elapsed_ms(started_at)
        )
        return result
    except DependencyCircuitOpen as exc:
        error = LLMServiceError(
            "LLM provider circuit is cooling down",
            category="circuit_open",
        )
        record_llm_metric(
            operation=operation,
            outcome="failed",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=attempts,
            failure_class=error.category,
        )
        raise error from exc
    except LLMServiceError as exc:
        record_llm_metric(
            operation=operation,
            outcome="failed",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=attempts,
            failure_class=exc.category,
        )
        if exc.category != "circuit_open":
            reliability_governor.record_dependency_failure(
                "llm", duration_ms=_elapsed_ms(started_at)
            )
        raise
    except (ValueError, TypeError) as exc:
        error = LLMServiceError(
            "Provider returned invalid JSON",
            category="invalid_response",
        )
        record_llm_metric(
            operation=operation,
            outcome="failed",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=attempts,
            failure_class=error.category,
        )
        reliability_governor.record_dependency_failure(
            "llm", duration_ms=_elapsed_ms(started_at)
        )
        raise error from exc


def _post_with_retry(
    url: str,
    headers: dict,
    payload: dict,
) -> tuple[httpx.Response, int]:
    retry_status_codes = {429, 500, 502, 503, 504}
    last_error: Exception | None = None
    error_category = "unknown"
    policy = current_llm_call_policy()
    max_attempts = policy.max_attempts or 3
    timeout_seconds = settings.deepseek_timeout_seconds
    if policy.timeout_seconds is not None:
        timeout_seconds = min(timeout_seconds, policy.timeout_seconds)

    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            if response.status_code not in retry_status_codes:
                response.raise_for_status()
                return response, attempt

            last_error = httpx.HTTPStatusError(
                f"Provider temporary status: {response.status_code}",
                request=response.request,
                response=response,
            )
            error_category = (
                "rate_limited" if response.status_code == 429 else "provider_unavailable"
            )
        except httpx.TimeoutException as exc:
            last_error = exc
            error_category = "timeout"
        except httpx.HTTPStatusError as exc:
            last_error = exc
            error_category = "provider_http"
            break
        except httpx.NetworkError as exc:
            last_error = exc
            error_category = "network"
        except httpx.HTTPError as exc:
            last_error = exc
            error_category = "network"

        if attempt < max_attempts:
            time.sleep(1 + attempt)

    raise LLMServiceError(
        "LLM provider request failed",
        category=error_category,
    ) from last_error


def _extract_text(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        raise LLMServiceError(
            "Provider returned no choices",
            category="invalid_response",
        )
    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise LLMServiceError(
            "Provider returned an empty answer",
            category="invalid_response",
        )
    return content.strip()


def _extract_response(data: dict) -> LLMResponse:
    choices = data.get("choices", [])
    if not choices:
        raise LLMServiceError(
            "Provider returned no choices",
            category="invalid_response",
        )

    message = choices[0].get("message", {})
    content = (message.get("content") or "").strip() or None
    raw_tool_calls = message.get("tool_calls") or None
    tool_calls = None
    if raw_tool_calls:
        tool_calls = []
        try:
            for tool_call in raw_tool_calls:
                function = tool_call.get("function", {})
                tool_calls.append(
                    {
                        "name": function.get("name", ""),
                        "arguments": json.loads(function.get("arguments", "{}")),
                    }
                )
        except (AttributeError, TypeError, json.JSONDecodeError) as exc:
            raise LLMServiceError(
                "Provider returned invalid tool arguments",
                category="invalid_response",
            ) from exc

    if not content and not tool_calls:
        raise LLMServiceError(
            "Provider returned an empty answer",
            category="invalid_response",
        )
    return LLMResponse(content=content, tool_calls=tool_calls)


def _extract_json_object(data: dict) -> dict:
    text = _extract_text(data)
    try:
        payload = json.loads(_strip_markdown_json(text))
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMServiceError(
            "Model did not return valid JSON",
            category="invalid_response",
        ) from exc
    if not isinstance(payload, dict):
        raise LLMServiceError(
            "Model JSON result must be an object",
            category="invalid_response",
        )
    return payload


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.deepseek_api_key}",
    }


def _usage_int(usage: dict, key: str) -> int | None:
    value = usage.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


def _strip_markdown_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned
