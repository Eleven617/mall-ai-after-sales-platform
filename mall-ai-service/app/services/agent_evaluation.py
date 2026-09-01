"""Deterministic, privacy-safe offline evaluation for the read-only Agent.

This module replays synthetic model and tool outcomes against the real Agent
loop.  It deliberately does not contact a model provider, Java, Redis, or a
customer account.  It is therefore a regression/evaluation harness, not proof
of live-model quality or production integration.
"""
import copy
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.services.agent_service import run_agent_result
from app.services.llm_service import LLMResponse
from app.services.trace_service import InMemoryTraceSink, set_trace_sink_for_tests


class AgentEvaluationError(ValueError):
    """Raised when a committed synthetic evaluation case is malformed."""


def load_agent_evaluation_cases(path: Path) -> list[dict[str, Any]]:
    """Load reviewed synthetic cases.  Cases must never contain live customer data."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentEvaluationError(f"无法读取 Agent 评测集：{exc}") from exc

    if not isinstance(data, list):
        raise AgentEvaluationError("Agent 评测集顶层必须是 JSON 数组。")
    return data


def evaluate_agent_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Replay all cases and return only safe process/result observations.

    The returned report intentionally excludes raw user messages, tool
    arguments, raw tool payloads, model prose, tokens, and credentials.
    """
    reports: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        case_id = _safe_case_id(case, index)
        try:
            reports.append(evaluate_agent_case(case))
        except AgentEvaluationError as exc:
            reports.append(_invalid_case_report(case_id, str(exc)))

    passed_cases = sum(1 for report in reports if report["passed"])
    process_checks = _check_summary(
        check
        for report in reports
        for check in report["process_checks"].values()
    )
    result_checks = _check_summary(
        check
        for report in reports
        for check in report["result_checks"].values()
    )

    return {
        "mode": "offline_scripted",
        "total_cases": len(reports),
        "passed_cases": passed_cases,
        "failed_cases": len(reports) - passed_cases,
        "pass_rate": _ratio(passed_cases, len(reports)),
        "process_check_summary": process_checks,
        "result_check_summary": result_checks,
        "cases": reports,
    }


def evaluate_agent_case(case: dict[str, Any]) -> dict[str, Any]:
    """Replay one synthetic case through the production Agent control flow."""
    if not isinstance(case, dict):
        raise AgentEvaluationError("每个 Agent 评测案例必须是 JSON 对象。")

    case_id = _required_text(case, "id")
    user_message = _required_text(case, "user_message")
    expected = case.get("expected")
    if not isinstance(expected, dict):
        raise AgentEvaluationError(f"案例 {case_id} 缺少 expected 对象。")

    scripted_responses = _scripted_responses(case.get("model_responses"), case_id)
    tool_result_plan = _tool_result_plan(case.get("tool_results", {}), case_id)
    observed_tool_names: list[str] = []
    trace_sink = InMemoryTraceSink()

    def fake_call_tool(tool_call: Any, _context: Any) -> dict[str, Any]:
        tool_name = getattr(tool_call, "name", "")
        observed_tool_names.append(tool_name)
        results = tool_result_plan.get(tool_name)
        if not results:
            raise AgentEvaluationError(
                f"案例 {case_id} 没有为工具 {tool_name} 提供模拟结果。"
            )
        result = results.pop(0) if len(results) > 1 else results[0]
        return copy.deepcopy(result)

    set_trace_sink_for_tests(trace_sink)
    try:
        with (
            patch(
                "app.services.agent_service.generate_with_tools",
                side_effect=scripted_responses,
            ),
            patch(
                "app.services.agent_service.call_tool",
                side_effect=fake_call_tool,
            ),
        ):
            result = run_agent_result(
                user_message,
                session_id=f"offline-eval-{case_id}",
            )
    finally:
        set_trace_sink_for_tests(None)

    trace_events = [event.event for event in trace_sink.events]
    max_step = max(
        (
            event.details.get("step", 0)
            for event in trace_sink.events
            if isinstance(event.details.get("step", 0), int)
        ),
        default=0,
    )
    verified_fact_sources = [fact.source for fact in result.verified_facts]
    pending_tool_name = result.pending_tool_call.name if result.pending_tool_call else None

    observed = {
        "tool_names": observed_tool_names,
        "tool_call_count": len(observed_tool_names),
        "trace_events": trace_events,
        "max_step": max_step,
        "verified_fact_sources": verified_fact_sources,
        "pending_tool_name": pending_tool_name,
    }
    process_checks = _process_checks(expected, observed)
    result_checks = _result_checks(expected, result.answer, observed)
    checks = [*process_checks.values(), *result_checks.values()]

    return {
        "id": case_id,
        "passed": bool(checks) and all(checks),
        "process_checks": process_checks,
        "result_checks": result_checks,
        "observed": observed,
    }


def _scripted_responses(value: Any, case_id: str) -> list[LLMResponse | Exception]:
    if not isinstance(value, list) or not value:
        raise AgentEvaluationError(f"案例 {case_id} 必须提供非空 model_responses。")

    responses: list[LLMResponse | Exception] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise AgentEvaluationError(
                f"案例 {case_id} 的第 {index} 个模型响应必须是对象。"
            )
        error = item.get("raise_error")
        if error is not None:
            if not isinstance(error, str) or not error.strip():
                raise AgentEvaluationError(
                    f"案例 {case_id} 的 raise_error 必须是非空字符串。"
                )
            responses.append(RuntimeError(error))
            continue

        content = item.get("content")
        tool_calls = item.get("tool_calls")
        if content is not None and not isinstance(content, str):
            raise AgentEvaluationError(
                f"案例 {case_id} 的模型 content 必须是字符串或 null。"
            )
        if tool_calls is not None and not isinstance(tool_calls, list):
            raise AgentEvaluationError(
                f"案例 {case_id} 的模型 tool_calls 必须是数组或 null。"
            )
        responses.append(LLMResponse(content=content, tool_calls=tool_calls))
    return responses


def _tool_result_plan(value: Any, case_id: str) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        raise AgentEvaluationError(f"案例 {case_id} 的 tool_results 必须是对象。")

    plan: dict[str, list[dict[str, Any]]] = {}
    for tool_name, raw_results in value.items():
        if not isinstance(tool_name, str) or not tool_name:
            raise AgentEvaluationError(f"案例 {case_id} 存在无效工具名。")
        items = raw_results if isinstance(raw_results, list) else [raw_results]
        if not items or not all(isinstance(item, dict) for item in items):
            raise AgentEvaluationError(
                f"案例 {case_id} 的工具 {tool_name} 必须返回对象或对象数组。"
            )
        plan[tool_name] = copy.deepcopy(items)
    return plan


def _process_checks(expected: dict[str, Any], observed: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "tool_names" in expected:
        checks["tool_names"] = observed["tool_names"] == _string_list(
            expected["tool_names"], "expected.tool_names"
        )
    if "max_tool_calls" in expected:
        limit = _non_negative_int(expected["max_tool_calls"], "expected.max_tool_calls")
        checks["max_tool_calls"] = observed["tool_call_count"] <= limit
    if "trace_events_include" in expected:
        required = set(
            _string_list(expected["trace_events_include"], "expected.trace_events_include")
        )
        checks["trace_events_include"] = required.issubset(observed["trace_events"])
    if "trace_events_exclude" in expected:
        blocked = set(
            _string_list(expected["trace_events_exclude"], "expected.trace_events_exclude")
        )
        checks["trace_events_exclude"] = not bool(
            blocked.intersection(observed["trace_events"])
        )
    if "max_steps" in expected:
        limit = _non_negative_int(expected["max_steps"], "expected.max_steps")
        checks["max_steps"] = observed["max_step"] <= limit
    return checks


def _result_checks(
    expected: dict[str, Any],
    answer: str,
    observed: dict[str, Any],
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "answer_contains" in expected:
        terms = _string_list(expected["answer_contains"], "expected.answer_contains")
        checks["answer_contains"] = all(term in answer for term in terms)
    if "answer_not_contains" in expected:
        terms = _string_list(expected["answer_not_contains"], "expected.answer_not_contains")
        checks["answer_not_contains"] = not any(term in answer for term in terms)
    if "verified_fact_sources" in expected:
        checks["verified_fact_sources"] = observed["verified_fact_sources"] == _string_list(
            expected["verified_fact_sources"], "expected.verified_fact_sources"
        )
    if "pending_tool_name" in expected:
        pending_name = expected["pending_tool_name"]
        if pending_name is not None and not isinstance(pending_name, str):
            raise AgentEvaluationError("expected.pending_tool_name 必须是字符串或 null。")
        checks["pending_tool_name"] = observed["pending_tool_name"] == pending_name
    return checks


def _check_summary(values: Iterable[bool]) -> dict[str, float | int]:
    checks = list(values)
    passed = sum(1 for check in checks if check)
    return {
        "total": len(checks),
        "passed": passed,
        "pass_rate": _ratio(passed, len(checks)),
    }


def _invalid_case_report(case_id: str, error: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "passed": False,
        "process_checks": {"case_is_valid": False},
        "result_checks": {},
        "observed": {"error": error},
    }


def _safe_case_id(case: Any, index: int) -> str:
    if isinstance(case, dict) and isinstance(case.get("id"), str) and case["id"].strip():
        return case["id"].strip()
    return f"invalid-case-{index}"


def _required_text(case: dict[str, Any], key: str) -> str:
    value = case.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentEvaluationError(f"案例缺少非空 {key}。")
    return value.strip()


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise AgentEvaluationError(f"{field_name} 必须是非空字符串数组。")
    return value


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AgentEvaluationError(f"{field_name} 必须是非负整数。")
    return value


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
