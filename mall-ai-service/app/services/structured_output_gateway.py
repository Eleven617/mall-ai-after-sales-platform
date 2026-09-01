"""A small, provider-neutral boundary for machine-readable LLM output.

Bounded customer-path call sites (intent routing, after-sales extraction and
policy-evidence verification) use this gateway before they can advance a
workflow.  It validates only the model's JSON contract and permits at most one
redacted correction attempt; it never bypasses Java authorization, business
facts, or write guards.
"""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.services.llm_service import LLMServiceError, generate_json


ModelT = TypeVar("ModelT", bound=BaseModel)
JsonGenerator = Callable[..., dict[str, Any]]
ModelValidator = Callable[[ModelT], Sequence[str] | None]
CorrectionContextBuilder = Callable[[ModelT], Mapping[str, Any] | None]

_SAFE_VALIDATION_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_CONTEXT_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_CONTEXT_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.:-]{0,95}$")
_SAFE_CONTEXT_VERSION = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SAFE_CORRECTION_CONTEXT_KEYS = {
    "allowed_chunk_ids",
    "allowed_enum_values",
    "candidate_projection",
    "candidate_count",
    "output_fields",
    "policy_version",
    "required_fields",
    "schema_version",
    "source_count",
}


class StructuredOutputMode(str, Enum):
    """How the provider is asked to deliver a JSON object."""

    PROMPT_JSON = "prompt_json"
    JSON_OBJECT = "json_object"


class StructuredOutputError(RuntimeError):
    """The model output was unavailable or failed the declared local contract."""

    def __init__(
        self,
        message: str,
        *,
        validation_codes: Sequence[str] = (),
        correction_attempted: bool = False,
    ) -> None:
        super().__init__(message)
        self.validation_codes = tuple(
            code
            for code in validation_codes
            if isinstance(code, str) and _SAFE_VALIDATION_CODE.fullmatch(code)
        )
        self.correction_attempted = correction_attempted


@dataclass(frozen=True)
class StructuredOutputResult(Generic[ModelT]):
    """A model object that has passed strict local schema validation."""

    value: ModelT
    mode: StructuredOutputMode


def generate_structured_output(
    *,
    message: str,
    system_prompt: str,
    response_model: type[ModelT],
    mode: StructuredOutputMode = StructuredOutputMode.PROMPT_JSON,
    temperature: float = 0,
    json_generator: JsonGenerator = generate_json,
    correction_context: Mapping[str, Any] | None = None,
    correction_system_prompt: str | None = None,
) -> StructuredOutputResult[ModelT]:
    """Generate and strictly validate one Pydantic-shaped JSON object.

    The schema is included in the model-facing contract, while the server uses
    ``strict=True`` and ``extra='forbid'`` regardless of a model class's
    default configuration.  This prevents silent coercion and accidental
    extra fields at the machine-to-machine boundary.

    This validates shape only.  It does *not* replace Java authorization,
    identifier extraction, RAG evidence verification, or confirmation gates.
    """
    return generate_structured_output_with_correction(
        message=message,
        system_prompt=system_prompt,
        response_model=response_model,
        mode=mode,
        temperature=temperature,
        json_generator=json_generator,
        correction_context=correction_context,
        correction_system_prompt=correction_system_prompt,
    )


def generate_structured_output_with_correction(
    *,
    message: str,
    system_prompt: str,
    response_model: type[ModelT],
    mode: StructuredOutputMode = StructuredOutputMode.PROMPT_JSON,
    temperature: float = 0,
    json_generator: JsonGenerator = generate_json,
    validate_result: ModelValidator[ModelT] | None = None,
    correction_message: str | None = None,
    correction_codes: Sequence[str] = (),
    correction_context: Mapping[str, Any] | None = None,
    correction_context_builder: CorrectionContextBuilder[ModelT] | None = None,
    correction_system_prompt: str | None = None,
) -> StructuredOutputResult[ModelT]:
    """Generate a structured result with at most one bounded correction.

    The first response is checked for strict schema validity and, optionally,
    for a caller-owned semantic contract.  A second provider call is made only
    for a contract failure and receives an allow-listed error-code envelope.
    This is deliberately not an unbounded reflection loop.  Transport failures
    remain owned by ``llm_service`` and fail closed without another call.
    """

    _ensure_response_model(response_model)
    contract_prompt = _append_schema_contract(system_prompt, response_model)
    first_codes: tuple[str, ...] = ()
    safe_context: dict[str, Any] | None = None
    try:
        value = _generate_and_validate_once(
            message=message,
            system_prompt=contract_prompt,
            response_model=response_model,
            mode=mode,
            temperature=temperature,
            json_generator=json_generator,
        )
        first_codes = _normalise_validation_codes(
            validate_result(value) if validate_result is not None else ()
        )
        if not first_codes:
            return StructuredOutputResult(value=value, mode=mode)
        if correction_context_builder is not None:
            safe_context = _safe_correction_context(correction_context_builder(value))
    except LLMServiceError as exc:
        # The transport layer already has bounded retries and a circuit breaker.
        # Only malformed provider output is eligible for this correction.
        if exc.category != "invalid_response":
            safe_code = exc.category if _SAFE_VALIDATION_CODE.fullmatch(exc.category) else "provider_unavailable"
            raise StructuredOutputError(
                "模型服务暂时不可用，未执行结构化校正",
                validation_codes=(safe_code,),
            ) from exc
        first_codes = ("schema_invalid",)
    except (ValidationError, TypeError, ValueError) as exc:
        first_codes = _normalise_validation_codes(
            getattr(exc, "validation_codes", ()) or ("schema_invalid",)
        )

    codes = _normalise_validation_codes(correction_codes) or first_codes or ("schema_invalid",)
    if safe_context is None:
        safe_context = _safe_correction_context(correction_context)
    if safe_context is None:
        # A correction must never resend the original user message merely to
        # make a malformed answer easier to repair.  Callers that have no
        # allow-listed projection stop safely and ask for a later retry.
        raise StructuredOutputError(
            "模型输出未通过契约，且不存在可安全发送的校正上下文",
            validation_codes=codes,
        )
    repair_envelope = {
        "validationErrors": list(codes),
        "safeContext": safe_context,
        "instruction": "仅修复已列出的契约错误；不要新增字段、权限或业务结论。",
    }
    repair_prompt = (
        "[validation_repair]\n"
        + (correction_message or "请根据已声明的 JSON Schema 重新生成输出。")
        + "\n"
        + _safe_json(repair_envelope)
    )
    try:
        repaired = _generate_and_validate_once(
            message=repair_prompt,
            system_prompt=(
                _append_schema_contract(correction_system_prompt or system_prompt, response_model)
                + "\n\n[受限校正]\n只允许修复 validationErrors 中列出的错误；"
                "不得输出解释或读取外部数据。校正最多执行一次。"
            ),
            response_model=response_model,
            mode=mode,
            temperature=temperature,
            json_generator=json_generator,
        )
        second_codes = _normalise_validation_codes(
            validate_result(repaired) if validate_result is not None else ()
        )
        if second_codes:
            raise StructuredOutputError(
                "模型输出二次校正仍未通过契约",
                validation_codes=second_codes,
                correction_attempted=True,
            )
        return StructuredOutputResult(value=repaired, mode=mode)
    except StructuredOutputError:
        raise
    except LLMServiceError as exc:
        raise StructuredOutputError(
            "模型输出二次校正不可用",
            validation_codes=("correction_provider_unavailable",),
            correction_attempted=True,
        ) from exc
    except (ValidationError, TypeError, ValueError) as exc:
        raise StructuredOutputError(
            "模型输出二次校正仍未通过契约",
            validation_codes=("correction_schema_invalid",),
            correction_attempted=True,
        ) from exc


