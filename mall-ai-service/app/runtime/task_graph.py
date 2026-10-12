"""独立长任务图。State 只保存安全游标，请求内决策和凭证不持久化。"""
from __future__ import annotations

from typing import TypedDict, Literal
import uuid

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from pydantic import ValidationError, BaseModel, ConfigDict, Field
from app.schemas.agent_task import AgentTaskStatus

from app.config import settings
from app.runtime.graph_checkpoint import TASK_GRAPH_VERSION, task_saver, thread_config, invoke_graph
from app.runtime.providers import RuntimeModelError
from app.runtime.task_planner import build_model_context
from app.services.human_handoff_client import record_handoff_event
from app.services.llm_observability import capture_llm_metrics
from app.services.trace_service import record_trace


class TaskGraphState(TypedDict, total=False):
    graph_version: str
    task_ref: str
    owner_ref: str
    domain_revision: int
    next_node: str
    status: str
    model_calls: int
    tool_calls: int
    wait_type: str
    plan_version: int
    artifact_refs: list[str]
    proposal_ref: str | None
    run_ref: str | None


class TaskCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    graph_version: Literal["task-v1"]
    task_ref: str = Field(pattern=r"^taskref-[a-z0-9]+$")
    owner_ref: str = Field(pattern=r"^owner-[a-f0-9]{24}$")
    domain_revision: int = Field(ge=0)
    next_node: Literal["prepare", "decide", "validate", "discover", "read_skills", "curate", "critic",
                       "spawn", "revise", "ask", "propose", "finish", "publish", "await_input", "domain_action", "end"]
    status: AgentTaskStatus
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    wait_type: Literal["input", "confirmation", "none"]
    plan_version: int = Field(ge=1)
    artifact_refs: list[str] = Field(max_length=128)
    proposal_ref: str | None
    run_ref: str | None = Field(default=None, pattern=r"^run-[a-f0-9]{32}$")


