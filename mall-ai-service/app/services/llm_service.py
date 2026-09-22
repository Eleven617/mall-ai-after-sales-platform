"""DeepSeek/OpenAI-compatible LLM boundary.

The customer path keeps its existing public behavior. Quality checkpoints can
temporarily collect latency, retry, and token metadata through the opt-in
context in ``llm_observability``; prompts and model output are never recorded.
"""
import json
import logging
import time
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

from app.config import settings
from app.services.llm_observability import (
    current_llm_call_policy,
    current_llm_operation,
    current_protocol_correction,
    record_llm_metric,
)
from app.services.provider_guard import ProviderGuardError, assert_provider_request_allowed
from app.services.release_ledger import (
    ReleaseLedgerBudgetError,
    ReleaseLedgerIntegrityError,
    reserve_provider_attempt,
    settle_provider_attempt,
)
from app.services.reliability_service import (
    DependencyCircuitOpen,
    reliability_governor,
)


_LOGGER = logging.getLogger("mall_ai.llm")
ResponseT = TypeVar("ResponseT")
DEEPSEEK_THINKING_MODE = "enabled"
DEEPSEEK_REASONING_EFFORT = "high"


def _agent_reasoning_control() -> dict[str, object]:
    """Use the single reviewed reasoning profile for every DeepSeek call."""
    return {
        "thinking": {"type": DEEPSEEK_THINKING_MODE},
        "reasoning_effort": DEEPSEEK_REASONING_EFFORT,
    }


