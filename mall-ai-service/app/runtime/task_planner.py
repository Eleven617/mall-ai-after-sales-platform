"""Plan/version helpers for the generic Task Runtime."""
from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import uuid4

from app.schemas.agent_task import AgentTask, ContextPack, TaskPlan, TaskPlanNode
from app.runtime.providers import RuntimeModelContext
from app.skills.catalog import SkillDefinition


_LONG_NUMBER = re.compile(r"(?<!\d)\d{6,}(?!\d)")
_TOKEN_PATTERN = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:authorization|token|api[_-]?key|password)\s*[=:]\s*\S+)"
)


def normalize_goal(goal: str) -> tuple[str, str]:
    """Return a safe display summary and a one-way digest of the transient goal."""

    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("任务目标不能为空")
    normalized = " ".join(goal.strip().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    safe = _TOKEN_PATTERN.sub("[已隐藏凭证]", normalized)
    safe = _LONG_NUMBER.sub("[业务标识]", safe)
    safe = safe[:240]
    if not safe:
        raise ValueError("任务目标无法形成安全摘要")
    return safe, digest


def new_task_id() -> str:
    return f"task-{uuid4().hex[:16]}"


def new_plan_id() -> str:
    return f"plan-{uuid4().hex[:16]}"


def new_node_id() -> str:
    return f"node-{uuid4().hex[:16]}"


def new_artifact_id() -> str:
    return f"artifact-{uuid4().hex[:16]}"


def new_context_id() -> str:
    return f"context-{uuid4().hex[:16]}"


def new_proposal_id() -> str:
    return f"proposal-{uuid4().hex[:16]}"


def new_arguments_ref() -> str:
    return f"args-{uuid4().hex[:16]}"


def build_initial_plan(task: AgentTask) -> TaskPlan:
    return TaskPlan(
        plan_id=new_plan_id(),
        task_id=task.task_id,
        version=1,
        objective=task.normalized_goal,
        assumptions=[],
        open_questions=[],
        nodes=[
            TaskPlanNode(
                node_id=new_node_id(),
                goal="理解目标并发现当前任务所需的商城 Skill",
                required_skills=["discover_skills"],
                status="pending",
            )
        ],
        created_by="commerce_executor",
    )


def build_model_context(
    task: AgentTask,
    plan: TaskPlan | None,
    artifacts: list[str],
    skills: list[SkillDefinition],
    transient_input: str = "",
    context_pack: ContextPack | None = None,
) -> RuntimeModelContext:
    plan_summary = "无计划"
    open_questions: list[str] = []
    if plan is not None:
        plan_summary = "；".join(
            f"{node.goal}({node.status})" for node in plan.nodes[:8]
        )[:640]
        open_questions = list(plan.open_questions[:8])
    return RuntimeModelContext(
        task_ref=task.task_ref,
        transient_input=transient_input[:2000],
        goal=task.normalized_goal,
        task_status=task.status,
        plan_version=task.plan_version,
        plan_summary=plan_summary,
        open_questions=open_questions,
        artifacts=artifacts[:12],
        context_pack_version=context_pack.version if context_pack is not None else None,
        context_verified_facts=(context_pack.verified_facts[:12] if context_pack is not None else []),
        context_unresolved_assumptions=(
            context_pack.unresolved_assumptions[:8] if context_pack is not None else []
        ),
        memory_hints=context_pack.memory_hints[:6] if context_pack is not None else [],
        context_artifact_refs=(context_pack.source_artifact_refs[:16] if context_pack is not None else []),
        available_skills=[
            {
                "skillId": skill.skill_id,
                "version": skill.semantic_version,
                "domain": skill.domain,
                "description": skill.description,
                "actionMode": skill.action_mode,
                "estimatedLatencyMs": skill.estimated_latency_ms,
            }
            for skill in skills[:8]
        ],
        action_pending=task.pending_action_ref is not None,
        model_calls_remaining=max(0, task.execution_budget.max_model_calls - task.model_calls),
        tool_calls_remaining=max(0, task.execution_budget.max_tool_calls - task.tool_calls),
    )