class TaskTurn:
    """一次认证交互的瞬态依赖，绝不放入 RunnableConfig 或 State。"""

    def __init__(self, runtime, bundle, transient_input, authorization, member_id, reference_hints):
        self.r = runtime
        self.b = bundle
        self.message = transient_input
        self.authorization = authorization
        self.member_id = member_id
        self.hints = dict(runtime._reference_hints)
        self.hints.update(reference_hints or {})
        self.started = runtime._now()
        self.deadline = self.started + bundle.task.execution_budget.max_wall_clock_seconds
        self.discovered = []
        self.decision = None
        self.signatures = set()
        self.repeated_discovery = 0
        self.operation_callback = None

    def projection(self, next_node):
        t = self.b.task
        return {"graph_version": TASK_GRAPH_VERSION, "task_ref": t.task_ref,
                "owner_ref": t.owner_ref, "domain_revision": self.b.storage_revision,
                "status": t.status, "model_calls": t.model_calls, "tool_calls": t.tool_calls,
                "plan_version": t.plan_version, "artifact_refs": list(t.artifact_refs),
                "proposal_ref": self.b.action_proposal.proposal_ref if self.b.action_proposal else None,
                "run_ref": self.b.graph_run_ref,
                "next_node": next_node,
                "wait_type": "confirmation" if t.status == "ready_to_commit" else
                "input" if t.status in {"waiting_for_user", "waiting_for_async_task"} else "none"}

    def block(self, code, message):
        self.r._block(self.b, code, message)
        return self.projection("publish")

    def prepare(self, state):
        t, r = self.b.task, self.r
        if t.expires_at <= r._now():
            return self.block("task_expired", "任务已过期，未继续调用 Skill。")
        if r._now() >= self.deadline:
            return self.block("wall_clock_budget_exhausted", "任务达到时间预算，已安全停止。")
        if t.model_calls >= t.execution_budget.max_model_calls:
            return self.block("model_call_budget_exhausted", "任务达到模型调用预算，已安全停止。")
        t.status = "executing"
        self.discovered = r._discover_for_turn(t, self.message, self.b)
        question = r._preflight_required_input_question(
            t, self.discovered, self.b, transient_input=self.message, reference_hints=self.hints)
        if question is not None:
            t.status, t.waiting_question = "waiting_for_user", question
            r._append_event(self.b, "waiting_for_user", question)
            r._save(self.b)
            return self.projection("publish")
        r._save(self.b)
        return self.projection("decide")

    def decide(self, state):
        t, r, b = self.b.task, self.r, self.b
        context = build_model_context(
            t, b.latest_plan(), [a.summary for a in b.artifacts[-12:]], self.discovered,
            transient_input=self.message, context_pack=b.latest_context_pack(),
            discovery_complete=True, reference_hints=self.hints,
            artifact_details=[{"kind": a.kind, "sourceSkill": a.source_skill,
                               "factuality": a.factuality, "reference": a.reference,
                               "summary": a.summary[:320]} for a in b.artifacts[-12:]],
            limitation_codes=list(t.limitation_codes[-8:]))
        remaining = r._remaining_seconds(self.deadline)
        if remaining <= 0:
            return self.block("runtime_deadline_exceeded", "任务运行时间达到安全上限，已停止等待。")
        # 调用前消费预算；进程退出也不会把已尝试调用从计数中抹掉。
        t.model_calls += 1
        r._save(b)
        try:
            with capture_llm_metrics(timeout_seconds=min(settings.executor_timeout_seconds, remaining), max_attempts=1):
                self.decision = r._provider.decide(context)
        except RuntimeModelError as exc:
            code = "runtime_deadline_exceeded" if r._remaining_seconds(self.deadline) <= 0 else f"model_{exc.category}"
            record_trace("task_runtime", "model_unavailable", t.task_ref, role=exc.role,
                         result_kind="blocked", error_category=exc.category, **exc.diagnostics)
            return self.block(code, "任务模型暂时不可用，任务已安全暂停；未调用业务 Skill。")
        except (ValidationError, TypeError, ValueError):
            t.invalid_decisions += 1
            return self.block("invalid_executor_decision", "任务模型返回的决策不符合契约，未执行任何 Skill。")
        return self.projection("validate")

    def validate(self, state):
        from app.runtime.task_runtime import TaskRuntimeError
        t, r, b, decision = self.b.task, self.r, self.b, self.decision
        if r._duplicate_read_decision(decision, self.signatures):
            if t.limitation_codes:
                t.status, t.waiting_question = "waiting_for_user", "当前事实暂时无法核验，请补充必要信息后再试。"
                r._append_event(b, "waiting_for_user", t.waiting_question)
                r._save(b)
                return self.projection("publish")
            r._append_event(b, "plan_updated", "相同参数的只读 Skill 已执行，未重复调用；请继续处理已有事实或安全澄清。")
            r._save(b)
            self.message = ("服务端已拒绝相同参数的重复只读 Skill；当前已有事实不会因重复调用而增加。"
                            "下一次决策必须使用已有事实 finish，或在确实缺少信息时 ask_user；"
                            "不得再次 call_skill，也不得把重复读取当成新的证据。")
            return self.projection("prepare")
        try:
            r._validate_decision(decision, t, self.discovered, b, reference_hints=self.hints)
        except TaskRuntimeError as exc:
            t.invalid_decisions += 1
            if exc.code == "required_action_input_missing":
                t.status = "waiting_for_user"
                t.waiting_question = r._action_input_question(exc.missing_keys)
                if exc.code not in t.limitation_codes:
                    t.limitation_codes.append(exc.code)
                r._append_event(b, "waiting_for_user", t.waiting_question)
                r._save(b)
                return self.projection("publish")
            return self.block(exc.code, "任务决策未通过服务端能力校验，未执行任何业务动作。")
        return self.projection({"call_skill": "read_skills", "spawn_subtask": "spawn",
                                "revise_plan": "revise", "ask_user": "ask",
                                "propose_action": "propose", "finish": "finish",
                                "discover_skills": "discover"}[decision.decision])

    def discover(self, state):
        self.repeated_discovery += 1
        self.r._append_event(self.b, "plan_updated", "已发现与当前目标相关的受控 Skill。")
        self.r._save(self.b)
        self.message = ("服务端已完成本轮能力发现；不要再次发现。请直接选择一个与目标最相关的只读 Skill、"
                        "必要的用户澄清、受控行动提案或只读完成决策。")
        if self.repeated_discovery >= 2:
            self.message += " 重复发现不会产生事实，必须推进到下一种决策。"
        return self.projection("prepare")

    def read_skills(self, state):
        if self.r._remaining_seconds(self.deadline) <= 0:
            return self.block("runtime_deadline_exceeded", "任务运行时间达到安全上限，已停止执行。")
        self.r._execute_skill_calls(self.b, self.decision, self.authorization, self.member_id)
        self.signatures.update(self.r._read_signature(c.skill_id, c.arguments) for c in self.decision.skill_calls)
        self.r._save(self.b)
        return self.projection("curate")

    def curate(self, state):
        try:
            self.r._refresh_context(self.b, self.discovered, deadline_at=self.deadline)
        except RuntimeModelError as exc:
            if self.r._auxiliary_failure_must_block(exc, self.deadline):
                self.r._block_auxiliary_failure(self.b, exc, self.deadline)
                return self.projection("publish")
            self.r._record_auxiliary_degradation(self.b, exc)
        self.r._save(self.b)
        return self.projection("critic")

    def critic(self, state):
        b, r = self.b, self.r
        if b.artifacts and r._critic.should_trigger(artifacts=b.artifacts, skill_calls=b.task.tool_calls,
                                                  has_action=False, has_conflict=r._has_conflict(b)):
            try:
                r._maybe_critic(b, deadline_at=self.deadline)
            except RuntimeModelError as exc:
                if r._auxiliary_failure_must_block(exc, self.deadline):
                    r._block_auxiliary_failure(b, exc, self.deadline)
                    return self.projection("publish")
                r._record_auxiliary_degradation(b, exc)
        r._save(b)
        conditional = r._conditional_draft_for_insufficient_policy_evidence(b, self.discovered, self.message)
        if conditional is not None:
            r._propose_action(b, conditional)
            r._save(b)
            return self.projection("publish")
        self.message = "观察刚刚获得的事实并决定是否需要继续、重规划或结束"
        return self.projection("prepare")

    def spawn(self, state):
        self.r._execute_spawn_subtask(self.b, self.decision, self.authorization, self.member_id)
        self.r._save(self.b)
        self.message = "观察子任务状态并决定下一步"
        return self.projection("prepare")

    def revise(self, state):
        self.r._revise_plan(self.b, self.decision)
        self.r._save(self.b)
        self.message = "根据新计划继续执行"
        return self.projection("prepare")

    def ask(self, state):
        self.b.task.status, self.b.task.waiting_question = "waiting_for_user", self.decision.user_question
        self.r._append_event(self.b, "waiting_for_user", self.decision.user_question or "请补充必要信息后继续。")
        self.r._save(self.b)
        return self.projection("publish")

    def propose(self, state):
        self.r._propose_action(self.b, self.decision)
        self.r._save(self.b)
        if self.b.handoff and self.decision.action_skill == "open_human_case":
            record_handoff_event(self.b.handoff, self.authorization, "suggested")
        return self.projection("publish")

    def finish(self, state):
        from app.runtime.task_runtime import _safe_reference
        t, b, r = self.b.task, self.b, self.r
        t.status, t.final_outcome, t.waiting_question = "completed", self.decision.reason_summary, None
        r._append_event(b, "task_completed", self.decision.reason_summary)
        if self.decision.reason_summary not in b.memory_hints:
            b.memory_hints = (b.memory_hints + [self.decision.reason_summary])[-32:]
        r._memory.remember(owner_ref=t.owner_ref, task_ref=t.task_ref, summary=self.decision.reason_summary,
                           reference=_safe_reference("memory", t.task_ref), ttl_seconds=settings.agent_task_ttl_seconds)
        r._save(b)
        return self.projection("publish")

    def publish(self, state):
        return self.projection("await_input" if self.b.task.status in {"waiting_for_user", "waiting_for_async_task", "ready_to_commit", "blocked"} else "end")

    def await_input(self, state):
        operation = interrupt({"task_ref": state["task_ref"], "wait_type": state["wait_type"]})
        if operation not in {"continue", "confirm", "amend", "reconcile"}:
            raise ValueError("不允许的任务恢复操作")
        return self.projection("prepare" if operation == "continue" else "domain_action")

    def domain_action(self, state):
        if self.operation_callback is None:
            return self.block("fresh_confirmation_required", "请重新核对当前提案后确认；未恢复旧确认动作。")
        self.operation_callback()
        self.b = self.r._store.load_owned(self.b.task.task_ref, self.b.task.owner_ref)
        return self.projection("publish")


