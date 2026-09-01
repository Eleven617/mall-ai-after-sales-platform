"""Bounded, privacy-safe runners for explicit evaluation checkpoints.

This module is intentionally not imported by any customer router. It turns a
fixed set of reviewed cases into a finite developer/CI run with progress,
per-case timing, provider metrics, and an unambiguous failure category.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.llm_observability import (
    TokenPricing,
    capture_llm_metrics,
    summarize_llm_metrics,
)
from app.services.llm_service import LLMServiceError
from app.services.embedding_service import EmbeddingServiceError


CaseEvaluator = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ProgressListener = Callable[[dict[str, object]], None]
Clock = Callable[[], float]

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_ENVIRONMENT_ERROR_CLASSES = {
    "missing_configuration",
    "network",
    "timeout",
    "rate_limited",
    "provider_unavailable",
    "provider_http",
}
_UNAVAILABLE_OUTCOMES = {
    "retrieval_unavailable",
    "evidence_verification_unavailable",
    "answer_generation_unavailable",
}


@dataclass(frozen=True)
class CheckpointBudget:
    max_cases: int
    max_total_seconds: float
    llm_timeout_seconds: float | None = None
    llm_max_attempts: int | None = None

    def __post_init__(self) -> None:
        if self.max_cases < 1:
            raise ValueError("max_cases must be at least one")
        if self.max_total_seconds <= 0:
            raise ValueError("max_total_seconds must be positive")
        if self.llm_timeout_seconds is not None and self.llm_timeout_seconds <= 0:
            raise ValueError("llm_timeout_seconds must be positive when set")
        if self.llm_max_attempts is not None and self.llm_max_attempts < 1:
            raise ValueError("llm_max_attempts must be at least one when set")


def run_quality_checkpoint(
    *,
    checkpoint_name: str,
    cases: Iterable[Mapping[str, Any]],
    evaluate_case: CaseEvaluator,
    budget: CheckpointBudget,
    pricing: TokenPricing | None = None,
    progress_listener: ProgressListener | None = None,
    clock: Clock = time.monotonic,
) -> dict[str, object]:
    """Run reviewed cases without exposing their text or model output.

    The evaluator may return its existing detailed result. This runner projects
    that into safe status/check-name metrics before producing a checkpoint
    report. A time budget is checked between cases; the LLM policy additionally
    caps one in-flight provider call during explicit live evaluation.
    """
    case_list = list(cases)
    if not checkpoint_name or not checkpoint_name.strip():
        raise ValueError("checkpoint_name must be non-empty")
    if not callable(evaluate_case):
        raise TypeError("evaluate_case must be callable")

    started_at = clock()
    results: list[dict[str, object]] = []
    attempted_cases = 0
    budget_exhausted_cases = 0

    with capture_llm_metrics(
        timeout_seconds=budget.llm_timeout_seconds,
        max_attempts=budget.llm_max_attempts,
    ) as metric_sink:
        for index, case in enumerate(case_list, start=1):
            case_id = _safe_case_id(case, index)
            elapsed_before_case = _elapsed_ms(started_at, clock())
            if index > budget.max_cases:
                budget_exhausted_cases = len(case_list) - index + 1
                break
            elif elapsed_before_case >= int(budget.max_total_seconds * 1000):
                budget_exhausted_cases = len(case_list) - index + 1
                break

            attempted_cases += 1
            metric_start = len(metric_sink.events)
            case_started_at = clock()
            result = _evaluate_one_case(
                case_id=case_id,
                case=case,
                evaluate_case=evaluate_case,
            )
            result["elapsed_ms"] = _elapsed_ms(case_started_at, clock())
            case_metrics = metric_sink.events[metric_start:]
            result["llm"] = summarize_llm_metrics(case_metrics, pricing)

            results.append(result)
            if progress_listener:
                progress_listener(
                    {
                        "checkpoint": checkpoint_name,
                        "completed_cases": len(results),
                        "total_cases": len(case_list),
                        "attempted_cases": attempted_cases,
                        "last_case_id": case_id,
                        "last_case_status": result["status"],
                        "elapsed_ms": _elapsed_ms(started_at, clock()),
                    }
                )

    status_counts = {
        status: sum(1 for result in results if result["status"] == status)
        for status in (
            "passed",
            "review_required",
            "quality_failed",
            "environment_blocked",
            "budget_exhausted",
        )
    }
    status_counts["budget_exhausted"] += budget_exhausted_cases
    return {
        "checkpoint": checkpoint_name.strip(),
        "status": _overall_status(status_counts),
        "progress": {
            "completed_cases": len(results),
            "total_cases": len(case_list),
            "attempted_cases": attempted_cases,
            "not_run_cases": budget_exhausted_cases,
            "elapsed_ms": _elapsed_ms(started_at, clock()),
            "max_cases": budget.max_cases,
            "max_total_seconds": budget.max_total_seconds,
        },
        "case_status_counts": status_counts,
        "llm": summarize_llm_metrics(metric_sink.events, pricing),
        "cases": results,
    }


def _evaluate_one_case(
    *,
    case_id: str,
    case: Mapping[str, Any],
    evaluate_case: CaseEvaluator,
) -> dict[str, object]:
    try:
        report = evaluate_case(case)
    except LLMServiceError as exc:
        return {
            "id": case_id,
            "status": (
                "environment_blocked"
                if exc.category in _ENVIRONMENT_ERROR_CLASSES
                else "quality_failed"
            ),
            "failure_classes": [exc.category],
            "failed_checks": [],
        }
    except (
        httpx.HTTPError,
        TimeoutError,
        ConnectionError,
        OSError,
        EmbeddingServiceError,
    ) as exc:
        del exc
        return {
            "id": case_id,
            "status": "environment_blocked",
            "failure_classes": ["environment_dependency"],
            "failed_checks": [],
        }
    except Exception as exc:
        del exc
        return {
            "id": case_id,
            "status": "quality_failed",
            "failure_classes": ["evaluation_error"],
            "failed_checks": [],
        }

    if not isinstance(report, Mapping):
        return {
            "id": case_id,
            "status": "quality_failed",
            "failure_classes": ["invalid_evaluation_report"],
            "failed_checks": [],
        }
    status = _status_from_report(report)
    return {
        "id": case_id,
        "status": status,
        "failure_classes": _failure_classes_from_report(report, status),
        "failed_checks": _failed_check_names(report),
    }


def _status_from_report(report: Mapping[str, Any]) -> str:
    if report.get("status") == "environment_blocked":
        return "environment_blocked"
    observed = report.get("observed")
    if isinstance(observed, Mapping) and observed.get("outcome") in _UNAVAILABLE_OUTCOMES:
        return "environment_blocked"
    if report.get("passed") is True:
        review_checks = report.get("review_checks")
        if isinstance(review_checks, Mapping) and any(
            value is False for value in review_checks.values()
        ):
            return "review_required"
        return "passed"
    return "quality_failed"


def _failure_classes_from_report(
    report: Mapping[str, Any],
    status: str,
) -> list[str]:
    if status == "passed":
        return []
    if status == "review_required":
        return ["review_signal"]
    if status == "environment_blocked":
        observed = report.get("observed")
        if isinstance(observed, Mapping):
            outcome = observed.get("outcome")
            if outcome in _UNAVAILABLE_OUTCOMES:
                return [str(outcome)]
        return ["environment_dependency"]
    return ["contract_failed"]


def _failed_check_names(report: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("checks", "process_checks", "result_checks", "review_checks"):
        checks = report.get(key)
        if not isinstance(checks, Mapping):
            continue
        for name, passed in checks.items():
            if passed is False and isinstance(name, str) and _SAFE_CASE_ID.fullmatch(name):
                names.append(f"{key}.{name}")
    return sorted(names)


def _safe_case_id(case: Mapping[str, Any], index: int) -> str:
    value = case.get("id") if isinstance(case, Mapping) else None
    if isinstance(value, str) and _SAFE_CASE_ID.fullmatch(value):
        return value
    return f"case-{index}"


def _overall_status(counts: Mapping[str, int]) -> str:
    if counts["quality_failed"]:
        return "quality_failed"
    if counts["environment_blocked"]:
        return "environment_blocked"
    if counts["budget_exhausted"]:
        return "budget_exhausted"
    if counts["review_required"]:
        return "review_required"
    return "passed"


def _elapsed_ms(started_at: float, current: float) -> int:
    return max(0, round((current - started_at) * 1000))