class LLMServiceError(RuntimeError):
    """A provider or model-contract failure with a safe machine category."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "unknown",
        attempts: int | None = None,
        request_id_hash: str | None = None,
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.attempts = attempts
        self.request_id_hash = request_id_hash
        self.diagnostics = dict(diagnostics or {})


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[dict] | None = None
    reasoning_content: str | None = None


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
        **_agent_reasoning_control(),
    }
    return _request_json(current_llm_operation("text"), url, _headers(), payload, _extract_text)


def generate_with_tools(
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0,
) -> LLMResponse:
    """Request a bounded tool plan with the reviewed high-thinking profile.

    ``temperature`` remains in the public signature for caller compatibility,
    but DeepSeek ignores it in thinking mode and it is therefore not sent.
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
        **_agent_reasoning_control(),
    }
    result = _request_json(current_llm_operation("tools"), url, _headers(), payload, _extract_response)
    _LOGGER.debug(
        "llm_tool_response has_content=%s tool_count=%s",
        bool(result.content),
        len(result.tool_calls or []),
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
        **_agent_reasoning_control(),
    }
    if output_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}

    return _request_json(current_llm_operation("json"), url, _headers(), payload, _extract_json_object)


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
    provider_request_id_hash: str | None = None
    usage_mapping: dict = {}
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
        provider_request_id_hash = _response_request_id_hash(response)
        data = response.json()
        if not isinstance(data, dict):
            raise LLMServiceError(
                "Provider response JSON must be an object",
                category="invalid_response",
            )
        usage = data.get("usage")
        usage_mapping = usage if isinstance(usage, dict) else {}
        try:
            result = parser(data)
        except LLMServiceError as exc:
            # Provider request identifiers are useful for support without
            # exposing a raw response header or model payload.
            request_id_hash = exc.request_id_hash or _response_request_id_hash(response)
            raise LLMServiceError(
                str(exc),
                category=exc.category,
                attempts=exc.attempts,
                request_id_hash=request_id_hash,
                diagnostics={**_provider_envelope_diagnostics(data), **exc.diagnostics},
            ) from exc
        record_llm_metric(
            operation=operation,
            outcome="succeeded",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=attempts,
            prompt_tokens=_usage_int(usage_mapping, "prompt_tokens"),
            completion_tokens=_usage_int(usage_mapping, "completion_tokens"),
            total_tokens=_usage_int(usage_mapping, "total_tokens"),
            provider_request_id_hash=provider_request_id_hash,
            protocol_correction=current_protocol_correction(),
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
            provider_request_id_hash=provider_request_id_hash,
        )
        raise error from exc
    except ProviderGuardError as exc:
        error = LLMServiceError(
            "外部模型请求被安全策略阻止",
            category=exc.category,
        )
        record_llm_metric(
            operation=operation,
            outcome="failed",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=0,
            failure_class=error.category,
            ledger_event_type="test",
        )
        raise error from exc
    except LLMServiceError as exc:
        if isinstance(exc.attempts, int) and exc.attempts > 0:
            attempts = exc.attempts
        record_llm_metric(
            operation=operation,
            outcome="failed",
            elapsed_ms=_elapsed_ms(started_at),
            attempts=attempts,
            failure_class=exc.category,
            prompt_tokens=_usage_int(usage_mapping, "prompt_tokens"),
            completion_tokens=_usage_int(usage_mapping, "completion_tokens"),
            total_tokens=_usage_int(usage_mapping, "total_tokens"),
            provider_request_id_hash=exc.request_id_hash or provider_request_id_hash,
            protocol_correction=current_protocol_correction(),
            write_ledger=exc.category != "budget_exhausted",
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
            prompt_tokens=_usage_int(usage_mapping, "prompt_tokens"),
            completion_tokens=_usage_int(usage_mapping, "completion_tokens"),
            total_tokens=_usage_int(usage_mapping, "total_tokens"),
            provider_request_id_hash=provider_request_id_hash,
            protocol_correction=current_protocol_correction(),
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
    # Keep the check at the lowest shared HTTP boundary so a new caller cannot
    # accidentally bypass the public LLM helpers or the release runner.
    assert_provider_request_allowed(url)
    retry_status_codes = {429, 500, 502, 503, 504}
    last_error: Exception | None = None
    error_category = "unknown"
    last_request_id_hash: str | None = None
    policy = current_llm_call_policy()
    max_attempts = policy.max_attempts or 3
    timeout_seconds = settings.deepseek_timeout_seconds
    if policy.timeout_seconds is not None:
        timeout_seconds = min(timeout_seconds, policy.timeout_seconds)

    for attempt in range(1, max_attempts + 1):
        reservation_id: str | None = None
        last_error = None
        try:
            try:
                reservation_id = reserve_provider_attempt(operation="llm")
            except ReleaseLedgerBudgetError as exc:
                raise LLMServiceError(
                    "Provider request budget exhausted before network access",
                    category="budget_exhausted",
                    attempts=attempt - 1,
                ) from exc
            except ReleaseLedgerIntegrityError as exc:
                raise LLMServiceError(
                    "Release ledger cannot be reconciled before network access",
                    category="ledger_malformed",
                    attempts=attempt - 1,
                ) from exc
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
                trust_env=False,
            )
            last_request_id_hash = _response_request_id_hash(response)
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
        except LLMServiceError:
            raise
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
        finally:
            settle_provider_attempt(
                reservation_id,
                outcome="succeeded" if last_error is None else "failed",
            )

        if attempt < max_attempts:
            time.sleep(1 + attempt)

    raise LLMServiceError(
        "LLM provider request failed",
        category=error_category,
        attempts=attempt,
        request_id_hash=last_request_id_hash,
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
    raw_reasoning_content = message.get("reasoning_content")
    reasoning_content = (
        raw_reasoning_content
        if isinstance(raw_reasoning_content, str) and raw_reasoning_content
        else None
    )
    raw_tool_calls = message.get("tool_calls") or None
    tool_calls = None
    if raw_tool_calls:
        if not isinstance(raw_tool_calls, list):
            raise LLMServiceError(
                "Provider tool_calls must be an array",
                category="invalid_response",
            )
        tool_calls = []
        try:
            for tool_call in raw_tool_calls:
                call_id = tool_call.get("id")
                if not isinstance(call_id, str) or not call_id.strip():
                    raise LLMServiceError(
                        "Provider tool call is missing its id",
                        category="invalid_response",
                    )
                function = tool_call.get("function", {})
                if not isinstance(function, dict):
                    raise LLMServiceError(
                        "Provider tool call function is invalid",
                        category="invalid_response",
                    )
                tool_calls.append(
                    {
                        "id": call_id,
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
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )


def _extract_json_object(data: dict) -> dict:
    text = _extract_text(data)
    try:
        payload = json.loads(_strip_markdown_json(text))
    except (json.JSONDecodeError, TypeError) as exc:
        # Some OpenAI-compatible providers occasionally prepend a short
        # presentation label despite JSON-object mode.  Accept only one
        # bounded embedded object, then hand it to the existing strict schema
        # validator.  The raw text remains process-local and is never traced,
        # persisted or exposed to callers.
        payload = _extract_embedded_json_object(text)
        if payload is None:
            raise LLMServiceError(
                "Model did not return valid JSON",
                category="invalid_response",
                diagnostics={"schema_error_kinds": ["json_parse"]},
            ) from exc
    if not isinstance(payload, dict):
        raise LLMServiceError(
            "Model JSON result must be an object",
            category="invalid_response",
            diagnostics={"schema_error_kinds": ["root_type"]},
        )
    return payload


def _provider_envelope_diagnostics(data: dict) -> dict[str, object]:
    """Return bounded response metadata without model text or reasoning."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return {"has_content": False, "has_tool_calls": False, "finish_reason": "missing_choice"}
    choice = choices[0]
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    raw_finish = choice.get("finish_reason")
    finish_reason = raw_finish if raw_finish in {"stop", "length", "tool_calls", "content_filter"} else None
    return {
        "has_content": isinstance(message.get("content"), str) and bool(message.get("content", "").strip()),
        "has_tool_calls": isinstance(message.get("tool_calls"), list) and bool(message.get("tool_calls")),
        "finish_reason": finish_reason,
    }


def _extract_embedded_json_object(text: str) -> dict | None:
    if not isinstance(text, str) or len(text) > 32_000:
        return None
    start = text.find("{")
    if start < 0 or start > 240:
        return None
    try:
        value, end = json.JSONDecoder().raw_decode(text[start:])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    trailing = text[start + end:].strip()
    if trailing and len(trailing) > 240:
        return None
    return value if isinstance(value, dict) else None


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


def _response_request_id_hash(response: object) -> str | None:
    """Hash a provider request id for diagnostics, never return the raw id."""

    headers = getattr(response, "headers", None)
    if not headers:
        return None
    for key in ("x-request-id", "request-id", "x-deepseek-request-id"):
        value = headers.get(key)
        if isinstance(value, str) and value.strip():
            return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:24]
    return None


def _strip_markdown_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned
