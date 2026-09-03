"""Generic, bounded E-Commerce Task Runtime.

This module is intentionally a runtime, not a second business workflow.  It
coordinates model decisions, Skill discovery, safe observations, Context Pack
updates, optional Critic calls and transaction gates.  Java/RAG access is
delegated to ``SkillGateway``; the runtime never writes the mall database.
"""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from app.config import settings
from app.schemas.agent_task import (
    ActionProposal,
    AgentTask,
    AgentTaskActionView,
    AgentTaskArtifactView,
    AgentTaskContextView,
    AgentTaskContinueRequest,
    AgentTaskEvent,
    AgentTaskPlanNodeView,
    AgentTaskPublicView,
    AgentTaskStatus,
    ContextPack,
    ExecutorDecision,
    TaskExecutionBudget,
    TaskArtifact,
    TaskPlan,
)
from app.runtime.context_curator import ContextCurator
from app.runtime.providers import (
    DeepSeekRuntimeProvider,
    RuntimeModelError,
    RuntimeModelProvider,
    UnavailableRuntimeProvider,
)
from app.runtime.resolution_critic import ResolutionCritic
from app.runtime.task_memory import TaskMemory
from app.runtime.task_planner import (
    build_initial_plan,
    build_model_context,
    new_artifact_id,
    new_arguments_ref,
    new_proposal_id,
    new_task_id,
    normalize_goal,
)
from app.runtime.task_store import (
    TaskRecordBundle,
    TaskStore,
    TaskStoreAccessDenied,
    TaskStoreError,
    TaskStoreUnavailable,
    assert_safe_action_arguments,
    get_task_store,
    owner_ref_for_member,
    session_ref_for_session,
)
from app.skills.catalog import SkillDefinition, discover_skills, get_skill
from app.skills.commerce_gateway import (
    SafeCommerceSkillGateway,
    SkillGateway,
    SkillGatewayError,
    SkillObservation,
)
from app.services.trace_service import record_trace


