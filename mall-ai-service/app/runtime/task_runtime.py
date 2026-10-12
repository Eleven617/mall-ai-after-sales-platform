"""Generic, bounded E-Commerce Task Runtime.

This module is intentionally a runtime, not a second business workflow.  It
coordinates model decisions, Skill discovery, safe observations, Context Pack
updates, optional Critic calls and transaction gates.  Java/RAG access is
delegated to ``SkillGateway``; the runtime never writes the mall database.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from functools import wraps
from app.services.reliability_service import reliability_governor, ConcurrentOperationError, ReliabilityBackendUnavailable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from app.config import settings
from app.runtime.graph_checkpoint import TASK_GRAPH_VERSION
from app.schemas.agent_task import (
    ActionProposal,
    AgentTask,
    AgentTaskActionView,
    AgentTaskArtifactView,
    AgentTaskContextView,
    AgentTaskContinueRequest,
    AgentTaskEvent,
    AgentTaskExecutionMetricsView,
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
    DeterministicRuntimeProvider,
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
from app.skills.catalog import (
    SkillDefinition,
    confirmation_executor_skill,
    discovery_score,
    discover_skills,
    get_skill,
    validate_catalog_consistency,
)
from app.skills.commerce_gateway import (
    SafeCommerceSkillGateway,
    SkillGateway,
    SkillGatewayError,
    SkillObservation,
)
from app.services.trace_service import record_trace
from app.services.identifier_extraction import extract_order_sn, extract_sku_id
from app.services.llm_observability import capture_llm_metrics
from app.schemas.human_handoff import HandoffContext, HandoffPrepare
from app.services.human_handoff_client import handoff_request, HandoffUnavailable, record_handoff_event


class TaskRuntimeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "runtime_error",
        status_code: int = 400,
        missing_keys: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.missing_keys = list(missing_keys or [])


def serialized_task(method):
    """One distributed guard across all mutation entry points for a task."""
    @wraps(method)
    def guarded(self,*args,**kwargs):
        request=args[0] if args else kwargs.get('request')
        ref=kwargs.get('task_ref') or getattr(request,'task_ref',None)
        scope=ref or 'handoff:'+str(kwargs.get('member_id'))+':'+str(getattr(request,'session_id',''))
        try:
            with reliability_governor.lock(scope=scope,kind='proposal',ttl_seconds=300):
                return method(self,*args,**kwargs)
        except ConcurrentOperationError as exc:
            raise TaskRuntimeError('当前事项正在处理，请稍后刷新原事项。',code='task_busy',status_code=409) from exc
        except ReliabilityBackendUnavailable as exc:
            raise TaskRuntimeError('事项保护服务暂不可用，请稍后重试。',code='task_lock_unavailable',status_code=503) from exc
    return guarded


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
        reference_hints: Mapping[str, str] | None = None,
        read_skill_allowlist: set[str] | None = None,
    ) -> None:
        self._store = store or get_task_store()
        catalog_errors = validate_catalog_consistency()
        if catalog_errors:
            raise RuntimeError("Skill Catalog contract invalid: " + ",".join(catalog_errors))
        if provider is None:
            # A configured provider key is never sufficient to enable network
            # access.  Live mode is selected only by an explicit formal
            # runner grant and is rechecked by the shared HTTP guard.
            provider_mode = str(os.getenv("MALL_RUNTIME_PROVIDER_MODE", "offline")).strip().lower()
            if provider_mode in {"deterministic", "replay"}:
                provider = DeterministicRuntimeProvider(mode=provider_mode)
            elif provider_mode == "live" and os.getenv("MALL_PROVIDER_LIVE_AUTH", "0") == "1":
                provider = DeepSeekRuntimeProvider()
            else:
                provider = UnavailableRuntimeProvider()
        self._provider = provider
        from app.skills.unified_gateway import UnifiedSkillGateway
        self._gateway = gateway or UnifiedSkillGateway()
        self._memory = memory or TaskMemory()
        self._now = now_fn
        self._reference_hints = {
            str(key): str(value)
            for key, value in (reference_hints or {}).items()
            if isinstance(key, str) and isinstance(value, str) and key and value
        }
        self._read_skill_allowlist = None if read_skill_allowlist is None else set(read_skill_allowlist)
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
            execution_budget=self._bounded_execution_budget(execution_budget),
            expires_at=now + settings.agent_task_ttl_seconds,
        )
        bundle = TaskRecordBundle(task=task, graph_version=TASK_GRAPH_VERSION)
        plan = build_initial_plan(task)
        bundle.plans.append(plan)
        task.plan_version = plan.version
        self._append_event(bundle, "task_created", "已创建电商任务，正在形成可执行计划。")
        self._save(bundle)
        with reliability_governor.lock(scope=task.task_ref, kind="proposal", ttl_seconds=300):
            result = self._run_turn(
                bundle, transient_input=goal, authorization=authorization, member_id=member_id,
                reference_hints=self._reference_hints_from_input(goal),
            )
        return result

    @serialized_task
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
        from app.runtime.task_graph import project_task
        bundle.task.status = project_task(self, bundle).status
        if bundle.task.status in {"completed", "cancelled", "waiting_human"} or (bundle.action_proposal and bundle.action_proposal.confirmation_status in {"confirmed", "unknown"}):
            raise TaskRuntimeError("该任务已经结束，不能继续。", code="task_terminal", status_code=409)
        if bundle.graph_version is None:
            if bundle.action_proposal and bundle.action_proposal.confirmation_status == "awaiting_confirmation":
                bundle.action_proposal.confirmation_status = "expired"
                bundle.task.pending_action_ref = None
            bundle.graph_version = TASK_GRAPH_VERSION
            self._append_event(bundle, "plan_updated", "执行器已升级；旧确认卡失效，保留已验证事实并重新生成方案。")
            self._save(bundle)
        elif bundle.graph_version != TASK_GRAPH_VERSION:
            raise TaskRuntimeError("任务图版本不兼容。", code="graph_version_mismatch", status_code=409)
        return self._run_turn(
            bundle,
            transient_input=message,
            authorization=authorization,
            member_id=member_id,
            reference_hints=self._reference_hints_from_input(message),
        )

    def get_task(self, *, task_ref: str, member_id: int | None, authorization: str | None) -> AgentTaskPublicView:
        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        try:
            bundle = self._store.load_owned(task_ref, owner_ref)
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc
        return self._public_view(bundle)

    @serialized_task
    def prepare_handoff(self, request: HandoffPrepare, *, member_id: int, authorization: str, channel="button") -> TaskRuntimeResult:
        from app.services.handoff_projection import project
        problem_projection = project(request.topic, request.problem_description)
        owner, session = self._require_owner(request.session_id, member_id, authorization)
        if request.task_ref:
            bundle = self._store.load_owned(request.task_ref, owner)
            if bundle.task.session_ref != session:
                raise TaskRuntimeError("事项不属于当前会话", status_code=404)
            if bundle.task.status in {"committing", "waiting_human"} or (bundle.action_proposal and bundle.action_proposal.confirmation_status in {"confirmed", "unknown"}):
                return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        else:
            existing = self._store.list_owned(owner, session)
            pending = next((item for item in existing if item.handoff and item.handoff.linked_task_ref is None and item.task.status in {"ready_to_commit","waiting_human","blocked"}), None)
            if pending and not request.new_issue:
                bundle=pending
                if bundle.task.status=='waiting_human' or (bundle.action_proposal and bundle.action_proposal.confirmation_status in {'confirmed','unknown'}):
                    return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
            else:
                task_id=new_task_id()
                bundle=TaskRecordBundle(graph_version=TASK_GRAPH_VERSION,task=AgentTask(task_id=task_id,task_ref='taskref-'+task_id.removeprefix('task-'),
                    owner_ref=owner,session_ref=session,goal_digest=hashlib.sha256(b'customer_handoff').hexdigest(),
                    normalized_goal="请求人工协助",expires_at=self._now()+settings.agent_task_ttl_seconds))
                bundle.plans.append(build_initial_plan(bundle.task)); bundle.task.plan_version=bundle.plans[-1].version
        from app.services.handoff_safe_context import snapshot
        if bundle.graph_version not in {None, TASK_GRAPH_VERSION}:
            raise TaskRuntimeError("任务图版本不兼容。", code="graph_version_mismatch", status_code=409)
        if bundle.graph_version is None and bundle.action_proposal and bundle.action_proposal.confirmation_status == "awaiting_confirmation":
            bundle.action_proposal.confirmation_status = "expired"
            bundle.task.pending_action_ref = None
        from app.services.conversation_scope import build_conversation_state_key
        from app.services.conversation_state import get_conversation_state
        from app.services.conversation_store import ConversationStoreError
        try:
            safe_state=get_conversation_state(build_conversation_state_key(request.session_id,member_id))
            safe_fragments=safe_state.handoff_fragments;context_omitted=safe_state.handoff_context_omitted
        except ConversationStoreError:
            safe_fragments=[];context_omitted=True
        execution=[]
        if request.task_ref:
            safe_skills={'read_order':'查询订单','build_service_resolution':'比较处理方案','query_policy':'查询政策'}
            for artifact in bundle.artifacts:
                if artifact.source_skill in safe_skills and artifact.factuality=='verified' and artifact.expires_at>self._now():
                    step=safe_skills[artifact.source_skill]+' 结果 已完成'
                    if step not in execution:execution.append(step)
        safe_input=snapshot(safe_fragments,request.problem_description,request.topic,request.task_ref,
            bundle.task.normalized_goal if request.task_ref else None,execution=execution,omitted=context_omitted)
        if bundle.handoff and bundle.action_proposal and bundle.action_proposal.confirmation_status == 'awaiting_confirmation' and bundle.action_proposal.expires_at>self._now() and bundle.handoff.reason==request.reason and bundle.handoff.topic==request.topic and bundle.handoff.problem_projection==problem_projection and bundle.handoff.safe_input_snapshot==safe_input:
            return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
        bundle.task.expires_at=max(bundle.task.expires_at,self._now()+settings.agent_task_ttl_seconds)
        if bundle.handoff is None:
            bundle.handoff=HandoffContext(request_ref=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                scope_key=hashlib.sha256((owner+':'+bundle.task.task_ref).encode()).hexdigest(),
                channel=channel,topic=request.topic,reason=request.reason,stage=bundle.task.status,linked_task_ref=request.task_ref)
        else:
            bundle.handoff.reason=request.reason; bundle.handoff.topic=request.topic
        bundle.handoff.plan_version=bundle.task.plan_version
        bundle.handoff.problem_projection=problem_projection
        bundle.handoff.safe_input_snapshot=safe_input
        bundle.handoff.completed_steps=sum(node.status=='completed' for node in bundle.plans[-1].nodes) if bundle.plans else 0
        bundle.handoff.verified_evidence_count=sum(artifact.factuality=='verified' and artifact.expires_at>self._now() for artifact in bundle.artifacts)
        reference='context-'+uuid.uuid4().hex[:24]
        bundle.artifacts.append(TaskArtifact(artifact_id=new_artifact_id(),task_id=bundle.task.task_id,
            kind='conversation_context_projection',source_skill='open_human_case',source_version='v2',
            factuality='derived',summary='客户请求人工；业务事实尚待人工核验。',reference=reference,
            expires_at=bundle.task.expires_at,hash=hashlib.sha256(reference.encode()).hexdigest()))
        bundle.task.artifact_refs.append(reference)
        self._propose_action(bundle, ExecutorDecision(decision='propose_action',action_skill='open_human_case',
            action_arguments={'artifactRefs':[reference],'reasonCode':'manual_review','customerReason':request.reason,'businessTopic':request.topic},
            reason_summary='确认后登记人工案件并等待领取；不代表实时客服接通，也不会申请退款。'))
        bundle.task.waiting_question=None
        self._save(bundle)
        record_handoff_event(bundle.handoff,authorization,'requested')
        bundle.graph_version = TASK_GRAPH_VERSION
        self._save(bundle)
        from app.runtime.task_graph import publish_task_checkpoint
        publish_task_checkpoint(self, bundle)
        return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))

    @serialized_task
    def reconcile_handoff(self, *, task_ref: str, member_id: int, authorization: str) -> TaskRuntimeResult:
        from app.runtime.task_graph import run_task_operation
        return run_task_operation(self, "reconcile", dict(task_ref=task_ref, member_id=member_id, authorization=authorization))

    def _reconcile_domain(self, *, task_ref: str, member_id: int, authorization: str) -> TaskRuntimeResult:
        owner,_=self._require_owner('task-session',member_id,authorization,allow_session_placeholder=True)
        bundle=self._store.load_owned(task_ref,owner)
        if not bundle.action_proposal:
            raise TaskRuntimeError('没有待核对的提交记录',status_code=404)
        if not bundle.handoff:
            proposal = bundle.action_proposal
            if proposal.confirmation_status not in {"confirmed", "unknown"}:
                return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
            if proposal.confirmation_executor_skill_id != "commit_after_sales_action":
                raise TaskRuntimeError("该行动没有受控对账接口。", code="reconciliation_not_supported", status_code=409)
            key = hashlib.sha256(f"{bundle.task.task_id}:{proposal.proposal_id}:{proposal.content_hash}:{proposal.confirmation_executor_skill_id}".encode()).hexdigest()[:32]
            observation = self._gateway.reconcile(key, authorization=authorization, member_id=member_id, task_ref=task_ref)
            if observation.status == "succeeded":
                self._record_observation(bundle, proposal.confirmation_executor_skill_id, observation)
                proposal.confirmation_status = "committed"
                bundle.task.pending_action_ref = None
                bundle.task.status = "executing"
                self._append_event(bundle, "action_committed", "已从 Java 查回原请求结果，未重新提交。")
                self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        result=handoff_request(bundle.handoff,bundle.action_proposal.content_hash,authorization,lookup=True)
        bundle.handoff.case_ref=result.caseRef
        bundle.action_proposal.confirmation_status='committed'
        bundle.task.pending_action_ref=None
        bundle.task.status='waiting_human'
        bundle.task.final_outcome='已登记人工案件，请在人工协同进度中查看处理状态。'
        self._save(bundle)
        return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))

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

    @serialized_task
    def amend_action(
        self, **kwargs,
    ) -> TaskRuntimeResult:
        from app.runtime.task_graph import run_task_operation
        return run_task_operation(self, "amend", kwargs)

    def _amend_domain(
        self,
        *,
        task_ref: str,
        proposal_ref: str,
        revision: int,
        application_type: str,
        member_id: int | None,
        authorization: str | None,
    ) -> TaskRuntimeResult:
        """Create a new version of an uncommitted after-sales draft.

        This path only changes the owner-scoped Runtime proposal vault.  It
        never calls Java, creates an idempotency key, or mutates a business
        application; confirmation of the returned version remains separate.
        """

        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        if application_type not in {"cancel_refund", "return_refund", "exchange", "repair"}:
            raise TaskRuntimeError("售后类型不受支持。", code="application_type_invalid")
        try:
            bundle = self._store.load_owned(task_ref, owner_ref)
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc
        current = bundle.action_proposal
        if current is None or current.confirmation_status != "awaiting_confirmation":
            raise TaskRuntimeError("当前没有可修改的待确认草案。", code="action_gate_missing", status_code=409)
        if proposal_ref != current.proposal_ref or revision != current.revision:
            raise TaskRuntimeError("方案已更新，请刷新后再修改。", code="stale_proposal_revision", status_code=409)
        if current.expires_at <= self._now():
            current.confirmation_status = "expired"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("action_expired")
            self._append_event(bundle, "task_blocked", "待确认草案已过期，未执行任何业务写入。")
            self._save(bundle)
            raise TaskRuntimeError("待确认草案已过期。", code="proposal_expired", status_code=409)
        if current.action_skill != "create_after_sales_draft":
            raise TaskRuntimeError("当前方案不是可修改的售后草案。", code="action_not_amendable", status_code=409)
        arguments = bundle.action_arguments.get(current.arguments_ref)
        if not isinstance(arguments, dict):
            raise TaskRuntimeError("草案参数已失效，请重新发起任务。", code="action_arguments_missing", status_code=409)
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != current.content_hash:
            raise TaskRuntimeError("草案内容校验失败，请重新发起任务。", code="proposal_content_hash_mismatch", status_code=409)
        next_arguments = dict(arguments)
        next_arguments["applicationType"] = application_type
        assert_safe_action_arguments(
            next_arguments,
            allowed_opaque_references={artifact.reference for artifact in bundle.artifacts},
        )
        bundle.action_proposal_history.append(current.model_copy(update={"confirmation_status": "superseded", "updated_at": self._now()}))
        bundle.action_proposal_history = bundle.action_proposal_history[-32:]
        arguments_ref = new_arguments_ref()
        bundle.action_arguments[arguments_ref] = next_arguments
        content_hash = hashlib.sha256(
            json.dumps(next_arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        new_id = new_proposal_id()
        next_proposal = ActionProposal(
            proposal_id=new_id,
            proposal_ref=f"proposalref-{new_id.removeprefix('proposal-')}",
            revision=current.revision + 1,
            supersedes_proposal_ref=current.proposal_ref,
            task_id=bundle.task.task_id,
            action_skill=current.action_skill,
            confirmation_executor_skill_id=current.confirmation_executor_skill_id,
            arguments_ref=arguments_ref,
            expected_effect=current.expected_effect,
            evidence_refs=list(current.evidence_refs),
            alternatives=list(current.alternatives),
            user_explanation="售后类型已更新；确认当前版本前不会写入商城。",
            confirmation_status="awaiting_confirmation",
            content_hash=content_hash,
            expires_at=min(bundle.task.expires_at, self._now() + 900),
        )
        bundle.action_proposal = next_proposal
        bundle.task.pending_action_ref = new_id
        bundle.task.status = "ready_to_commit"
        bundle.task.limitation_codes = [code for code in bundle.task.limitation_codes if code != "required_action_input_missing"]
        self._append_event(bundle, "action_revised", "售后草案已生成新版本；旧版本已失效，确认前不会写入商城。")
        self._save(bundle)
        return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))

    @serialized_task
    def confirm_action(
        self, **kwargs,
    ) -> TaskRuntimeResult:
        from app.runtime.task_graph import run_task_operation
        return run_task_operation(self, "confirm", kwargs)

    def _confirm_domain(
        self,
        *,
        task_ref: str,
        confirmation: str,
        member_id: int | None,
        authorization: str | None,
        proposal_ref: str | None = None,
        revision: int | None = None,
    ) -> TaskRuntimeResult:
        owner_ref, _ = self._require_owner("task-session", member_id, authorization, allow_session_placeholder=True)
        try:
            bundle = self._store.load_owned(task_ref, owner_ref)
        except TaskStoreAccessDenied as exc:
            raise TaskRuntimeError(str(exc), code="task_not_found", status_code=404) from exc
        proposal = bundle.action_proposal
        if bundle.handoff and proposal and proposal.confirmation_status == 'committed' and proposal_ref == proposal.proposal_ref and revision == proposal.revision:
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if proposal is None or proposal.confirmation_status != "awaiting_confirmation":
            raise TaskRuntimeError("当前任务没有有效的待确认行动。", code="action_gate_missing", status_code=409)
        if (proposal_ref is not None or revision is not None) and (
            proposal_ref != proposal.proposal_ref or revision != proposal.revision
        ):
            raise TaskRuntimeError(
                "待确认方案已更新，请刷新后重新确认。",
                code="stale_proposal_revision",
                status_code=409,
            )
        if proposal.expires_at <= self._now():
            proposal.confirmation_status = "expired"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("action_expired")
            self._append_event(bundle, "task_blocked", "待确认行动已过期，未执行任何业务写入。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if confirmation == "withdraw":
            if bundle.handoff and proposal.action_skill == 'open_human_case':
                record_handoff_event(bundle.handoff,authorization,'cancelled')
            proposal.confirmation_status = "withdrawn"
            bundle.task.pending_action_ref = None
            bundle.task.status = "executing"
            self._append_event(bundle, "task_completed", "已撤回待确认行动，未执行业务写入。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if confirmation != "confirm":
            raise TaskRuntimeError("确认状态不合法。", code="invalid_confirmation")
        proposal_skill = get_skill(proposal.action_skill)
        executor_skill = confirmation_executor_skill(proposal.action_skill)
        if proposal.confirmation_executor_skill_id is None:
            # A record written before the v3.0.3 contract has no explicit
            # executor.  Never infer one from the proposal name; block it in
            # a persisted, user-safe state instead of raising/guessing.
            proposal.confirmation_status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("confirmation_executor_missing")
            self._append_event(bundle, "task_blocked", "待确认行动缺少受控执行映射，未执行任何业务写入。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if (
            proposal_skill is None
            or proposal_skill.action_mode not in {"draft", "commit", "async_task"}
            or not proposal_skill.requires_confirmation
            or executor_skill is None
            or proposal.confirmation_executor_skill_id != executor_skill.skill_id
        ):
            proposal.confirmation_status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("confirmation_executor_invalid")
            self._append_event(bundle, "task_blocked", "待确认行动的执行映射未通过服务端目录校验，未执行任何业务写入。")
            self._save(bundle)
            record_trace(
                "task_runtime",
                "confirmation_rejected",
                bundle.task.task_ref,
                proposal_skill_id=proposal.action_skill,
                execution_skill_id=proposal.confirmation_executor_skill_id,
                result_kind="blocked",
                contract_violation="confirmation_executor_invalid",
            )
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        arguments = bundle.action_arguments.get(proposal.arguments_ref)
        if arguments is None:
            raise TaskRuntimeError("待确认行动参数已失效，请重新生成方案。", code="action_arguments_missing", status_code=409)
        canonical_arguments = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if hashlib.sha256(canonical_arguments).hexdigest() != proposal.content_hash:
            proposal.confirmation_status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("proposal_content_hash_mismatch")
            self._append_event(bundle, "task_blocked", "待确认行动内容校验失败，未执行任何业务写入。")
            self._save(bundle)
            record_trace(
                "task_runtime",
                "confirmation_rejected",
                bundle.task.task_ref,
                proposal_skill_id=proposal.action_skill,
                execution_skill_id=executor_skill.skill_id,
                result_kind="blocked",
                contract_violation="proposal_content_hash_mismatch",
            )
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if "idempotencyKey" in arguments:
            proposal.confirmation_status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("model_idempotency_key_present")
            self._append_event(bundle, "task_blocked", "待确认行动包含非服务端生成的幂等键，未执行任何业务写入。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if proposal.action_skill == 'open_human_case' and not bundle.handoff:
            proposal.confirmation_status='blocked'
            self._block(bundle,'handoff_contract_upgrade_required','交接卡需要更新，请重新点击转人工生成新卡。')
            return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
        if bundle.handoff and proposal.action_skill == 'open_human_case':
            projection_hash=hashlib.sha256(bundle.handoff.model_dump_json(exclude={'case_ref'}).encode()).hexdigest()
            if arguments.get('handoffProjectionHash') != projection_hash:
                proposal.confirmation_status='blocked'
                self._block(bundle,'handoff_projection_changed','交接内容已变化，请重新生成交接卡。')
                return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
            live_refs={artifact.reference for artifact in bundle.artifacts if artifact.expires_at>self._now()}
            refs=arguments.get('artifactRefs')
            if not isinstance(refs,list) or not refs or any(ref not in live_refs for ref in refs) or arguments.get('reasonCode') not in {'manual_review','insufficient_evidence','tool_failure'}:
                self._block(bundle,'handoff_artifact_reference_invalid','交接背景已失效，请重新生成交接卡。')
                return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
            proposal.confirmation_status='confirmed'; bundle.task.status='committing'; self._save(bundle)
            try:
                result=handoff_request(bundle.handoff,proposal.content_hash,authorization)
            except HandoffUnavailable:
                try:
                    result=handoff_request(bundle.handoff,proposal.content_hash,authorization,lookup=True)
                except HandoffUnavailable:
                    proposal.confirmation_status='unknown'; bundle.task.status='blocked'
                    bundle.task.final_outcome='交接结果待确认，请查询原请求；不要重新创建案件。'
                    self._save(bundle)
                    return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
            bundle.handoff.case_ref=result.caseRef
            proposal.confirmation_status='committed'; bundle.task.pending_action_ref=None
            bundle.task.status='waiting_human'
            bundle.task.final_outcome='已登记，等待人工领取。可在人工协同进度中补充信息。'
            self._append_event(bundle,'action_committed',bundle.task.final_outcome)
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle),list(bundle.events))
        missing_keys = [
            key
            for key in executor_skill.confirmation_required_input_keys
            if key not in arguments or arguments.get(key) in (None, "")
        ]
        if missing_keys:
            proposal.confirmation_status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.status = "waiting_for_user"
            bundle.task.waiting_question = self._action_input_question(missing_keys)
            bundle.task.limitation_codes.append("required_action_input_missing")
            self._append_event(bundle, "waiting_for_user", bundle.task.waiting_question)
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        if executor_skill.skill_id == "commit_after_sales_action":
            order_fact_ref = arguments.get("orderFactRef")
            verified_order_artifacts = [
                artifact
                for artifact in bundle.artifacts
                if artifact.kind == "order_fact"
                and artifact.factuality == "verified"
                and artifact.expires_at > self._now()
            ]
            if not isinstance(order_fact_ref, str) or not any(
                artifact.reference == order_fact_ref for artifact in verified_order_artifacts
            ):
                proposal.confirmation_status = "blocked"
                bundle.task.pending_action_ref = None
                bundle.task.status = "blocked"
                bundle.task.limitation_codes.append("commit_without_verified_order_fact")
                self._append_event(bundle, "task_blocked", "提交行动缺少当前任务的有效订单事实，未执行任何业务写入。")
                self._save(bundle)
                return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
            execution_arguments = {
                "orderFactRef": order_fact_ref,
                "applicationType": arguments.get("applicationType"),
                # proposalRef is server-bound; a model-supplied value is never
                # used to select the transaction gate.
                "proposalRef": proposal.proposal_id,
            }
            if isinstance(arguments.get("actionRef"), str):
                execution_arguments["actionRef"] = arguments["actionRef"]
        elif executor_skill.skill_id == "commit_human_case":
            artifact_refs = arguments.get("artifactRefs")
            reason_code = arguments.get("reasonCode")
            current_artifacts = {
                artifact.reference: artifact
                for artifact in bundle.artifacts
                if artifact.expires_at > self._now()
            }
            if (
                not isinstance(artifact_refs, list)
                or not artifact_refs
                or not all(isinstance(ref, str) and ref in current_artifacts for ref in artifact_refs)
                or reason_code not in {"tool_failure", "insufficient_evidence", "manual_review"}
            ):
                proposal.confirmation_status = "blocked"
                bundle.task.pending_action_ref = None
                bundle.task.status = "blocked"
                bundle.task.limitation_codes.append("handoff_artifact_reference_invalid")
                self._append_event(bundle, "task_blocked", "人工协同提案引用已失效，未创建人工案件。")
                self._save(bundle)
                return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
            selected = [current_artifacts[ref] for ref in artifact_refs]
            evidence_status = "complete" if all(item.factuality == "verified" for item in selected) else "partial"
            execution_arguments = {
                "artifactRefs": list(artifact_refs),
                "reasonCode": reason_code,
                "diagnosisCategory": "tool_failure" if reason_code == "tool_failure" else "facts_incomplete",
                "evidenceStatus": evidence_status,
                "verifiedSourceTypes": sorted({item.kind for item in selected})[:4],
            }
        else:
            proposal.confirmation_status = "blocked"
            bundle.task.pending_action_ref = None
            bundle.task.status = "blocked"
            bundle.task.limitation_codes.append("confirmation_executor_invalid")
            self._append_event(bundle, "task_blocked", "待确认行动没有受控服务器执行器，未创建业务对象。")
            self._save(bundle)
            return TaskRuntimeResult(self._public_view(bundle), list(bundle.events))
        execution_arguments["idempotencyKey"] = hashlib.sha256(
            f"{bundle.task.task_id}:{proposal.proposal_id}:{proposal.content_hash}:{executor_skill.skill_id}".encode("utf-8")
        ).hexdigest()[:32]
        assert_safe_action_arguments(
            execution_arguments,
            allow_generated_idempotency_key=True,
            allowed_opaque_references={
                artifact.reference for artifact in bundle.artifacts
            }
            | {proposal.proposal_id},
        )
        proposal.confirmation_status = "confirmed"
        bundle.task.status = "committing"
        self._append_event(bundle, "action_committed", "已收到客户确认，正在由受控领域服务复核执行。")
        self._save(bundle)
        try:
            observation = self._gateway.commit(
                executor_skill.skill_id,
                execution_arguments,
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
        self._record_observation(bundle, executor_skill.skill_id, observation)
        record_trace(
            "task_runtime",
            "confirmation_execution",
            bundle.task.task_ref,
            proposal_skill_id=proposal.action_skill,
            execution_skill_id=executor_skill.skill_id,
            result_kind=observation.status,
        )
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
            # Keep the proposal reference bound while the Java result is
            # unknown.  Clearing it would make the persisted bundle invalid
            # (the proposal is still publicly represented as ``unknown``) and
            # a repeated confirmation could surface a 500 instead of a safe
            # idempotent gate rejection.
            bundle.task.pending_action_ref = proposal.proposal_id
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
        reference_hints: Mapping[str, str] | None = None,
    ) -> TaskRuntimeResult:
        from app.runtime.task_graph import run_task_graph
        return run_task_graph(
            self, bundle, transient_input=transient_input, authorization=authorization,
            member_id=member_id, reference_hints=reference_hints,
        )

    def _remaining_seconds(self, deadline_at: float) -> float:
        return deadline_at - self._now()

    @staticmethod
    def _bounded_execution_budget(execution_budget: TaskExecutionBudget | None) -> TaskExecutionBudget:
        budget = execution_budget.model_copy(deep=True) if execution_budget is not None else TaskExecutionBudget()
        maximum = min(240, max(10, int(settings.agent_runtime_max_wall_clock_seconds)))
        if budget.max_wall_clock_seconds > maximum:
            budget = budget.model_copy(update={"max_wall_clock_seconds": maximum})
        return budget

    def _preflight_required_input_question(
        self,
        task: AgentTask,
        discovered: list[SkillDefinition],
        bundle: TaskRecordBundle,
        *,
        transient_input: str,
        reference_hints: Mapping[str, str],
    ) -> str | None:
        """Check declared Skill inputs before invoking the model.

        Capability discovery remains metadata-driven.  Only Skills that match
        the current goal/turn through their catalog metadata participate; the
        method never maps a keyword to a business action.  A required input is
        considered satisfied by a server-provided turn hint or a still-valid
        verified artifact from the Skill/prerequisite declared by the catalog.
        """

        # Relevance comes from the persisted, safe task goal.  The transient
        # instruction is deliberately excluded: it contains generic words
        # such as “事实/继续” used to guide the model and must not make an
        # unrelated Skill's input contract appear applicable.
        query = task.normalized_goal
        relevant = [
            skill
            for skill in discovered
            if skill.required_input_keys and discovery_score(skill, query) > 0
        ]
        if not relevant:
            return None

        now = self._now()
        verified_sources = {
            artifact.source_skill
            for artifact in bundle.artifacts
            if artifact.factuality == "verified" and artifact.expires_at > now
        }
        missing: list[str] = []
        for skill in relevant:
            allowed_sources = {skill.skill_id, *skill.prerequisite_skill_ids}
            for key in skill.required_input_keys:
                if key in reference_hints:
                    continue
                if verified_sources.intersection(allowed_sources):
                    continue
                if key not in missing:
                    missing.append(key)
        if not missing:
            return None

        questions = {
            "orderRef": "请提供订单标识，或从已展示的订单候选中选择一笔；确认后我再核验订单或物流事实。",
            "skuRef": "请提供商品候选或 SKU 标识；确认后我再核验库存事实。",
        }
        return " ".join(questions[key] for key in missing if key in questions) or "请补充当前受控能力所需的信息后继续。"

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
        if self._read_skill_allowlist is not None:
            selected = [
                skill
                for skill in selected
                if skill.action_mode != "read" or skill.skill_id in self._read_skill_allowlist
            ]
        known = {skill.skill_id for skill in selected}
        for artifact in bundle.artifacts[-8:]:
            if artifact.source_skill and artifact.source_skill not in known:
                skill = get_skill(artifact.source_skill)
                if skill is not None and skill.model_visible and (
                    skill.action_mode != "read"
                    or self._read_skill_allowlist is None
                    or skill.skill_id in self._read_skill_allowlist
                ):
                    selected.append(skill)
                    known.add(skill.skill_id)
        return selected[:8]

    def _validate_decision(
        self,
        decision: ExecutorDecision,
        task: AgentTask,
        discovered: list[SkillDefinition],
        bundle: TaskRecordBundle,
        *,
        reference_hints: Mapping[str, str] | None = None,
    ) -> None:
        discovered_ids = {skill.skill_id for skill in discovered}
        if decision.decision == "call_skill":
            if len(decision.skill_calls) > task.execution_budget.max_parallel_reads:
                raise TaskRuntimeError("一次调用的 Skill 数量超过并行预算。", code="parallel_budget_exceeded")
            if task.tool_calls + len(decision.skill_calls) > task.execution_budget.max_tool_calls:
                raise TaskRuntimeError("任务达到 Skill 调用预算。", code="tool_call_budget_exhausted")
            decision_skill_ids = {call.skill_id for call in decision.skill_calls}
            has_order_fact = any(
                artifact.kind == "order_fact" and artifact.factuality == "verified"
                for artifact in bundle.artifacts
            )
            # Logistics is an order-scoped fact.  When the catalog has exposed
            # the order reader, do not let a plan that requests both facts
            # silently finish after a logistics-only read.  A first-turn
            # parallel read of both remains valid; a logistics-only catalog
            # (for example an upstream failure fixture) is also preserved.
            if (
                "read_logistics" in decision_skill_ids
                and "read_order" in discovered_ids
                and "read_order" not in decision_skill_ids
                and not has_order_fact
            ):
                raise TaskRuntimeError(
                    "物流事实需要先绑定当前订单事实。",
                    code="required_order_fact_before_logistics",
                )
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
                self._validate_reference_arguments(
                    call.skill_id,
                    call.arguments,
                    bundle,
                    reference_hints=reference_hints,
                )
        if decision.decision == "spawn_subtask":
            skill = get_skill("spawn_subtask")
            if skill is None or skill.skill_id not in discovered_ids:
                raise TaskRuntimeError("子任务能力必须先经当前任务发现。", code="undiscovered_subtask_skill")
            if self._skill_call_count(bundle, skill.skill_id) >= skill.max_calls_per_task:
                raise TaskRuntimeError("当前任务已达到子任务上限。", code="skill_call_budget_exhausted")
            if task.tool_calls >= task.execution_budget.max_tool_calls:
                raise TaskRuntimeError("任务达到 Skill 调用预算。", code="tool_call_budget_exhausted")
            self._validate_skill_arguments(skill.skill_id, decision.action_arguments)
        if decision.decision == "propose_action":
            if decision.action_skill is None:
                raise TaskRuntimeError("行动提案缺少 Skill。", code="action_skill_missing")
            skill = get_skill(decision.action_skill)
            if skill is None or skill.action_mode not in {"draft", "commit", "async_task"}:
                raise TaskRuntimeError("行动 Skill 不在受控范围内。", code="action_skill_denied")
            if skill.model_visible is not True or skill.exposure != "model_visible":
                raise TaskRuntimeError("模型不能直接选择服务器内部执行器。", code="internal_executor_denied")
            if skill.skill_id not in discovered_ids:
                raise TaskRuntimeError("行动 Skill 必须先经当前任务发现。", code="undiscovered_action_skill")
            if not skill.requires_confirmation:
                raise TaskRuntimeError("行动 Skill 必须声明客户确认前置条件。", code="confirmation_contract_invalid")
            executor = confirmation_executor_skill(skill.skill_id)
            if executor is None:
                raise TaskRuntimeError(
                    "该行动尚未配置受控确认执行器。",
                    code="confirmation_executor_not_configured",
                )
            if not bundle.artifacts:
                raise TaskRuntimeError("没有已核验事实，不能形成业务行动提案。", code="action_without_evidence")
            if self._skill_call_count(bundle, skill.skill_id) >= skill.max_calls_per_task:
                raise TaskRuntimeError("当前行动 Skill 已达到该任务的调用上限。", code="skill_call_budget_exhausted")
            self._validate_skill_arguments(decision.action_skill, decision.action_arguments)
            required_keys = executor.confirmation_required_input_keys
            missing_keys = [
                key
                for key in required_keys
                if key not in decision.action_arguments or decision.action_arguments.get(key) in (None, "")
            ]
            if missing_keys:
                error = TaskRuntimeError(
                    "行动提案缺少确认执行所需字段。",
                    code="required_action_input_missing",
                    missing_keys=missing_keys,
                )
                raise error
            if skill.skill_id == "create_after_sales_draft":
                order_fact_ref = decision.action_arguments.get("orderFactRef")
                verified_order_refs = {
                    artifact.reference
                    for artifact in bundle.artifacts
                    if artifact.kind == "order_fact" and artifact.factuality == "verified" and artifact.expires_at > self._now()
                }
                if not isinstance(order_fact_ref, str) or order_fact_ref not in verified_order_refs:
                    raise TaskRuntimeError("提交行动必须引用当前任务的已核验订单事实。", code="commit_without_verified_order_fact")
            elif skill.skill_id == "open_human_case":
                refs = decision.action_arguments.get("artifactRefs")
                reason = decision.action_arguments.get("reasonCode")
                owned_refs = {
                    artifact.reference
                    for artifact in bundle.artifacts
                    if artifact.expires_at > self._now()
                }
                if (
                    not isinstance(refs, list)
                    or not refs
                    or not all(isinstance(ref, str) and ref in owned_refs for ref in refs)
                    or reason not in {"tool_failure", "insufficient_evidence", "manual_review"}
                ):
                    raise TaskRuntimeError("人工协同提案必须引用当前任务的安全 Artifact。", code="handoff_artifact_reference_invalid")
        if decision.decision == "revise_plan":
            if task.plan_version >= 99:
                raise TaskRuntimeError("计划版本已达到上限。", code="plan_version_exhausted")
            for node in decision.new_plan_nodes:
                for skill_id in node.required_skills:
                    if skill_id != "discover_skills" and get_skill(skill_id) is None:
                        raise TaskRuntimeError("重规划引用了未知 Skill。", code="unknown_skill")
        if decision.decision == "finish" and not decision.reason_summary:
            raise TaskRuntimeError("完成决策缺少用户可见摘要。", code="finish_summary_missing")
        if decision.decision == "finish" and self._requires_catalog_comparison(task.normalized_goal):
            artifact_kinds = {artifact.kind for artifact in bundle.artifacts if artifact.factuality in {"verified", "derived"}}
            if not {"catalog_fact", "sku_comparison"}.issubset(artifact_kinds):
                raise TaskRuntimeError(
                    "商品比较尚未完成候选搜索和规格对比。",
                    code="catalog_comparison_incomplete",
                )
        if decision.decision == "finish" and self._has_blocking_limitation(task.limitation_codes):
            raise TaskRuntimeError(
                "当前任务存在未解决的 Skill 或事实失败，不能宣称完成。",
                code="finish_after_dependency_failure",
            )

    @staticmethod
    def _has_blocking_limitation(limitation_codes: list[str]) -> bool:
        advisory = {
            "context_curator_unavailable",
            "resolution_critic_unavailable",
        }
        return any(code not in advisory for code in limitation_codes)

    @staticmethod
    def _requires_catalog_comparison(goal: str) -> bool:
        normalized = str(goal or "").lower()
        return any(token in normalized for token in ("比较商品", "比较两个", "商品候选", "sku", "规格对比")) and any(
            token in normalized for token in ("比较", "对比", "compare")
        )

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
            "create_after_sales_draft": {"proposalRef", "orderFactRef", "applicationType"},
            "amend_after_sales_draft": {"proposalRef"},
            # The Runtime owns the idempotency key.  It must never be accepted
            # from an Executor decision, even when the value has a valid shape.
            "commit_after_sales_action": {"actionRef", "proposalRef", "orderFactRef", "applicationType"},
            "open_human_case": {"artifactRefs", "reasonCode"},
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

    def _validate_reference_arguments(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        bundle: TaskRecordBundle,
        *,
        reference_hints: Mapping[str, str] | None = None,
    ) -> None:
        """Accept only server-provided or current-task artifact references."""

        if skill_id not in {"read_order", "read_logistics", "read_inventory"}:
            return
        key = "skuRef" if skill_id == "read_inventory" else "orderRef"
        supplied = arguments.get(key) or arguments.get("sku_id" if key == "skuRef" else "order_sn")
        if not isinstance(supplied, str) or not supplied.strip():
            return
        # ``self._reference_hints`` are server-approved opaque references
        # (used by synthetic/live fixtures). A value parsed from the current
        # user message is a syntax-validated, user-visible identifier and is
        # intentionally accepted for this turn; it is never persisted.
        # The current-turn hints are syntax-validated references explicitly
        # supplied by the user.  They may be used for this request only; they
        # are still subject to the Java gateway's owner/eligibility checks and
        # are never persisted as task state.  Server-provided and artifact
        # references remain the preferred source.
        known = set(self._reference_hints.values())
        known.update(str(value) for value in (reference_hints or {}).values())
        known.update(artifact.reference for artifact in bundle.artifacts)
        if known and supplied not in known:
            raise TaskRuntimeError(
                "Skill 参数不是当前服务端提供的 opaque reference。",
                code="unapproved_reference",
            )

    @staticmethod
    def _reference_hints_from_input(message: str) -> dict[str, str]:
        """Extract only explicitly formatted, user-visible references.

        The result is a turn-local server hint. It is intentionally limited to
        the existing conservative identifier parsers; it does not infer an
        order, SKU, intent, permission, or business state from free text.
        """

        hints: dict[str, str] = {}
        order = extract_order_sn(message)
        if order.value:
            hints["orderRef"] = order.value
        sku = extract_sku_id(message)
        if sku.value:
            hints["skuRef"] = sku.value
        # Synthetic/demo references are opaque but have an explicit, bounded
        # syntax.  Accept only the user-written ``ref-order-*`` and
        # ``ref-sku-*`` forms; this is identifier parsing, not intent or
        # ownership inference.
        explicit = re.findall(r"\b(ref-(?:order|sku)-[A-Za-z0-9_-]+)\b", message, re.IGNORECASE)
        for value in explicit:
            key = "skuRef" if value.lower().startswith("ref-sku-") else "orderRef"
            # Prefer the explicitly typed opaque form over the generic SKU
            # parser, which may otherwise see the ``sku-*`` suffix.
            hints[key] = value
        return hints

    @staticmethod
    def _read_signature(skill_id: str, arguments: Mapping[str, Any]) -> str:
        return f"{skill_id}:{json.dumps(dict(arguments), ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"

    @classmethod
    def _duplicate_read_decision(
        cls,
        decision: ExecutorDecision,
        executed_signatures: set[str],
    ) -> bool:
        if decision.decision != "call_skill" or not decision.skill_calls:
            return False
        signatures = [
            cls._read_signature(call.skill_id, call.arguments)
            for call in decision.skill_calls
            if (get_skill(call.skill_id) is not None and get_skill(call.skill_id).action_mode == "read")
        ]
        return bool(signatures) and all(signature in executed_signatures for signature in signatures)

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
        # 预留调用计数，崩溃不回退预算；只读副作用同样不能无界重放。
        bundle.task.tool_calls += len(calls)
        self._save(bundle)
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
            code = observation.safe_facts.get("failure_code") or f"skill_{observation.status}"
            if code not in bundle.task.limitation_codes:
                bundle.task.limitation_codes.append(code)
        return artifact

    @staticmethod
    def _explicit_after_sales_type(customer_text: str) -> str | None:
        """Accept an explicit customer declaration, never a bare keyword.

        This parser is deliberately limited to an action/type declaration in
        the customer task or continuation. It never reads artifacts, product
        descriptions or policy summaries, so those sources cannot choose an
        application type on the customer's behalf.
        """

        if not isinstance(customer_text, str):
            return None
        declarations = (
            (r"(?:申请|我要|我想|需要|选择|售后类型(?:是|为)?|继续形成)(?:取消退款)", "cancel_refund"),
            (r"(?:申请|我要|我想|需要|选择|售后类型(?:是|为)?|继续形成)(?:退货退款)", "return_refund"),
            (r"(?:申请|我要|我想|需要|选择|售后类型(?:是|为)?|继续形成)(?:换货)", "exchange"),
            (r"(?:申请|我要|我想|需要|选择|售后类型(?:是|为)?|继续形成)(?:维修)", "repair"),
        )
        for pattern, application_type in declarations:
            if re.search(pattern, customer_text):
                return application_type
        return None

    def _conditional_draft_for_insufficient_policy_evidence(
        self,
        bundle: TaskRecordBundle,
        discovered: list[SkillDefinition],
        transient_input: str,
    ) -> ExecutorDecision | None:
        """Create only a conditional draft after the declared safe boundary.

        Insufficient policy evidence remains visible and never becomes policy
        support. A draft is allowed solely when Java has verified the order,
        the customer explicitly named an application type, and a read-only
        candidate already exists. Confirmation still routes through the
        server-selected Java executor and its fresh eligibility check.
        """

        task = bundle.task
        if "insufficient_evidence" not in task.limitation_codes:
            return None
        if "create_after_sales_draft" not in {skill.skill_id for skill in discovered}:
            return None
        application_type = self._explicit_after_sales_type(f"{task.normalized_goal} {transient_input}")
        if application_type is None:
            return None
        order_fact = next(
            (
                artifact
                for artifact in reversed(bundle.artifacts)
                if artifact.kind == "order_fact"
                and artifact.factuality == "verified"
                and artifact.expires_at > self._now()
            ),
            None,
        )
        has_candidate = any(
            artifact.kind == "resolution_candidate" and artifact.expires_at > self._now()
            for artifact in bundle.artifacts
        )
        if order_fact is None or not has_candidate:
            return None
        return ExecutorDecision(
            decision="propose_action",
            reason_summary=(
                "政策证据不足；已按您明确的售后类型生成有条件待确认草案。"
                "确认后仍由 Java 重新核验身份、订单状态和售后资格，不保证处理成功。"
            ),
            action_skill="create_after_sales_draft",
            action_arguments={
                "orderFactRef": order_fact.reference,
                "applicationType": application_type,
            },
        )

    def _refresh_context(
        self,
        bundle: TaskRecordBundle,
        discovered: list[SkillDefinition],
        *,
        deadline_at: float | None = None,
    ) -> ContextPack | None:
        plan = bundle.latest_plan()
        if plan is None:
            return None
        remaining = self._remaining_seconds(deadline_at) if deadline_at is not None else settings.context_timeout_seconds
        if remaining <= 0:
            raise RuntimeModelError("任务运行时间达到安全上限。", role="context_curator", category="runtime_deadline_exceeded")
        curator_arguments = {
            "task": bundle.task,
            "plan": plan,
            "artifacts": bundle.artifacts[-24:],
            "memory_hints": bundle.memory_hints[-8:],
            "available_skills": [skill.skill_id for skill in discovered],
        }
        bundle.task.context_model_calls += 1
        self._save(bundle)
        try:
            with capture_llm_metrics(
                timeout_seconds=min(settings.context_timeout_seconds, remaining),
                max_attempts=1,
            ):
                pack = self._curator.build_pack(**curator_arguments)
        except RuntimeModelError:
            pack = self._curator.build_pack(**curator_arguments, use_provider=False)
            bundle.context_packs.append(pack)
            bundle.task.context_pack_ref = pack.pack_id
            bundle.task.working_memory_ref = pack.pack_id
            bundle.memory_hints.extend(pack.memory_hints[-4:])
            raise
        bundle.context_packs.append(pack)
        bundle.task.context_pack_ref = pack.pack_id
        bundle.task.working_memory_ref = pack.pack_id
        bundle.memory_hints.extend(pack.memory_hints[-4:])
        return pack

    def _auxiliary_failure_must_block(
        self,
        exc: RuntimeModelError,
        deadline_at: float | None,
    ) -> bool:
        if deadline_at is not None and self._remaining_seconds(deadline_at) <= 0:
            return True
        return exc.category in {
            "runtime_deadline_exceeded",
            "budget_exhausted",
            "ledger_malformed",
            "missing_configuration",
            "provider_http",
        }

    def _block_auxiliary_failure(
        self,
        bundle: TaskRecordBundle,
        exc: RuntimeModelError,
        deadline_at: float | None,
    ) -> None:
        failure_code = (
            "runtime_deadline_exceeded"
            if deadline_at is not None and self._remaining_seconds(deadline_at) <= 0
            else f"model_{exc.category}"
        )
        self._block(
            bundle,
            failure_code,
            "任务辅助模型遇到不可降级的基础设施错误，已安全停止；未执行业务写入。",
        )
        record_trace(
            "task_runtime",
            "auxiliary_model_unavailable",
            bundle.task.task_ref,
            role=exc.role,
            result_kind="blocked",
            error_category=exc.category,
            **exc.diagnostics,
        )

    def _record_auxiliary_degradation(
        self,
        bundle: TaskRecordBundle,
        exc: RuntimeModelError,
    ) -> None:
        limitation = f"{exc.role}_unavailable"
        if limitation not in bundle.task.limitation_codes:
            bundle.task.limitation_codes.append(limitation)
        self._append_event(
            bundle,
            "plan_updated",
            "辅助分析暂不可用；继续使用已经核验的事实和服务端合同。",
        )
        record_trace(
            "task_runtime",
            "auxiliary_model_degraded",
            bundle.task.task_ref,
            role=exc.role,
            result_kind="degraded",
            error_category=exc.category,
            **exc.diagnostics,
        )

    def _maybe_critic(self, bundle: TaskRecordBundle, *, deadline_at: float | None = None) -> None:
        plan = bundle.latest_plan()
        if plan is None:
            return
        remaining = self._remaining_seconds(deadline_at) if deadline_at is not None else settings.critic_timeout_seconds
        if remaining <= 0:
            raise RuntimeModelError("任务运行时间达到安全上限。", role="resolution_critic", category="runtime_deadline_exceeded")
        bundle.task.critic_calls += 1
        self._save(bundle)
        with capture_llm_metrics(
            timeout_seconds=min(settings.critic_timeout_seconds, remaining),
            max_attempts=1,
        ):
            critique = self._critic.evaluate(task_ref=bundle.task.task_ref, plan=plan, artifacts=bundle.artifacts[-12:])
        if critique is None:
            return
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
        child_bundle = TaskRecordBundle(task=child, graph_version=TASK_GRAPH_VERSION)
        child_bundle.plans.append(build_initial_plan(child))
        self._append_event(child_bundle, "task_created", "已创建受控子任务，等待上级任务继续安排。")
        self._save(child_bundle)
        from app.runtime.task_graph import publish_task_checkpoint
        publish_task_checkpoint(self, child_bundle)
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
        if decision.action_skill == 'open_human_case' and bundle.handoff is None:
            bundle.handoff=HandoffContext(request_ref=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                scope_key=hashlib.sha256((bundle.task.owner_ref+':'+bundle.task.task_ref).encode()).hexdigest(),
                source='system_suggested_accepted',channel='chat',stage=bundle.task.status,
                linked_task_ref=bundle.task.task_ref,plan_version=bundle.task.plan_version,
                completed_steps=sum(node.status=='completed' for node in bundle.plans[-1].nodes) if bundle.plans else 0,
                verified_evidence_count=sum(artifact.factuality=='verified' and artifact.expires_at>self._now() for artifact in bundle.artifacts))
        skill = get_skill(decision.action_skill or "")
        if skill is None:
            raise TaskRuntimeError("行动 Skill 不存在。", code="action_skill_denied")
        executor = confirmation_executor_skill(skill.skill_id)
        if executor is None:
            raise TaskRuntimeError("该行动尚未配置受控确认执行器。", code="confirmation_executor_not_configured")
        # Action arguments are a server-side vault entry. They contain only
        # opaque references, not order numbers, credentials or raw messages.
        action_arguments = dict(decision.action_arguments)
        # The model may never choose an idempotency key. It is generated only
        # during confirmation, after the proposal hash and current facts are
        # revalidated by the Runtime.
        assert_safe_action_arguments(
            action_arguments,
            allow_generated_idempotency_key=skill.action_mode == "commit",
            allowed_opaque_references={artifact.reference for artifact in bundle.artifacts},
        )
        if skill.skill_id == 'open_human_case' and bundle.handoff:
            action_arguments['handoffProjectionHash']=hashlib.sha256(bundle.handoff.model_dump_json(exclude={'case_ref'}).encode()).hexdigest()
        current_proposal = bundle.action_proposal
        if current_proposal is not None:
            # A natural-language amendment must use the same immutable
            # version chain as the structured PATCH endpoint.  Never silently
            # overwrite a pending gate: retain the old proposal as a
            # superseded history record and bind the task only to the new
            # proposal.  The old arguments remain server-side and cannot be
            # confirmed through the current gate.
            bundle.action_proposal_history.append(
                current_proposal.model_copy(
                    update={
                        "confirmation_status": "superseded",
                        "updated_at": self._now(),
                    }
                )
            )
            bundle.action_proposal_history = bundle.action_proposal_history[-32:]
        arguments_ref = new_arguments_ref()
        bundle.action_arguments[arguments_ref] = action_arguments
        content_hash = hashlib.sha256(
            json.dumps(action_arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        proposal = ActionProposal(
            proposal_id=new_proposal_id(),
            revision=(current_proposal.revision + 1) if current_proposal is not None else 1,
            supersedes_proposal_ref=(current_proposal.proposal_ref if current_proposal is not None else None),
            task_id=bundle.task.task_id,
            action_skill=skill.skill_id,
            confirmation_executor_skill_id=executor.skill_id,
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

    @staticmethod
    def _action_input_question(missing_keys: list[str]) -> str:
        questions = {
            "orderFactRef": "请先补充或选择一笔已核验订单。",
            "applicationType": "请补充售后类型：取消退款、退货退款、换货或维修。",
        }
        return " ".join(questions[key] for key in missing_keys if key in questions) or "请补充方案执行所需的信息后继续。"

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
        from app.runtime.task_graph import project_task
        task = project_task(self, bundle)
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
            proposal_arguments = bundle.action_arguments.get(bundle.action_proposal.arguments_ref, {})
            application_type = proposal_arguments.get("applicationType") if isinstance(proposal_arguments, dict) else None
            type_labels = {
                "cancel_refund": "取消退款",
                "return_refund": "退货退款",
                "exchange": "换货",
                "repair": "维修",
            }
            action_view = AgentTaskActionView(
                action_skill=bundle.action_proposal.action_skill,
                expected_effect=bundle.action_proposal.expected_effect,
                user_explanation=bundle.action_proposal.user_explanation,
                confirmation_status=bundle.action_proposal.confirmation_status,
                proposal_ref=bundle.action_proposal.proposal_ref or "",
                revision=bundle.action_proposal.revision,
                application_type=application_type if isinstance(application_type, str) else None,
                application_type_label=type_labels.get(application_type) if isinstance(application_type, str) else None,
                evidence_summaries=[
                    artifact.summary for artifact in bundle.artifacts
                    if artifact.reference in set(bundle.action_proposal.evidence_refs)
                ][:4],
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
            handoff_topic=bundle.handoff.topic if bundle.handoff else None,
            handoff_reason=bundle.handoff.reason if bundle.handoff else None,
            handoff_problem=bundle.handoff.problem_projection if bundle.handoff else None,
            handoff_context_preview=[f['text'] for f in (bundle.handoff.safe_input_snapshot or {}).get('fragments',[])] if bundle.handoff else [],
            handoff_case_ref=bundle.handoff.case_ref if bundle.handoff else None,
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
            execution_metrics=AgentTaskExecutionMetricsView(
                model_calls=task.model_calls,
                context_model_calls=task.context_model_calls,
                critic_calls=task.critic_calls,
                tool_calls=task.tool_calls,
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