def compile_task_graph(turn, saver):
    builder = StateGraph(TaskGraphState)
    names = ("prepare", "decide", "validate", "discover", "read_skills", "curate", "critic",
             "spawn", "revise", "ask", "propose", "finish", "publish", "await_input", "domain_action")
    for name in names:
        builder.add_node(name, getattr(turn, name))
        builder.add_conditional_edges(name, lambda state: state["next_node"], {**{n: n for n in names}, "end": END})
    builder.add_edge(START, "prepare")
    return builder.compile(checkpointer=saver, name="TaskGraph")


def run_task_graph(runtime, bundle, *, transient_input, authorization, member_id, reference_hints=None):
    from app.runtime.task_runtime import TaskRuntimeResult, TaskRuntimeError
    turn = TaskTurn(runtime, bundle, transient_input, authorization, member_id, reference_hints)
    graph = compile_task_graph(turn, task_saver(runtime._store))
    config = thread_config(TASK_GRAPH_VERSION, bundle.task.owner_ref, bundle.task.task_ref)
    saved = graph.get_state(config)
    if saved.values:
        TaskCursor.model_validate(saved.values)
    if saved.values and saved.values.get("graph_version") != TASK_GRAPH_VERSION:
        raise TaskRuntimeError("任务图版本不兼容。", code="graph_version_mismatch", status_code=409)
    domain_advanced = saved.values and saved.values.get("domain_revision") != bundle.storage_revision
    checkpoint_missing = not saved.values and bundle.graph_run_ref is not None
    if bundle.graph_invocation_pending or checkpoint_missing or domain_advanced or (saved.next and saved.next != ("await_input",)):
        # 不重放丢失的请求内决策或未结算外部操作，保留已保存的领域事实。
        turn.block("interrupted_graph_run", "上次执行被中断，请核对已有结果后重新补充信息；没有自动重放调用。")
        bundle.graph_invocation_pending = False
        runtime._save(bundle)
        publish_task_checkpoint(runtime, bundle)
    else:
        bundle.graph_invocation_pending = True
        bundle.graph_run_ref = "run-"+uuid.uuid4().hex
        runtime._save(bundle)
        if saved.next == ("await_input",):
            invoke_graph(graph, Command(resume="continue"), config)
        else:
            invoke_graph(graph, turn.projection("prepare"), config)
        bundle.graph_invocation_pending = False
        runtime._save(bundle)
        publish_task_checkpoint(runtime, bundle)
    record_trace("task_runtime", "turn_finished", bundle.task.task_ref,
                 result_kind="success" if bundle.task.status == "completed" else "blocked" if bundle.task.status == "blocked" else "pending",
                 duration_ms=max(0, round((runtime._now()-turn.started)*1000)),
                 tool_call_count=bundle.task.tool_calls, profile_version="v3_0")
    return TaskRuntimeResult(runtime._public_view(bundle), list(bundle.events))


def run_task_operation(runtime, operation, arguments):
    from app.runtime.task_runtime import TaskRuntimeResult, TaskRuntimeError
    from app.runtime.task_store import TaskStoreAccessDenied
    owner, _ = runtime._require_owner("task-session", arguments.get("member_id"), arguments.get("authorization"), allow_session_placeholder=True)
    try:
        bundle = runtime._store.load_owned(arguments["task_ref"], owner)
    except TaskStoreAccessDenied as exc:
        raise TaskRuntimeError("任务不存在或不属于当前用户。", code="task_not_found", status_code=404) from exc
    if operation == "reconcile" and bundle.graph_version is None:
        bundle.graph_version = TASK_GRAPH_VERSION
        runtime._save(bundle)
    if bundle.graph_version != TASK_GRAPH_VERSION:
        raise TaskRuntimeError("旧版本提案不能在新图确认，请重新生成确认卡；未知提交请先对账。",
                               code="legacy_graph_confirmation_disabled", status_code=409)
    turn = TaskTurn(runtime, bundle, "", arguments.get("authorization"), arguments.get("member_id"), {})
    turn.operation_callback = lambda: getattr(runtime, f"_{operation}_domain")(**arguments)
    graph = compile_task_graph(turn, task_saver(runtime._store))
    config = thread_config(TASK_GRAPH_VERSION, owner, bundle.task.task_ref)
    saved = graph.get_state(config)
    if saved.values:
        TaskCursor.model_validate(saved.values)
    if saved.next and saved.next not in {("await_input",)}:
        # 已落库的提交结果可投影恢复；其他中断先由领域对账接口处理。
        if bundle.action_proposal and bundle.action_proposal.confirmation_status in {"confirmed", "unknown"} and operation != "reconcile":
            raise TaskRuntimeError("提交结果尚未核实，请查询原请求。", code="commit_result_unknown", status_code=409)
    # prepare_handoff 也是领域提案工厂，在此仅登记等待游标，不推断确认。
    bundle.graph_invocation_pending = True
    bundle.graph_run_ref = "run-"+uuid.uuid4().hex
    runtime._save(bundle)
    graph.update_state(config, turn.projection("await_input"), as_node="publish")
    invoke_graph(graph, None, config)
    invoke_graph(graph, Command(resume=operation), config)
    turn.b.graph_invocation_pending = False
    runtime._save(turn.b)
    publish_task_checkpoint(runtime, turn.b)
    return TaskRuntimeResult(runtime._public_view(turn.b), list(turn.b.events))


