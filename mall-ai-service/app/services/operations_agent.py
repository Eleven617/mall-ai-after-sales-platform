"""Controlled Operations Analysis Agent.

The human selects the only permitted aggregation window in the UI.  The role
therefore makes exactly one structured model call: it summarizes the trusted,
already-scoped aggregate data and cannot call customer tools or write business
data.
"""

import json
import time
from dataclasses import dataclass
from typing import Callable

from app.schemas.operations import CaseHandoffView, OperationsAnalysisDraft, OperationsMetrics
from app.services.operations_client import get_after_sales_metrics
from app.services.structured_output_gateway import (
    StructuredOutputError,
    StructuredOutputMode,
    generate_structured_output,
)
from app.services.llm_service import LLMServiceError
from app.services.trace_service import record_trace


class OperationsAnalysisError(RuntimeError):
    """A safe failure; no partial or fabricated draft is returned."""

    def __init__(self, message: str, *, category: str = "unknown") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class OperationsAnalysisResult:
    case: CaseHandoffView
    metrics: OperationsMetrics
    draft: OperationsAnalysisDraft


GenerateStructured = Callable[..., object]


def analyze_case(
    *,
    case: CaseHandoffView,
    authorization: str | None,
    preferred_window_days: int = 7,
    generate_fn: GenerateStructured = generate_structured_output,
    metrics_fn: Callable[[int, str | None], OperationsMetrics] = get_after_sales_metrics,
) -> OperationsAnalysisResult:
    if preferred_window_days not in {7, 30}:
        raise OperationsAnalysisError("仅支持 7 或 30 天运营聚合窗口。")

    started_at = time.perf_counter()
    # The case reference is only used as an opaque trace correlation input and
    # is hashed by the trace boundary.  No handoff payload, aggregate value,
    # authorization header or model prompt reaches observability.
    record_trace("operations_analysis", "run_started", case.case_id)
    safe_case = case.model_dump(mode="json")
    try:
        # The window is an explicit human choice, not a model planning task.
        # It is validated both here and in the Java authority before any
        # aggregate query is made.
        metrics = metrics_fn(preferred_window_days, authorization)
        draft_result = generate_fn(
            message=json.dumps(
                {
                    "case": safe_case,
                    "metrics": metrics.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            system_prompt=(
                "你是受控的售后运营分析 Agent。只能依据给定的人工跟进摘要和"
                "可信聚合数字生成内部分析草稿。不得推测个人、订单、退款、仓储或通知事实；"
                "不得声称已执行订单、售后、退款、Outbox 或通知写入；不得输出行动执行指令；"
                "证据不足时标记 data_insufficient。只输出契约 JSON。"
            ),
            response_model=OperationsAnalysisDraft,
            mode=StructuredOutputMode.JSON_OBJECT,
            temperature=0,
        )
        draft = _model_value(draft_result, OperationsAnalysisDraft)
        result = OperationsAnalysisResult(case=case, metrics=metrics, draft=draft)
        record_trace(
            "operations_analysis",
            "run_finished",
            case.case_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result_kind="success",
        )
        return result
    except StructuredOutputError as exc:
        record_trace(
            "operations_analysis",
            "run_finished",
            case.case_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result_kind="failure",
        )
        raise OperationsAnalysisError(
            "运营分析草稿暂不可用，请稍后重试。",
            category=_structured_failure_category(exc),
        ) from exc
    except OperationsAnalysisError as exc:
        record_trace(
            "operations_analysis",
            "run_finished",
            case.case_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result_kind="failure",
        )
        raise OperationsAnalysisError(
            "运营分析草稿暂不可用，请稍后重试。",
            category=exc.category,
        ) from exc
    except Exception as exc:
        record_trace(
            "operations_analysis",
            "run_finished",
            case.case_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            result_kind="failure",
        )
        raise OperationsAnalysisError(
            "运营分析草稿暂不可用，请稍后重试。",
            category="infrastructure",
        ) from exc


def _structured_failure_category(exc: StructuredOutputError) -> str:
    """Keep a safe machine category without exposing provider details."""

    cause = exc.__cause__
    if isinstance(cause, LLMServiceError) and cause.category in {
        "missing_configuration",
        "network",
        "timeout",
        "rate_limited",
        "provider_unavailable",
        "provider_http",
    }:
        return "environment"
    return "model_contract"


def _model_value(value: object, expected_type: type):
    result = getattr(value, "value", value)
    if not isinstance(result, expected_type):
        raise OperationsAnalysisError("运营分析输出未通过契约校验。")
    return result
