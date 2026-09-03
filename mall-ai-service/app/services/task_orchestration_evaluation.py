"""Synthetic, side-effect-free evaluation for task-aware turn orchestration.

The customer path never imports this module.  ``contract_mock`` executes the
real task-state runtime with declared synthetic TurnPlans; ``live_model_synthetic``
calls only the bounded P0 model with versioned synthetic messages and safe task
summaries.  Neither mode connects to Java, Redis production state, RAG, or a
customer conversation, and neither mode can perform a business write.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.schemas.after_sales_application import PendingAfterSalesProposal
from app.schemas.task_orchestration import TurnPlan
from app.schemas.tool import ToolCall
from app.services.after_sales_application_state import owner_fingerprint, session_fingerprint
from app.services.conversation_state import (
    get_conversation_state,
    reset_conversation_state_for_tests,
    set_conversation_manager_for_tests,
)
from app.services.intent_service import IntentServiceError, detect_intent
from app.services.task_orchestration_service import TaskOrchestrationService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE_PATH = PROJECT_ROOT / "evals" / "task_orchestration_cases.v1.json"
_EVALUATION_AUTHORIZATION = "Bearer synthetic-task-orchestration-evaluation"
_EVALUATION_MEMBER_ID = 1


@dataclass(frozen=True)
class TaskOrchestrationEvalCaseResult:
    case_id: str
    status: Literal["PASSED", "FAILED", "ENVIRONMENT_BLOCKED"]
    violations: tuple[str, ...] = ()
    elapsed_ms: int = 0


@dataclass(frozen=True)
class TaskOrchestrationEvalReport:
    suite_version: str
    mode: Literal["contract_mock", "live_model_synthetic"]
    total: int
    passed: int
    failed: int
    environment_blocked: int
    total_elapsed_ms: int
    p95_elapsed_ms: int
    cases: tuple[TaskOrchestrationEvalCaseResult, ...]


def run_task_orchestration_evaluation(
    *,
    mode: Literal["contract_mock", "live_model_synthetic"],
    suite_path: Path = DEFAULT_SUITE_PATH,
    max_total_seconds: float = 180.0,
) -> TaskOrchestrationEvalReport:
    """Run a versioned synthetic suite without touching business services."""

    suite = _load_suite(suite_path)
    raw_cases = suite["contractCases" if mode == "contract_mock" else "liveModelCases"]
    started = time.monotonic()
    results: list[TaskOrchestrationEvalCaseResult] = []

    for raw_case in raw_cases:
        if time.monotonic() - started > max_total_seconds:
            results.append(
                TaskOrchestrationEvalCaseResult(
                    case_id=_case_id(raw_case),
                    status="ENVIRONMENT_BLOCKED",
                    violations=("evaluation_budget_exhausted",),
                )
            )
            continue
        if mode == "contract_mock":
            results.append(_run_contract_case(raw_case))
        else:
            results.append(_run_live_model_case(raw_case))

    elapsed_values = [item.elapsed_ms for item in results if item.elapsed_ms >= 0]
    return TaskOrchestrationEvalReport(
        suite_version=_required_text(suite, "suiteVersion"),
        mode=mode,
        total=len(results),
        passed=sum(item.status == "PASSED" for item in results),
        failed=sum(item.status == "FAILED" for item in results),
        environment_blocked=sum(item.status == "ENVIRONMENT_BLOCKED" for item in results),
        total_elapsed_ms=_elapsed_ms(started),
        p95_elapsed_ms=_p95(elapsed_values),
        cases=tuple(results),
    )


def _run_contract_case(raw_case: dict[str, Any]) -> TaskOrchestrationEvalCaseResult:
    started = time.monotonic()
    case_id = _case_id(raw_case)
    reset_conversation_state_for_tests()
    try:
        runtime = TaskOrchestrationService()
        session_id = f"task-eval-{case_id}"
        _prime_contract_state(runtime, session_id, _required_text(raw_case, "initialState"))
        plan = TurnPlan.model_validate(raw_case["turnPlan"], strict=True)
        decision = runtime.prepare_turn(
            session_id=session_id,
            authorization=_EVALUATION_AUTHORIZATION,
            member_id=_EVALUATION_MEMBER_ID,
            plan=plan,
        )
        state = get_conversation_state(session_id)
        expected = _required_mapping(raw_case, "expected")
        violations = _contract_violations(decision.mode, state, expected)
        return TaskOrchestrationEvalCaseResult(
            case_id=case_id,
            status="PASSED" if not violations else "FAILED",
            violations=tuple(violations),
            elapsed_ms=_elapsed_ms(started),
        )
    except (KeyError, TypeError, ValueError):
        return TaskOrchestrationEvalCaseResult(
            case_id=case_id,
            status="FAILED",
            violations=("invalid_eval_case",),
            elapsed_ms=_elapsed_ms(started),
        )
    finally:
        # Restore the normal configured store; the synthetic in-memory state
        # has never reached Redis or any customer session.
        set_conversation_manager_for_tests(None)


def _run_live_model_case(raw_case: dict[str, Any]) -> TaskOrchestrationEvalCaseResult:
    """Measure P0 semantics only; it deliberately does not execute a route."""

    started = time.monotonic()
    case_id = _case_id(raw_case)
    try:
        context = raw_case.get("safeContext")
        context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":")) if context else ""
        plan = detect_intent(_required_text(raw_case, "syntheticInput"), context_json)
        expected = _required_mapping(raw_case, "expectedPlan")
        violations = _plan_violations(plan, expected)
        return TaskOrchestrationEvalCaseResult(
            case_id=case_id,
            status="PASSED" if not violations else "FAILED",
            violations=tuple(violations),
            elapsed_ms=_elapsed_ms(started),
        )
    except IntentServiceError:
        # This covers provider/network unavailability and a model JSON contract
        # failure.  It is never counted as a pass and does not run a fallback.
        return TaskOrchestrationEvalCaseResult(
            case_id=case_id,
            status="ENVIRONMENT_BLOCKED",
            violations=("p0_unavailable_or_contract_error",),
            elapsed_ms=_elapsed_ms(started),
        )
    except (KeyError, TypeError, ValueError):
        return TaskOrchestrationEvalCaseResult(
            case_id=case_id,
            status="FAILED",
            violations=("invalid_eval_case",),
            elapsed_ms=_elapsed_ms(started),
        )


def _prime_contract_state(
    runtime: TaskOrchestrationService,
    session_id: str,
    initial_state: str,
) -> None:
    if initial_state == "none":
        return
    if initial_state in {
        "active_order_waiting",
        "paused_order_waiting",
        "active_and_paused",
    }:
        _start_waiting_order_task(runtime, session_id)
    if initial_state == "paused_order_waiting":
        runtime.prepare_turn(
            session_id=session_id,
            authorization=_EVALUATION_AUTHORIZATION,
            member_id=_EVALUATION_MEMBER_ID,
            plan=_plan("after_sales_policy", "rag", "temporary_detour"),
        )
        return
    if initial_state == "active_and_paused":
        runtime.prepare_turn(
            session_id=session_id,
            authorization=_EVALUATION_AUTHORIZATION,
            member_id=_EVALUATION_MEMBER_ID,
            plan=_plan("after_sales_policy", "rag", "temporary_detour"),
        )
        runtime.prepare_turn(
            session_id=session_id,
            authorization=_EVALUATION_AUTHORIZATION,
            member_id=_EVALUATION_MEMBER_ID,
            plan=_plan(
                "apply_after_sales",
                "after_sales_flow",
                "start_new_task",
                task_kind="after_sales_draft",
            ),
        )
        return
    if initial_state == "proposal_gate":
        _save_synthetic_proposal(session_id)
        return
    if initial_state not in {"active_order_waiting", "none"}:
        raise ValueError("unknown synthetic task-evaluation state")


def _start_waiting_order_task(runtime: TaskOrchestrationService, session_id: str) -> None:
    runtime.record_waiting_diagnosis(
        session_id=session_id,
        authorization=_EVALUATION_AUTHORIZATION,
        member_id=_EVALUATION_MEMBER_ID,
        pending_tool_call=ToolCall(name="order_service", arguments={}),
        answer="synthetic waiting answer",
    )


def _save_synthetic_proposal(session_id: str) -> None:
    from app.services.after_sales_application_state import save_pending_after_sales_proposal

    now = time.time()
    save_pending_after_sales_proposal(
        session_id,
        PendingAfterSalesProposal(
            proposal_id="e" * 32,
            application_type="return_refund",
            order_sn="SYNTHETIC-ORDER-REFERENCE",
            order_item_id=1,
            product_name="合成商品",
            product_attr="合成规格",
            reason="合成原因",
            description="合成说明",
            owner_fingerprint=owner_fingerprint(
                _EVALUATION_AUTHORIZATION, _EVALUATION_MEMBER_ID
            ),
            session_fingerprint=session_fingerprint(session_id),
            content_hash="f" * 64,
            expires_at=now + 600,
        ),
    )


def _plan(
    intent: str,
    route: str,
    relation: str,
    *,
    task_kind: str | None = None,
    confirmation: str = "none",
) -> TurnPlan:
    rationale = {
        "continue_active": "active_task_match",
        "temporary_detour": "temporary_detour",
        "resume_paused": "paused_task_match",
        "start_new_task": "new_long_running_goal",
        "standalone_answer": "standalone_question",
        "discard_active": "explicit_task_abandonment",
        "discard_paused": "explicit_task_abandonment",
        "resolve_task_conflict": "task_conflict",
    }[relation]
    return TurnPlan.model_validate(
        {
            "business_intent": intent,
            "task_relation": relation,
            "route": route,
            "task_kind": task_kind,
            "confirmation_intent": confirmation,
            "rationale_code": rationale,
            "need_tool": route == "agent",
            "tool_call": {"name": "analysis_agent", "arguments": {}}
            if route == "agent"
            else None,
            "reply": None,
            "chat_scope": None,
        },
        strict=True,
    )


def _contract_violations(mode: str, state: Any, expected: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if mode != expected.get("mode"):
        violations.append("unexpected_transition_mode")
    if _kind_or_none(state.active_task) != expected.get("activeTaskKind"):
        violations.append("active_task_mismatch")
    if _kind_or_none(state.paused_task) != expected.get("pausedTaskKind"):
        violations.append("paused_task_mismatch")
    gate_kind = state.transaction_gate.kind if state.transaction_gate is not None else None
    if gate_kind != expected.get("transactionGateKind"):
        violations.append("transaction_gate_mismatch")
    if bool(state.pending_tool_call) != bool(expected.get("legacyPendingToolCall", False)):
        violations.append("legacy_pending_tool_mismatch")
    return violations


def _plan_violations(plan: TurnPlan, expected: dict[str, Any]) -> list[str]:
    actual = {
        "businessIntent": plan.business_intent,
        "taskRelation": plan.task_relation,
        "route": plan.route,
        "taskKind": plan.task_kind,
        "confirmationIntent": plan.confirmation_intent,
    }
    violations: list[str] = []
    for key, expected_value in expected.items():
        if key.endswith("AnyOf"):
            actual_key = key[: -len("AnyOf")]
            allowed = expected_value if isinstance(expected_value, list) else []
            if actual.get(actual_key) not in allowed:
                violations.append(f"{actual_key}_mismatch")
            continue
        if actual.get(key) != expected_value:
            violations.append(f"{key}_mismatch")
    return violations


def _load_suite(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("contractCases"), list) or not isinstance(value.get("liveModelCases"), list):
        raise ValueError("task orchestration evaluation suite is malformed")
    return value


def _case_id(raw_case: dict[str, Any]) -> str:
    return _required_text(raw_case, "caseId")


def _required_text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"missing {key}")
    return item


def _required_mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"missing {key}")
    return item


def _kind_or_none(task: Any) -> str | None:
    return task.kind if task is not None else None


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, (len(ordered) * 95 + 99) // 100 - 1)
    return ordered[index]
