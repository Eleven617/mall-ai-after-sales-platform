"""Offline evaluation for the LangGraph diagnosis flow.

Cases are synthetic and only assert safe process/result properties. They do
not prove live model planning quality or Java integration quality.
"""

import copy
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.services.diagnosis_agent import run_diagnosis_agent
from app.services.durable_diagnosis import (
    DurableDiagnosisManager,
    SanitizedMemorySaver,
    set_durable_diagnosis_manager_for_tests,
)
from app.services.llm_service import LLMResponse
from app.services.trace_service import InMemoryTraceSink, set_trace_sink_for_tests
from app.services.tool_context import ToolExecutionContext


class DiagnosisEvaluationError(ValueError):
    pass


def load_diagnosis_cases(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosisEvaluationError(f"无法读取诊断评测集：{exc}") from exc
    if not isinstance(data, list):
        raise DiagnosisEvaluationError("诊断评测集顶层必须是 JSON 数组。")
    return data


def evaluate_diagnosis_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    reports = [evaluate_diagnosis_case(case) for case in cases]
    passed = sum(1 for report in reports if report["passed"])
    return {
        "mode": "offline_scripted_langgraph",
        "total_cases": len(reports),
        "passed_cases": passed,
        "failed_cases": len(reports) - passed,
        "pass_rate": passed / len(reports) if reports else 0.0,
        "cases": reports,
    }


def evaluate_diagnosis_case(case: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise DiagnosisEvaluationError("每个诊断案例必须是 JSON 对象。")
    case_id = _required_text(case, "id")
    responses = _responses(case.get("model_responses"), case_id)
    tool_plan = _tool_plan(case.get("tool_results", {}), case_id)
    observed_tools: list[str] = []
    trace_sink = InMemoryTraceSink()

    def generate_fn(_messages: list[dict], _tools: list[dict]) -> LLMResponse:
        if not responses:
            raise DiagnosisEvaluationError(f"案例 {case_id} 的模型响应已耗尽。")
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def call_tool_fn(tool_call: Any, _context: ToolExecutionContext) -> dict[str, Any]:
        name = tool_call.name
        observed_tools.append(name)
        results = tool_plan.get(name)
        if not results:
            raise DiagnosisEvaluationError(f"案例 {case_id} 缺少工具 {name} 的模拟结果。")
        return copy.deepcopy(results.pop(0) if len(results) > 1 else results[0])

    set_trace_sink_for_tests(trace_sink)
    # Offline synthetic evaluation must never depend on the configured Redis
    # runtime or leave durable state behind.
    set_durable_diagnosis_manager_for_tests(
        DurableDiagnosisManager(SanitizedMemorySaver(), ttl_seconds=600)
    )
    try:
        result = run_diagnosis_agent(
            user_message=_required_text(case, "user_message"),
            tool_context=ToolExecutionContext(),
            session_id=f"offline-diagnosis-{case_id}",
            generate_fn=generate_fn,
            call_tool_fn=call_tool_fn,
        )
    finally:
        set_trace_sink_for_tests(None)
        set_durable_diagnosis_manager_for_tests(None)

    expected = case.get("expected", {})
    if not isinstance(expected, dict):
        raise DiagnosisEvaluationError(f"案例 {case_id} 缺少 expected 对象。")
    diagnosis = result.diagnosis
    observed = {
        "tool_names": observed_tools,
        "trace_events": [event.event for event in trace_sink.events],
        "category": diagnosis.category if diagnosis else None,
        "evidence_status": diagnosis.evidence_status if diagnosis else None,
        "handoff": bool(diagnosis and diagnosis.handoff),
        "pending_tool_name": result.pending_tool_call.name if result.pending_tool_call else None,
    }
    checks = {
        "tool_names": "tool_names" not in expected or observed["tool_names"] == expected["tool_names"],
        "category": "category" not in expected or observed["category"] == expected["category"],
        "evidence_status": "evidence_status" not in expected or observed["evidence_status"] == expected["evidence_status"],
        "handoff": "handoff" not in expected or observed["handoff"] == expected["handoff"],
        "pending_tool_name": "pending_tool_name" not in expected or observed["pending_tool_name"] == expected["pending_tool_name"],
        "trace_events_include": set(expected.get("trace_events_include", [])) <= set(observed["trace_events"]),
        "answer_contains": all(term in result.answer for term in expected.get("answer_contains", [])),
    }
    return {
        "id": case_id,
        "passed": all(checks.values()),
        "checks": checks,
        "observed": observed,
    }


def _responses(value: Any, case_id: str) -> list[LLMResponse | Exception]:
    if not isinstance(value, list) or not value:
        raise DiagnosisEvaluationError(f"案例 {case_id} 必须提供非空 model_responses。")
    result: list[LLMResponse | Exception] = []
    for item in value:
        if not isinstance(item, dict):
            raise DiagnosisEvaluationError(f"案例 {case_id} 的模型响应格式错误。")
        if item.get("raise_error"):
            result.append(RuntimeError(str(item["raise_error"])))
            continue
        result.append(LLMResponse(content=item.get("content"), tool_calls=item.get("tool_calls")))
    return result


def _tool_plan(value: Any, case_id: str) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        raise DiagnosisEvaluationError(f"案例 {case_id} 的 tool_results 必须是对象。")
    result: dict[str, list[dict[str, Any]]] = {}
    for name, raw in value.items():
        items = raw if isinstance(raw, list) else [raw]
        if not items or not all(isinstance(item, dict) for item in items):
            raise DiagnosisEvaluationError(f"案例 {case_id} 的工具结果格式错误。")
        result[name] = copy.deepcopy(items)
    return result


def _required_text(case: dict[str, Any], key: str) -> str:
    value = case.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DiagnosisEvaluationError(f"案例缺少非空 {key}。")
    return value.strip()