def project_task(runtime, bundle):
    """展示缓存丢失时按同修订检查点重建，领域提案和结果永不被覆盖。"""
    task = bundle.task.model_copy(deep=True)
    if bundle.graph_version != TASK_GRAPH_VERSION:
        return task
    checkpoint = task_saver(runtime._store).get_tuple(thread_config(TASK_GRAPH_VERSION, task.owner_ref, task.task_ref))
    if checkpoint:
        values = checkpoint.checkpoint["channel_values"]
        values = TaskCursor.model_validate({key: values[key] for key in TaskGraphState.__annotations__ if key in values}).model_dump()
        if values.get("domain_revision") == bundle.storage_revision:
            task.status = values.get("status", task.status)
    return task


def publish_task_checkpoint(runtime, bundle):
    """领域工厂生成交接卡/子任务后登记等待位置，不启动任何模型或 Skill。"""
    turn = TaskTurn(runtime, bundle, "", None, None, {})
    graph = compile_task_graph(turn, task_saver(runtime._store))
    config = thread_config(TASK_GRAPH_VERSION, bundle.task.owner_ref, bundle.task.task_ref)
    graph.update_state(config, turn.publish({}), as_node="publish")
    if bundle.task.status in {"waiting_for_user", "waiting_for_async_task", "ready_to_commit", "blocked"}:
        invoke_graph(graph, None, config)