def _ensure_response_model(response_model: type[ModelT]) -> None:
    if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
        raise TypeError("response_model 必须是 Pydantic BaseModel 子类")


def _generate_and_validate_once(
    *,
    message: str,
    system_prompt: str,
    response_model: type[ModelT],
    mode: StructuredOutputMode,
    temperature: float,
    json_generator: JsonGenerator,
) -> ModelT:
    payload = json_generator(
        message=message,
        system_prompt=system_prompt,
        temperature=temperature,
        output_mode=mode.value,
    )
    return response_model.model_validate(payload, strict=True, extra="forbid")


def _normalise_validation_codes(codes: Sequence[str] | None) -> tuple[str, ...]:
    if not codes:
        return ()
    return tuple(
        dict.fromkeys(
            code.strip()
            for code in codes
            if isinstance(code, str) and _SAFE_VALIDATION_CODE.fullmatch(code.strip())
        )
    )


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_correction_context(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Keep correction input to a small, non-textual allow-list.

    The first model call may need the customer message or reviewed policy
    content to understand the task.  A retry does not: it may only receive a
    typed projection such as known source IDs and the prior boolean decision.
    This prevents a validation failure from becoming a second disclosure of
    customer text, order numbers, RAG passages or prompt history.
    """

    if not isinstance(value, Mapping) or not value:
        return None
    sanitized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not _SAFE_CONTEXT_KEY.fullmatch(raw_key):
            return None
        if raw_key not in _SAFE_CORRECTION_CONTEXT_KEYS:
            return None
        if raw_key in {"candidate_count", "source_count"}:
            if not isinstance(raw_value, int) or isinstance(raw_value, bool) or not 0 <= raw_value <= 100:
                return None
            sanitized[raw_key] = raw_value
        elif raw_key in {"schema_version", "policy_version"}:
            if not isinstance(raw_value, str) or not _SAFE_CONTEXT_VERSION.fullmatch(raw_value):
                return None
            sanitized[raw_key] = raw_value
        elif raw_key in {"allowed_chunk_ids", "allowed_enum_values", "output_fields", "required_fields"}:
            if not isinstance(raw_value, (list, tuple)) or len(raw_value) > 32:
                return None
            if not all(
                isinstance(item, str) and _SAFE_CONTEXT_IDENTIFIER.fullmatch(item)
                for item in raw_value
            ):
                return None
            sanitized[raw_key] = list(raw_value)
        elif raw_key == "candidate_projection":
            if not isinstance(raw_value, Mapping) or set(raw_value) - {"sufficient", "supporting_chunk_ids"}:
                return None
            sufficient = raw_value.get("sufficient")
            chunk_ids = raw_value.get("supporting_chunk_ids")
            if not isinstance(sufficient, bool) or not isinstance(chunk_ids, (list, tuple)) or len(chunk_ids) > 32:
                return None
            if not all(
                isinstance(item, str) and _SAFE_CONTEXT_IDENTIFIER.fullmatch(item)
                for item in chunk_ids
            ):
                return None
            sanitized[raw_key] = {
                "sufficient": sufficient,
                "supporting_chunk_ids": list(chunk_ids),
            }
    return sanitized or None


def _append_schema_contract(system_prompt: str, response_model: type[BaseModel]) -> str:
    """Give the model the same explicit JSON shape that the server validates."""
    schema = json.dumps(
        response_model.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        f"{system_prompt.strip()}\n\n"
        "[结构化输出契约]\n"
        "只输出一个 JSON 对象；不要输出 Markdown、解释或代码块。"
        "对象必须符合以下 JSON Schema：\n"
        f"{schema}"
    )