class TaskRuntimeError(RuntimeError):
    def __init__(self, message: str, *, code: str = "runtime_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class TaskRuntimeResult:
    view: AgentTaskPublicView
    events: list[AgentTaskEvent]


class TaskRuntime:
    """A single owner-scoped runtime with explicit model/tool budgets."""

    def __init__(
        self,
        *,
        store: TaskStore | None = None,
        provider: RuntimeModelProvider | None = None,
        gateway: SkillGateway | None = None,
        memory: TaskMemory | None = None,
        now_fn=time.time,
    ) -> None:
        self._store = store or get_task_store()
        if provider is None:
            provider = DeepSeekRuntimeProvider() if settings.deepseek_api_key else UnavailableRuntimeProvider()
        self._provider = provider
        self._gateway = gateway or SafeCommerceSkillGateway()
        self._memory = memory or TaskMemory()
        self._now = now_fn
        self._curator = ContextCurator(self._provider)
        self._critic = ResolutionCritic(self._provider)

    def create_task(
        self,
        *,
        session_id: str,
        goal: str,
        member_id: int | None,
        authorization: str | None,
        success_criteria: list[str] | None = None,
        execution_budget: TaskExecutionBudget | None = None,
    ) -> TaskRuntimeResult:
        owner_ref, session_ref = self._require_owner(session_id, member_id, authorization)
        normalized_goal, goal_digest = normalize_goal(goal)
        now = self._now()
        task_id = new_task_id()
        task = AgentTask(
            task_id=task_id,
            task_ref=f"taskref-{task_id.removeprefix('task-')}",
            owner_ref=owner_ref,
            session_ref=session_ref,
            goal_digest=goal_digest,
            normalized_goal=normalized_goal,
            success_criteria=list(success_criteria or [])[:6],
            status="planning",
            plan_version=1,
            execution_budget=(
                execution_budget.model_copy(deep=True)
                if execution_budget is not None
                else TaskExecutionBudget()
            ),
            expires_at=now + settings.agent_task_ttl_seconds,
        )
        bundle = TaskRecordBundle(task=task)
        plan = build_initial_plan(task)
        bundle.plans.append(plan)
        task.plan_version = plan.version
        self._append_event(bundle, "task_created", "已创建电商任务，正在形成可执行计划。")
        self._save(bundle)
        result = self._run_turn(
            bundle,
            transient_input=goal,
            authorization=authorization,
            member_id=member_id,
        )
        return result

    def continue_task(
        self,
        *,
        task_ref: str,
        message: str,
        member_id: int | None,
        authorization: str | None,
    ) -> TaskRuntimeResult:
        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        try:
            bundle = self._store.load_owned(task_ref, owner_ref)
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc
        if not isinstance(message, str) or not message.strip() or len(message) > 2000:
            raise TaskRuntimeError("继续任务的消息不合法。", code="invalid_message")
        if bundle.task.status in {"completed", "cancelled"}:
            raise TaskRuntimeError("该任务已经结束，不能继续。", code="task_terminal", status_code=409)
        return self._run_turn(bundle, transient_input=message, authorization=authorization, member_id=member_id)

    def get_task(self, *, task_ref: str, member_id: int | None, authorization: str | None) -> AgentTaskPublicView:
        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        try:
            bundle = self._store.load_owned(task_ref, owner_ref)
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc
        return self._public_view(bundle)

    def list_tasks(self, *, session_id: str | None, member_id: int | None, authorization: str | None) -> list[AgentTaskPublicView]:
        owner_ref, session_ref = self._require_owner(session_id or "task-session", member_id, authorization, allow_session_placeholder=True)
        bundles = self._store.list_owned(owner_ref, session_ref if session_id else None)
        return [self._public_view(bundle) for bundle in bundles]

    def list_events(self, *, task_ref: str, member_id: int | None, authorization: str | None) -> list[AgentTaskEvent]:
        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        try:
            return self._store.load_owned(task_ref, owner_ref).events
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc

    def confirm_action(
        self,
        *,
        task_ref: str,
        confirmation: str,
        member_id: int | None,
        authorization: str | None,
    ) -> TaskRuntimeResult:
        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        try:
            bundle = self._store.load_owned(task_ref, owner_ref)
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc
        proposal = bundle.action_proposal
        if proposal is None or proposal.confirmation_status != "awaiting_confirmation":
            raise TaskRuntimeError("当前任务没有有效的待确认行动。", code="action_gate_missing", status_code=409)
        if proposal.expires_at <= self._now():
            proposal.confirmation_status = "expired"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("action_expired")
            self._append_event(bundle, "task_blocked", "待确认行动已过期，未执行任何业务写入。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if confirmation == "withdraw":
            proposal.confirmation_status = "withdrawn"
            bundle.task.pending_action_ref = None
            bundle.task.status = "executing"
            self._append_event(bundle, "task_completed", "已撤回待确认行动，未执行业务写入。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if confirmation != "confirm":
            raise TaskRuntimeError("确认状态不合法。", code="invalid_confirmation")
        skill = get_skill(proposal.action_skill)
        if (
            skill is None
            or skill.action_mode not in {"draft", "commit", "async_task"}
            or not skill.requires_confirmation
        ):
            raise TaskRuntimeError("待确认行动不在受控提交白名单中。", code="action_skill_denied", status_code=403)
        arguments = bundle.action_arguments.get(proposal.arguments_ref)
        if arguments is None:
            raise TaskRuntimeError("待确认行动参数已失效，请重新生成方案。", code="action_arguments_missing", status_code=409)
        proposal.confirmation_status = "confirmed"
        bundle.task.status = "committing"
        self._append_event(bundle, "action_committed", "已收到客户确认，正在由受控领域服务复核执行。")
        self._save(bundle)
        try:
            observation = self._gateway.commit(
                proposal.action_skill,
                arguments,
                authorization=authorization,
                member_id=member_id,
                task_ref=bundle.task.task_ref,
            )
        except Exception:
            observation = SkillObservation(
                status="unavailable",
                artifact_kind="action_result",
                summary="提交结果暂时无法确认，未在 AI 层重放业务动作。",
                reference=_safe_reference("action-unknown", bundle.task.task_ref),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "commit_result_unknown"},
            )
        self._record_observation(bundle, proposal.action_skill, observation)
        if observation.status == "succeeded":
            proposal.confirmation_status = "committed"
            bundle.task.status = "executing"
            bundle.task.pending_action_ref = None
            self._append_event(bundle, "action_committed", "Java 已返回受控行动结果，任务将继续观察后续状态。")
        elif observation.status == "blocked":
            proposal.confirmation_status = "blocked"
            bundle.task.status = "blocked"
            bundle.task.pending_action_ref = None
            failure_code = observation.safe_facts.get("failure_code", "action_blocked")
            bundle.task.limitation_codes.append(failure_code)
            self._append_event(bundle, "task_blocked", "行动未通过受控前置条件，未执行任何业务写入。")
        else:
            proposal.confirmation_status = "unknown"
            bundle.task.status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.limitation_codes.append("commit_result_unknown")
            self._append_event(bundle, "task_blocked", "提交结果无法确认，已停止重试；请稍后查询业务状态。")
        self._save(bundle)
        return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))

    def _run_turn(
        self,
        bundle: TaskRecordBundle,
        *,
        transient_input: str,
        authorization: str | None,
        member_id: int | None,
    ) -> TaskRuntimeResult:
        task = bundle.task
        started = self._now()
        if task.expires_at <= started:
            task.status = "blocked"
            task.limitation_codes.append("task_expired")
            self._append_event(bundle, "task_blocked", "任务已过期，未继续调用 Skill。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        task.status = "executing"
        self._save(bundle)
        while True:
            if self._now() - started > task.execution_budget.max_wall_clock_seconds:
                self._block(bundle, "wall_clock_budget_exhausted", "任务达到时间预算，已安全停止。")
                break
            if task.model_calls >= task.execution_budget.max_model_calls:
                self._block(bundle, "model_call_budget_exhausted", "任务达到模型调用预算，已安全停止。")
                break
            plan = bundle.latest_plan()
            discovered = self._discover_for_turn(task, transient_input, bundle)
            context = build_model_context(
                task,
                plan,
                [artifact.summary for artifact in bundle.artifacts[-12:]],
                discovered,
                transient_input=transient_input,
                context_pack=bundle.latest_context_pack(),
            )
            try:
                decision = self._provider.decide(context)
                task.model_calls += 1
            except RuntimeModelError as exc:
                task.model_calls += 1
                self._block(bundle, f"model_{exc.category}", "任务模型暂时不可用，任务已安全暂停；未调用业务 Skill。")
                record_trace("task_runtime", "model_unavailable", task.task_ref, role=exc.role, result_kind="blocked", error_category=exc.category)
                break
            except (ValidationError, TypeError, ValueError) as exc:
                task.invalid_decisions += 1
                self._block(bundle, "invalid_executor_decision", "任务模型返回的决策不符合契约，未执行任何 Skill。")
                record_trace("task_runtime", "invalid_decision", task.task_ref, result_kind="blocked", contract_violation="invalid_executor_decision")
                break
            try:
                self._validate_decision(decision, task, discovered, bundle)
            except TaskRuntimeError as exc:
                task.invalid_decisions += 1
                self._block(bundle, exc.code, "任务决策未通过服务端能力校验，未执行任何业务动作。")
                record_trace("task_runtime", "decision_rejected", task.task_ref, result_kind="blocked", contract_violation=exc.code)
                break
            if decision.decision == "discover_skills":
                self._append_event(bundle, "plan_updated", "已发现与当前目标相关的受控 Skill。")
                self._save(bundle)
                transient_input = "继续根据已发现的 Skill 形成下一步行动"
                continue
            if decision.decision == "call_skill":
                self._execute_skill_calls(bundle, decision, authorization, member_id)
                self._refresh_context(bundle, discovered)
                if bundle.artifacts and self._critic.should_trigger(
                    artifacts=bundle.artifacts,
                    skill_calls=task.tool_calls,
                    has_action=False,
                    has_conflict=self._has_conflict(bundle),
                ):
                    self._maybe_critic(bundle)
                self._save(bundle)
                transient_input = "观察刚刚获得的事实并决定是否需要继续、重规划或结束"
                continue
            if decision.decision == "spawn_subtask":
                self._execute_spawn_subtask(bundle, decision, authorization, member_id)
                self._save(bundle)
                transient_input = "观察子任务状态并决定下一步"
                continue
            if decision.decision == "revise_plan":
                self._revise_plan(bundle, decision)
                self._save(bundle)
                transient_input = "根据新计划继续执行"
                continue
            if decision.decision == "ask_user":
                task.status = "waiting_for_user"
                task.waiting_question = decision.user_question
                self._append_event(bundle, "waiting_for_user", decision.user_question or "请补充必要信息后继续。")
                self._save(bundle)
                break
            if decision.decision == "propose_action":
                self._propose_action(bundle, decision)
                self._save(bundle)
                break
            if decision.decision == "finish":
                task.status = "completed"
                task.final_outcome = decision.reason_summary
                task.waiting_question = None
                self._append_event(bundle, "task_completed", decision.reason_summary)
                # Persist an owner-scoped episodic projection with the task
                # bundle.  The in-process TaskMemory below is only a fast
                # cache; this durable copy is what lets a restarted Runtime
                # discover the safe summary without retaining raw messages.
                if decision.reason_summary not in bundle.memory_hints:
                    bundle.memory_hints.append(decision.reason_summary)
                    bundle.memory_hints = bundle.memory_hints[-32:]
                self._memory.remember(
                    owner_ref=task.owner_ref,
                    task_ref=task.task_ref,
                    summary=decision.reason_summary,
                    reference=_safe_reference("memory", task.task_ref),
                    ttl_seconds=settings.agent_task_ttl_seconds,
                )
                self._save(bundle)
                break
        record_trace(
            "task_runtime",
            "turn_finished",
            task.task_ref,
            result_kind="success" if task.status == "completed" else "blocked" if task.status == "blocked" else "pending",
            duration_ms=max(0, round((self._now() - started) * 1000)),
            tool_call_count=task.tool_calls,
            profile_version="v3_0",
        )
        return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))

    def _require_owner(
        self,
        session_id: str,
        member_id: int | None,
        authorization: str | None,
        *,
        allow_session_placeholder: bool = False,
    ) -> tuple[str, str]:
        if not authorization or not authorization.startswith("Bearer "):
            raise TaskRuntimeError("请先登录后再使用任务运行时。", code="unauthenticated", status_code=401)
        if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
            raise TaskRuntimeError("当前账号不能使用任务运行时。", code="scope_denied", status_code=403)
        if not allow_session_placeholder and (not isinstance(session_id, str) or not session_id.strip()):
            raise TaskRuntimeError("会话标识不合法。", code="invalid_session")
        return owner_ref_for_member(member_id), session_ref_for_session(session_id)

    def _discover_for_turn(self, task: AgentTask, transient_input: str, bundle: TaskRecordBundle) -> list[SkillDefinition]:
        query = f"{task.normalized_goal} {transient_input}"
        selected = discover_skills(query, limit=8)
        known = {skill.skill_id for skill in selected}
        for artifact in bundle.artifacts[-8:]:
            if artifact.source_skill and artifact.source_skill not in known:
                skill = get_skill(artifact.source_skill)
                if skill is not None:
                    selected.append(skill)
                    known.add(skill.skill_id)
        return selected[:8]

    def _validate_decision(
        self,
        decision: ExecutorDecision,
        task: AgentTask,
        discovered: list[SkillDefinition],
        bundle: TaskRecordBundle,
    ) -> None:
        discovered_ids = {skill.skill_id for skill in discovered}
        if decision.decision == "call_skill":
            if len(decision.skill_calls) > task.execution_budget.max_parallel_reads:
                raise TaskRuntimeError("一次调用的 Skill 数量超过并行预算。", code="parallel_budget_exceeded")
            if task.tool_calls + len(decision.skill_calls) > task.execution_budget.max_tool_calls:
                raise TaskRuntimeError("任务达到 Skill 调用预算。", code="tool_call_budget_exhausted")
            for call in decision.skill_calls:
                skill = get_skill(call.skill_id)
                if skill is None or call.skill_id not in discovered_ids:
                    raise TaskRuntimeError("调用了未发现或未注册的 Skill。", code="unknown_skill")
                if skill.action_mode != "read":
                    raise TaskRuntimeError(
                        "有副作用的 Skill 必须先形成行动提案并等待客户确认。",
                        code="action_requires_proposal",
                    )
                if self._skill_call_count(bundle, call.skill_id) >= skill.max_calls_per_task:
                    raise TaskRuntimeError("当前 Skill 已达到该任务的调用上限。", code="skill_call_budget_exhausted")
                self._validate_skill_arguments(call.skill_id, call.arguments)
        if decision.decision == "spawn_subtask":
            skill = get_skill("spawn_subtask")
            if skill is None or skill.skill_id not in discovered_ids:
                raise TaskRuntimeError("子任务能力必须先经当前任务发现。", code="undiscovered_subtask_skill")
            if self._skill_call_count(bundle, skill.skill_id) >= skill.max_calls_per_task:
                raise TaskRuntimeError("当前任务已达到子任务上限。", code="skill_call_budget_exhausted")
            if task.tool_calls >= task.execution_budget.max_tool_calls:
                raise TaskRuntimeError("任务达到 Skill 调用预算。", code="tool_call_budget_exhausted")
        if decision.decision == "propose_action":
            if decision.action_skill is None:
                raise TaskRuntimeError("行动提案缺少 Skill。", code="action_skill_missing")
            skill = get_skill(decision.action_skill)
            if skill is None or skill.action_mode not in {"draft", "commit", "async_task"}:
                raise TaskRuntimeError("行动 Skill 不在受控范围内。", code="action_skill_denied")
            if skill.skill_id not in discovered_ids:
                raise TaskRuntimeError("行动 Skill 必须先经当前任务发现。", code="undiscovered_action_skill")
            if not skill.requires_confirmation:
                raise TaskRuntimeError("行动 Skill 必须声明客户确认前置条件。", code="confirmation_contract_invalid")
            if not bundle.artifacts:
                raise TaskRuntimeError("没有已核验事实，不能形成业务行动提案。", code="action_without_evidence")
            if self._skill_call_count(bundle, skill.skill_id) >= skill.max_calls_per_task:
                raise TaskRuntimeError("当前行动 Skill 已达到该任务的调用上限。", code="skill_call_budget_exhausted")
            self._validate_skill_arguments(decision.action_skill, decision.action_arguments)
            if skill.action_mode == "commit":
                order_fact_ref = decision.action_arguments.get("orderFactRef")
                verified_order_refs = {
                    artifact.reference
                    for artifact in bundle.artifacts
                    if artifact.kind == "order_fact" and artifact.factuality == "verified" and artifact.expires_at > self._now()
                }
                if not isinstance(order_fact_ref, str) or order_fact_ref not in verified_order_refs:
                    raise TaskRuntimeError("提交行动必须引用当前任务的已核验订单事实。", code="commit_without_verified_order_fact")
        if decision.decision == "revise_plan":
            if task.plan_version >= 99:
                raise TaskRuntimeError("计划版本已达到上限。", code="plan_version_exhausted")
            for node in decision.new_plan_nodes:
                for skill_id in node.required_skills:
                    if skill_id != "discover_skills" and get_skill(skill_id) is None:
                        raise TaskRuntimeError("重规划引用了未知 Skill。", code="unknown_skill")
        if decision.decision == "finish" and not decision.reason_summary:
            raise TaskRuntimeError("完成决策缺少用户可见摘要。", code="finish_summary_missing")

    def _validate_skill_arguments(self, skill_id: str, arguments: Mapping[str, Any]) -> None:
        if not isinstance(arguments, Mapping) or len(arguments) > 8:
            raise TaskRuntimeError("Skill 参数不合法。", code="invalid_skill_arguments")
        allowed: dict[str, set[str]] = {
            "search_catalog": {"query", "category"},
            "compare_skus": {"sku_refs", "criteria"},
            "read_order": {"order_sn", "orderRef"},
            "read_logistics": {"order_sn", "orderRef"},
            "read_inventory": {"sku_id", "skuRef"},
            "retrieve_policy": {"query", "policy_version"},
            "list_service_applications": set(),
            "build_service_resolution": {"factRefs", "facts"},
            "create_after_sales_draft": {"proposalRef"},
            "amend_after_sales_draft": {"proposalRef"},
            # The Runtime owns the idempotency key.  It must never be accepted
            # from an Executor decision, even when the value has a valid shape.
            "commit_after_sales_action": {"actionRef", "proposalRef", "orderFactRef", "applicationType"},
            "open_human_case": {"artifactRefs", "reasonCode"},
            "request_customer_evidence": {"questionCode"},
            "schedule_follow_up": {"taskRef", "delayCode"},
            "search_task_memory": {"query"},
            "spawn_subtask": {"goalCode", "requiredSkills"},
        }
        keys = set(arguments.keys())
        if keys - allowed.get(skill_id, set()):
            raise TaskRuntimeError("Skill 参数包含未知字段。", code="unknown_skill_argument")
        for key, value in arguments.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise TaskRuntimeError("Skill 参数名不合法。", code="invalid_skill_arguments")
            if isinstance(value, str):
                if len(value) > 500 or any(marker in value.lower() for marker in ("bearer ", "token=", "password")):
                    raise TaskRuntimeError("Skill 参数包含禁止内容。", code="sensitive_skill_argument")
            elif isinstance(value, list):
                if len(value) > 8:
                    raise TaskRuntimeError("Skill 参数列表过长。", code="invalid_skill_arguments")
            elif value is not None and not isinstance(value, (bool, int, float, dict)):
                raise TaskRuntimeError("Skill 参数类型不支持。", code="invalid_skill_arguments")
        if skill_id == "commit_after_sales_action":
            if arguments.get("applicationType") not in {"cancel_refund", "return_refund", "exchange", "repair"}:
                raise TaskRuntimeError("提交行动必须使用受支持的售后类型。", code="application_type_invalid")

    @staticmethod
    def _skill_call_count(bundle: TaskRecordBundle, skill_id: str) -> int:
        """Count observed calls, not arbitrary model mentions, for one Skill."""

        return sum(artifact.source_skill == skill_id for artifact in bundle.artifacts)

    def _execute_skill_calls(self, bundle: TaskRecordBundle, decision: ExecutorDecision, authorization: str | None, member_id: int | None) -> None:
        """Run independent read Skills concurrently, then persist in call order.

        The Executor has already passed the catalog check that limits this path
        to ``read`` Skills.  No action proposal, confirmation state or task
        store record is mutated in worker threads, so parallel observations
        cannot race a business write or reorder the persisted audit timeline.
        """

        calls = list(decision.skill_calls)
        if len(calls) == 1:
            call = calls[0]
            skill = get_skill(call.skill_id)
            observations = [
                self._invoke_read_skill(
                    skill,
                    call.skill_id,
                    call.arguments,
                    authorization=authorization,
                    member_id=member_id,
                    task_ref=bundle.task.task_ref,
                )
            ]
        else:
            workers = min(len(calls), bundle.task.execution_budget.max_parallel_reads)
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mall-task-read") as executor:
                futures = [
                    executor.submit(
                        self._invoke_read_skill,
                        get_skill(call.skill_id),
                        call.skill_id,
                        call.arguments,
                        authorization=authorization,
                        member_id=member_id,
                        task_ref=bundle.task.task_ref,
                    )
                    for call in calls
                ]
                observations = [future.result() for future in futures]

        for call, observation in zip(calls, observations, strict=True):
            skill = get_skill(call.skill_id)
            if skill is None:  # guarded before execution; keep future changes fail-closed.
                continue
            bundle.task.tool_calls += 1
            self._record_observation(bundle, call.skill_id, observation)
            self._append_event(bundle, "skill_observed", observation.summary)
            record_trace(
                "task_runtime",
                "skill_observed",
                bundle.task.task_ref,
                skill_id=call.skill_id,
                skill_version=skill.semantic_version,
                result_kind=observation.status if observation.status in {"succeeded", "blocked", "unavailable", "failed"} else "failure",
                tool_call_count=bundle.task.tool_calls,
            )

    def _invoke_read_skill(
        self,
        skill: SkillDefinition | None,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        authorization: str | None,
        member_id: int | None,
        task_ref: str,
    ) -> SkillObservation:
        if skill is None:
            return SkillObservation(
                status="blocked",
                artifact_kind="action_result",
                summary="当前 Skill 不在受控能力目录中。",
                reference=_safe_reference("skill", f"unknown:{task_ref}"),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "unknown_skill"},
            )
        if skill_id == "search_task_memory":
            return self._search_task_memory(task_ref, member_id, arguments)
        try:
            return self._gateway.invoke(
                skill_id,
                arguments,
                authorization=authorization,
                member_id=member_id,
                task_ref=task_ref,
            )
        except Exception:
            return SkillObservation(
                status="unavailable",
                artifact_kind="action_result",
                summary="Skill 执行暂时不可用，未形成业务结论。",
                reference=_safe_reference("skill", f"{skill_id}:{task_ref}"),
                source_version=skill.semantic_version,
                factuality="unavailable",
                safe_facts={"failure_code": "skill_execution_error"},
            )

    def _search_task_memory(
        self,
        task_ref: str,
        member_id: int | None,
        arguments: Mapping[str, Any],
    ) -> SkillObservation:
        """Resolve only owner-scoped, safe episodic summaries inside Runtime."""

        query = arguments.get("query", "")
        if not isinstance(query, str):
            return SkillObservation(
                status="blocked",
                artifact_kind="memory_hint",
                summary="任务记忆查询参数不合法，未读取任何历史信息。",
                reference=_safe_reference("memory", task_ref),
                source_version="v1",
                factuality="unavailable",
                safe_facts={"failure_code": "memory_query_invalid"},
            )
        try:
            owner_ref = owner_ref_for_member(member_id or 0)
            # TaskMemory is a short-lived process cache only.  The durable
            # source is the owner-scoped TaskStore: completed-task summaries
            # are persisted with their task bundle, so a fresh Runtime can
            # reuse a safe episodic hint without reviving any raw message or
            # tool payload.
            persisted_hints = [
                hint
                for item in self._store.list_owned(owner_ref)
                for hint in item.memory_hints
                if isinstance(hint, str) and hint.strip()
            ]
            cached_entries = self._memory.search(owner_ref=owner_ref, query=query[:240], limit=4)
        except (ValueError, TaskStoreError):
            persisted_hints = []
            cached_entries = []
        normalized_query = query.lower().strip()
        hints = list(dict.fromkeys(persisted_hints + [entry.summary for entry in cached_entries]))
        if normalized_query:
            matching = [hint for hint in hints if normalized_query in hint.lower()]
            hints = matching or hints
        hints = hints[:4]
        if not hints:
            return SkillObservation(
                status="succeeded",
                artifact_kind="memory_hint",
                summary="当前账号没有可安全复用的历史任务摘要。",
                reference=_safe_reference("memory", f"empty:{task_ref}"),
                source_version="v1",
                factuality="derived",
                safe_facts={"memory_count": "0"},
            )
        return SkillObservation(
            status="succeeded",
            artifact_kind="memory_hint",
            summary=f"已找到当前账号范围内 {len(hints)} 条脱敏历史任务摘要。",
            reference=_safe_reference("memory", f"{task_ref}:{len(hints)}"),
            source_version="v1",
            factuality="derived",
            safe_facts={"memory_count": str(len(hints))},
        )

    def _record_observation(self, bundle: TaskRecordBundle, skill_id: str, observation: SkillObservation) -> TaskArtifact:
        artifact = TaskArtifact(
            artifact_id=new_artifact_id(),
            task_id=bundle.task.task_id,
            kind=observation.artifact_kind,
            source_skill=skill_id,
            source_version=observation.source_version,
            factuality=observation.factuality,
            summary=observation.summary,
            reference=observation.reference,
            expires_at=min(bundle.task.expires_at, self._now() + 3600),
            visibility_scope="owner",
            hash=hashlib.sha256(
                json.dumps(
                    {
                        "kind": observation.artifact_kind,
                        "summary": observation.summary,
                        "reference": observation.reference,
                        "status": observation.status,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        )
        bundle.artifacts.append(artifact)
        bundle.task.artifact_refs.append(artifact.reference)
        if observation.status in {"blocked", "unavailable", "failed"}:
            code = observation.safe_facts.get("failure_code")
            if code and code not in bundle.task.limitation_codes:
                bundle.task.limitation_codes.append(code)
        return artifact

    def _refresh_context(self, bundle: TaskRecordBundle, discovered: list[SkillDefinition]) -> ContextPack | None:
        plan = bundle.latest_plan()
        if plan is None:
            return None
        pack = self._curator.build_pack(
            task=bundle.task,
            plan=plan,
            artifacts=bundle.artifacts[-24:],
            memory_hints=bundle.memory_hints[-8:],
            available_skills=[skill.skill_id for skill in discovered],
        )
        bundle.context_packs.append(pack)
        bundle.task.context_model_calls += 1
        bundle.task.context_pack_ref = pack.pack_id
        bundle.task.working_memory_ref = pack.pack_id
        bundle.memory_hints.extend(pack.memory_hints[-4:])
        return pack

    def _maybe_critic(self, bundle: TaskRecordBundle) -> None:
        plan = bundle.latest_plan()
        if plan is None:
            return
        critique = self._critic.evaluate(task_ref=bundle.task.task_ref, plan=plan, artifacts=bundle.artifacts[-12:])
        if critique is None:
            return
        bundle.task.critic_calls += 1
        if critique.conflicting_artifacts:
            bundle.task.limitation_codes.append("artifact_conflict")
        if critique.unmet_success_criteria:
            bundle.task.limitation_codes.append("success_criteria_unmet")
        if critique.recommended_next_experiment:
            bundle.memory_hints.append(critique.recommended_next_experiment)
        self._append_event(bundle, "plan_updated", "评审发现了方案或事实缺口，后续计划将重新检查。")

    def _execute_spawn_subtask(self, bundle: TaskRecordBundle, decision: ExecutorDecision, authorization: str | None, member_id: int | None) -> None:
        """Create a real owner-scoped child Task instead of faking an async result.

        A child begins in ``waiting_for_async_task``.  It has no inherited raw
        message, credentials or Java fact payload; a later Runtime turn must
        independently discover Skills and obtain fresh facts before it can
        perform work.  This keeps subtask creation useful for planning while
        avoiding an implicit background write or an unbounded worker loop.
        """

        parent = bundle.task
        child_task_id = new_task_id()
        child = AgentTask(
            task_id=child_task_id,
            task_ref=f"taskref-{child_task_id.removeprefix('task-')}",
            owner_ref=parent.owner_ref,
            session_ref=parent.session_ref,
            parent_task_id=parent.task_id,
            goal_digest=hashlib.sha256(
                f"{parent.task_id}:{decision.reason_summary}".encode("utf-8")
            ).hexdigest(),
            normalized_goal=f"子任务：{decision.reason_summary}",
            status="waiting_for_async_task",
            plan_version=1,
            expires_at=parent.expires_at,
        )
        child_bundle = TaskRecordBundle(task=child)
        child_bundle.plans.append(build_initial_plan(child))
        self._append_event(child_bundle, "task_created", "已创建受控子任务，等待上级任务继续安排。")
        self._save(child_bundle)
        observation = SkillObservation(
            status="succeeded",
            artifact_kind="async_task",
            summary="已创建一个受控调查子任务；它尚未执行任何业务动作。",
            reference=_safe_reference("subtask", child.task_ref),
            source_version="v1",
            factuality="derived",
            safe_facts={"subtask_status": "waiting_for_async_task"},
        )
        bundle.task.tool_calls += 1
        self._record_observation(bundle, "spawn_subtask", observation)
        self._append_event(bundle, "skill_observed", observation.summary)
        record_trace(
            "task_runtime",
            "skill_observed",
            parent.task_ref,
            skill_id="spawn_subtask",
            skill_version="v1",
            result_kind="succeeded",
            tool_call_count=bundle.task.tool_calls,
        )

    def _revise_plan(self, bundle: TaskRecordBundle, decision: ExecutorDecision) -> None:
        old = bundle.latest_plan()
        if old is None:
            return
        version = old.version + 1
        nodes = decision.new_plan_nodes[:4]
        if not nodes:
            return
        revised = TaskPlan(
            plan_id=f"plan-{hashlib.sha256(f'{bundle.task.task_ref}:{version}'.encode()).hexdigest()[:16]}",
            task_id=bundle.task.task_id,
            version=version,
            objective=old.objective,
            assumptions=old.assumptions,
            open_questions=old.open_questions,
            nodes=nodes,
            revision_reason=decision.reason_summary,
            created_by="commerce_executor",
        )
        bundle.plans.append(revised)
        bundle.task.plan_version = version
        self._append_event(bundle, "plan_updated", f"计划已修订到第 {version} 版：{decision.reason_summary}")

    def _propose_action(self, bundle: TaskRecordBundle, decision: ExecutorDecision) -> None:
        skill = get_skill(decision.action_skill or "")
        if skill is None:
            raise TaskRuntimeError("行动 Skill 不存在。", code="action_skill_denied")
        # Action arguments are a server-side vault entry. They contain only
        # opaque references, not order numbers, credentials or raw messages.
        action_arguments = dict(decision.action_arguments)
        if skill.action_mode == "commit":
            action_arguments["idempotencyKey"] = hashlib.sha256(
                f"{bundle.task.task_id}:{bundle.task.plan_version}:{json.dumps(action_arguments, ensure_ascii=False, sort_keys=True)}".encode("utf-8")
            ).hexdigest()[:32]
        # The model may never choose an idempotency key.  It is generated only
        # after the action schema/evidence checks and accepted by the vault
        # validator through its explicit internal-only flag.
        assert_safe_action_arguments(
            action_arguments,
            allow_generated_idempotency_key=skill.action_mode == "commit",
        )
        arguments_ref = new_arguments_ref()
        bundle.action_arguments[arguments_ref] = action_arguments
        content_hash = hashlib.sha256(
            json.dumps(action_arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        proposal = ActionProposal(
            proposal_id=new_proposal_id(),
            task_id=bundle.task.task_id,
            action_skill=skill.skill_id,
            arguments_ref=arguments_ref,
            expected_effect=decision.reason_summary,
            evidence_refs=[artifact.reference for artifact in bundle.artifacts[-8:]],
            alternatives=[],
            user_explanation=decision.reason_summary,
            confirmation_status="awaiting_confirmation" if skill.requires_confirmation else "not_required",
            content_hash=content_hash,
            expires_at=min(bundle.task.expires_at, self._now() + 900),
        )
        bundle.action_proposal = proposal
        bundle.task.pending_action_ref = proposal.proposal_id
        if skill.requires_confirmation:
            bundle.task.status = "ready_to_commit"
            self._append_event(bundle, "action_proposed", "已生成待确认行动卡；确认前不会执行业务写入。")
        else:
            bundle.task.status = "executing"
            self._append_event(bundle, "action_proposed", "已生成结构化行动提案。")

    def _has_conflict(self, bundle: TaskRecordBundle) -> bool:
        return len({artifact.reference for artifact in bundle.artifacts[-12:]}) != len(bundle.artifacts[-12:])

    def _append_event(self, bundle: TaskRecordBundle, event_type: str, summary: str) -> None:
        try:
            event = AgentTaskEvent(event_type=event_type, task_ref=bundle.task.task_ref, summary=summary)
        except ValidationError:
            event = AgentTaskEvent(event_type="task_failed", task_ref=bundle.task.task_ref, summary="任务事件无法安全生成。")
        bundle.events.append(event)
        bundle.events = bundle.events[-settings.agent_task_event_limit :]

    def _block(self, bundle: TaskRecordBundle, code: str, summary: str) -> None:
        bundle.task.status = "blocked"
        bundle.task.limitation_codes.append(code)
        bundle.task.limitation_codes = list(dict.fromkeys(bundle.task.limitation_codes))[-8:]
        bundle.task.final_outcome = summary
        self._append_event(bundle, "task_blocked", summary)
        self._save(bundle)

    def _save(self, bundle: TaskRecordBundle) -> None:
        bundle.task.updated_at = self._now()
        try:
            self._store.save(bundle)
        except TaskStoreUnavailable as exc:
            raise TaskRuntimeError(
                "任务状态存储暂时不可用，未继续执行任何业务行动。",
                code="task_store_unavailable",
                status_code=503,
            ) from exc
        except TaskStoreError as exc:
            raise TaskRuntimeError(
                "任务状态无法安全保存，未继续执行任何业务行动。",
                code="task_store_error",
                status_code=503,
            ) from exc

    def _public_view(self, bundle: TaskRecordBundle) -> AgentTaskPublicView:
        task = bundle.task
        plan = bundle.latest_plan()
        node_views: list[AgentTaskPlanNodeView] = []
        if plan is not None:
            for index, node in enumerate(plan.nodes[:8], start=1):
                node_views.append(AgentTaskPlanNodeView(node_label=f"步骤 {index}", goal=node.goal, status=node.status))
        artifact_views = [
            AgentTaskArtifactView(
                kind=artifact.kind,
                summary=artifact.summary,
                source_skill=artifact.source_skill,
                factuality=artifact.factuality,
            )
            for artifact in bundle.artifacts[-12:]
        ]
        action_view = None
        if bundle.action_proposal is not None and bundle.action_proposal.confirmation_status in {"awaiting_confirmation", "confirmed", "unknown"}:
            action_view = AgentTaskActionView(
                action_skill=bundle.action_proposal.action_skill,
                expected_effect=bundle.action_proposal.expected_effect,
                user_explanation=bundle.action_proposal.user_explanation,
                confirmation_status=bundle.action_proposal.confirmation_status,
            )
        context = bundle.latest_context_pack()
        context_view = None
        if context is not None:
            context_view = AgentTaskContextView(
                version=context.version,
                token_estimate_before=context.token_estimate_before,
                token_estimate_after=context.token_estimate_after,
                fact_reference_retention=context.fact_reference_retention,
            )
        return AgentTaskPublicView(
            task_ref=task.task_ref,
            goal=task.normalized_goal,
            status=task.status,
            plan_version=task.plan_version,
            plan_nodes=node_views,
            artifacts=artifact_views,
            open_question=task.waiting_question,
            action=action_view,
            outcome=task.final_outcome,
            limitation_codes=task.limitation_codes,
            execution_summary=(
                f"模型调用 {task.model_calls} 次；Skill 调用 {task.tool_calls} 次；"
                f"上下文整理 {task.context_model_calls} 次；计划版本 {task.plan_version}。"
            ),
            context_summary=context_view,
        )


def _safe_reference(prefix: str, value: object) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


_runtime: TaskRuntime | None = None


def get_task_runtime() -> TaskRuntime:
    global _runtime
    if _runtime is None:
        _runtime = TaskRuntime()
    return _runtime


def set_task_runtime_for_tests(runtime: TaskRuntime | None) -> None:
    global _runtime
    _runtime = runtime
