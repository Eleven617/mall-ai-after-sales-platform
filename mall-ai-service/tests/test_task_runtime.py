"""Contract tests for the v3 E-Commerce Task Runtime.

These tests use a scripted provider and synthetic gateway.  They exercise the
same runtime contracts that production uses, without a model key, Java service
or database.  Every assertion is about a concrete safety or recovery risk;
there are no keyword fallbacks or no-op count-only cases here.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.runtime.providers import CuratorModelOutput, RuntimeModelError, ScriptedRuntimeProvider
from app.runtime.reference_vault import RuntimeReferenceVault
from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
from app.runtime.task_store import InMemoryTaskStore
from app.schemas.agent_task import AgentTask, ExecutorDecision, SkillCall, TaskExecutionBudget, TaskPlan
from app.runtime.task_planner import build_initial_plan
from app.runtime.task_store import TaskRecordBundle, owner_ref_for_member, session_ref_for_session
from app.skills.catalog import get_skill
from app.skills.commerce_gateway import (
    SafeCommerceSkillGateway,
    SkillObservation,
    SyntheticSkillGateway,
)


AUTHORIZATION = "Bearer synthetic-runtime-credential"
MEMBER_ID = 71
SESSION_ID = "synthetic-runtime-session"


def _observation(
    *,
    kind: str = "order_fact",
    reference: str = "fact-abcdefghijklmnopqrstuvwxyz",
    status: str = "succeeded",
    factuality: str = "verified",
    summary: str = "Java 已核验当前账号的合成订单事实。",
) -> SkillObservation:
    return SkillObservation(
        status=status,
        artifact_kind=kind,
        summary=summary,
        reference=reference,
        source_version="v1",
        factuality=factuality,
    )


class RecordingGateway:
    def __init__(self, observations: dict[str, SkillObservation]) -> None:
        self.observations = observations
        self.invocations: list[tuple[str, dict]] = []
        self.commits: list[tuple[str, dict]] = []

    def invoke(self, skill_id, arguments, **_kwargs):
        self.invocations.append((skill_id, dict(arguments)))
        return self.observations[skill_id]

    def commit(self, skill_id, arguments, **_kwargs):
        self.commits.append((skill_id, dict(arguments)))
        return self.observations[skill_id]


def _runtime(provider, gateway) -> TaskRuntime:
    return TaskRuntime(store=InMemoryTaskStore(), provider=provider, gateway=gateway)


def _decision(*, name: str, summary: str, calls=None, action_skill=None, action_arguments=None, question=None):
    return ExecutorDecision(
        decision=name,
        reason_summary=summary,
        skill_calls=calls or [],
        action_skill=action_skill,
        action_arguments=action_arguments or {},
        user_question=question,
    )


def test_runtime_runs_dynamic_read_then_finishes_without_persisting_raw_goal() -> None:
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="先读取当前账号可核验的订单事实。",
                calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})],
            ),
            _decision(name="finish", summary="已完成订单事实核验并给出下一步。"),
        ]
    )
    gateway = RecordingGateway({"read_order": _observation()})
    runtime = _runtime(provider, gateway)

    result = runtime.create_task(
        session_id=SESSION_ID,
        goal="请核验合成订单 123456789012 的状态，authorization=should-not-persist",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "completed"
    assert result.view.goal == "请核验合成订单 [业务标识] 的状态，[已隐藏凭证]"
    assert result.view.artifacts[0].kind == "order_fact"
    assert result.view.artifacts[0].summary == "Java 已核验当前账号的合成订单事实。"
    assert gateway.invocations == [("read_order", {"orderRef": "ref-order-alpha"})]
    bundle = runtime._store.load_owned(  # noqa: SLF001 - validates persisted projection
        result.view.task_ref,
        runtime._store._items[result.view.task_ref].task.owner_ref,  # type: ignore[attr-defined] # noqa: SLF001
    )
    persisted = str(bundle.model_dump())
    assert "123456789012" not in persisted
    assert "should-not-persist" not in persisted


def test_runtime_rejects_unknown_skill_before_gateway_invocation() -> None:
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="尝试调用未注册能力。",
                calls=[SkillCall(skill_id="invented_skill", arguments={})],
            )
        ]
    )
    gateway = RecordingGateway({})

    result = _runtime(provider, gateway).create_task(
        session_id=SESSION_ID,
        goal="查询合成订单",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "blocked"
    assert "unknown_skill" in result.view.limitation_codes
    assert gateway.invocations == []


def test_model_failure_safely_blocks_before_any_skill_or_action() -> None:
    class FailingProvider:
        def decide(self, _context):
            raise RuntimeModelError("synthetic outage", role="commerce_executor", category="timeout")

        def curate(self, _context):
            raise AssertionError("curator must not run")

        def critique(self, _context):
            raise AssertionError("critic must not run")

    gateway = RecordingGateway({})
    result = _runtime(FailingProvider(), gateway).create_task(
        session_id=SESSION_ID,
        goal="查询合成订单",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "blocked"
    assert "model_timeout" in result.view.limitation_codes
    assert gateway.invocations == []
    assert gateway.commits == []


def test_commit_requires_current_verified_order_fact_and_explicit_confirmation() -> None:
    order_reference = "fact-order-abcdefghijklmnopqrstuvwxyz"
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="先核验订单事实。",
                calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})],
            ),
            _decision(
                name="propose_action",
                summary="已形成一个待确认的退货退款行动。",
                action_skill="commit_after_sales_action",
                action_arguments={
                    "orderFactRef": order_reference,
                    "applicationType": "return_refund",
                },
            ),
        ]
    )
    gateway = RecordingGateway(
        {
            "read_order": _observation(reference=order_reference),
            "commit_after_sales_action": _observation(
                kind="action_result",
                reference="action-abcdefghijklmnopqrstuvwxyz",
                summary="Java 已返回合成售后提交结果。",
            ),
        }
    )
    runtime = _runtime(provider, gateway)

    proposal = runtime.create_task(
        session_id=SESSION_ID,
        goal="核验订单后准备售后处理方案",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert proposal.view.status == "ready_to_commit"
    assert proposal.view.action is not None
    assert proposal.view.action.confirmation_status == "awaiting_confirmation"
    assert gateway.commits == []

    committed = runtime.confirm_action(
        task_ref=proposal.view.task_ref,
        confirmation="confirm",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert committed.view.status == "executing"
    assert len(gateway.commits) == 1
    _, arguments = gateway.commits[0]
    assert arguments["orderFactRef"] == order_reference
    assert arguments["applicationType"] == "return_refund"
    assert len(arguments["idempotencyKey"]) == 32


def test_commit_proposal_cannot_reference_another_task_or_unverified_fact() -> None:
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="查询的是不可用事实。",
                calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})],
            ),
            _decision(
                name="propose_action",
                summary="不应提交未核验事实。",
                action_skill="commit_after_sales_action",
                action_arguments={
                    "orderFactRef": "fact-not-owned-abcdefghijklmnopqrstuvwxyz",
                    "applicationType": "exchange",
                },
            ),
        ]
    )
    gateway = RecordingGateway(
        {
            "read_order": _observation(
                reference="fact-unavailable-abcdefghijklmnopqrstuvwxyz",
                status="unavailable",
                factuality="unavailable",
                summary="订单事实暂时不可用。",
            )
        }
    )

    result = _runtime(provider, gateway).create_task(
        session_id=SESSION_ID,
        goal="核验订单后准备售后处理方案",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "blocked"
    assert "commit_without_verified_order_fact" in result.view.limitation_codes
    assert gateway.commits == []


def test_executor_cannot_supply_the_runtime_idempotency_key() -> None:
    """MALL-R2: a model-shaped action cannot select its own replay key."""

    order_reference = "fact-order-abcdefghijklmnopqrstuvwxyz"
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="先核验当前账号订单事实。",
                calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})],
            ),
            _decision(
                name="propose_action",
                summary="错误地尝试自行指定提交幂等键。",
                action_skill="commit_after_sales_action",
                action_arguments={
                    "orderFactRef": order_reference,
                    "applicationType": "return_refund",
                    "idempotencyKey": "f" * 32,
                },
            ),
        ]
    )
    gateway = RecordingGateway({"read_order": _observation(reference=order_reference)})

    result = _runtime(provider, gateway).create_task(
        session_id=SESSION_ID,
        goal="核验订单后准备售后处理方案",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "blocked"
    assert "unknown_skill_argument" in result.view.limitation_codes
    assert result.view.action is None
    assert gateway.commits == []


def test_executor_cannot_call_a_draft_skill_without_an_action_proposal() -> None:
    """MALL-R2: non-read Skills never bypass the ActionProposal boundary."""

    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="错误地直接创建售后草案。",
                calls=[SkillCall(skill_id="create_after_sales_draft", arguments={"proposalRef": "proposal-abcdefghi"})],
            )
        ]
    )
    gateway = RecordingGateway({})

    result = _runtime(provider, gateway).create_task(
        session_id=SESSION_ID,
        goal="准备一个退货退款草案",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "blocked"
    assert "action_requires_proposal" in result.view.limitation_codes
    assert gateway.invocations == []
    assert gateway.commits == []


def test_parallel_read_calls_cannot_cross_the_remaining_tool_budget() -> None:
    """MALL-R2: a multi-call decision is rejected atomically before reads."""

    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="错误地尝试在剩余一个预算内并发读取两项事实。",
                calls=[
                    SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"}),
                    SkillCall(skill_id="read_logistics", arguments={"orderRef": "ref-order-alpha"}),
                ],
            )
        ]
    )
    gateway = RecordingGateway({})
    runtime = _runtime(provider, gateway)
    task_id = "task-" + "a" * 16
    task = AgentTask(
        task_id=task_id,
        task_ref="taskref-" + "a" * 16,
        owner_ref=owner_ref_for_member(MEMBER_ID),
        session_ref=session_ref_for_session(SESSION_ID),
        goal_digest="b" * 64,
        normalized_goal="查询合成订单与物流",
        status="executing",
        plan_version=1,
        execution_budget=TaskExecutionBudget(max_tool_calls=1),
        tool_calls=0,
        expires_at=9_999_999_999,
    )
    bundle = TaskRecordBundle(task=task, plans=[build_initial_plan(task)])
    task.tool_calls = 0
    with pytest.raises(TaskRuntimeError) as error:
        runtime._validate_decision(  # noqa: SLF001 - contract boundary unit test
            _decision(
                name="call_skill",
                summary="剩余预算不足时禁止并发读取。",
                calls=[
                    SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"}),
                    SkillCall(skill_id="read_logistics", arguments={"orderRef": "ref-order-alpha"}),
                ],
            ),
            task,
            [get_skill("read_order"), get_skill("read_logistics")],
            bundle,
        )
    assert error.value.code == "tool_call_budget_exhausted"
    assert gateway.invocations == []


def test_spawn_subtask_creates_a_real_owner_scoped_task_without_gateway_write() -> None:
    """A Runtime subtask is persisted safely; it is not a fabricated async reply."""

    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(name="spawn_subtask", summary="调查库存替代方案。"),
            _decision(name="finish", summary="上级任务已记录后续调查安排。"),
        ]
    )
    gateway = RecordingGateway({})
    runtime = _runtime(provider, gateway)

    parent = runtime.create_task(
        session_id=SESSION_ID,
        goal="创建子任务调查库存替代方案",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    owner_ref = runtime._store._items[parent.view.task_ref].task.owner_ref  # type: ignore[attr-defined] # noqa: SLF001
    tasks = runtime._store.list_owned(owner_ref)  # noqa: SLF001 - validates store persistence
    child = next(item for item in tasks if item.task.task_ref != parent.view.task_ref)
    parent_bundle = runtime._store.load_owned(parent.view.task_ref, owner_ref)  # noqa: SLF001

    assert child.task.parent_task_id == parent_bundle.task.task_id
    assert child.task.status == "waiting_for_async_task"
    assert any(artifact.kind == "async_task" for artifact in parent_bundle.artifacts)
    assert gateway.invocations == []
    assert gateway.commits == []


def test_context_pack_is_present_on_the_executor_turn_after_a_read() -> None:
    """MALL-R4: Curator output is actually reused instead of only being stored."""

    class CapturingProvider:
        def __init__(self) -> None:
            self.contexts = []
            self.decisions = [
                _decision(
                    name="call_skill",
                    summary="读取已核验订单事实。",
                    calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})],
                ),
                _decision(name="finish", summary="已完成事实核验。"),
            ]

        def decide(self, context):
            self.contexts.append(context)
            return self.decisions.pop(0)

        def curate(self, _context):
            return CuratorModelOutput(
                verified_facts=["Java 已核验当前账号的合成订单事实。"],
                memory_hints=["后续仅复用仍有效的事实引用。"],
            )

        def critique(self, _context):
            raise AssertionError("critic should not run for one read")

    provider = CapturingProvider()
    result = _runtime(provider, RecordingGateway({"read_order": _observation()})).create_task(
        session_id=SESSION_ID,
        goal="核验合成订单事实",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "completed"
    assert len(provider.contexts) == 2
    second = provider.contexts[1]
    assert second.context_pack_version == 1
    assert second.context_verified_facts == ["Java 已核验当前账号的合成订单事实。"]
    assert second.memory_hints == ["后续仅复用仍有效的事实引用。"]


def test_task_memory_skill_is_owner_scoped_and_never_calls_gateway() -> None:
    """MALL-R4: memory lookup is a Runtime-safe projection, not a tool payload."""

    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(name="finish", summary="此前任务已完成，用户偏好记录为脱敏摘要。"),
            _decision(
                name="call_skill",
                summary="查询当前账号的脱敏历史任务摘要。",
                calls=[SkillCall(skill_id="search_task_memory", arguments={"query": "历史"})],
            ),
            _decision(name="finish", summary="已依据可安全复用的历史摘要完成处理。"),
        ]
    )
    gateway = RecordingGateway({})
    runtime = _runtime(provider, gateway)

    runtime.create_task(
        session_id=SESSION_ID,
        goal="完成一个合成历史任务",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )
    result = runtime.create_task(
        session_id=SESSION_ID,
        goal="查询上次处理的历史记忆",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    owner_ref = runtime._store._items[result.view.task_ref].task.owner_ref  # type: ignore[attr-defined] # noqa: SLF001
    bundle = runtime._store.load_owned(result.view.task_ref, owner_ref)  # noqa: SLF001
    memory_artifact = next(artifact for artifact in bundle.artifacts if artifact.kind == "memory_hint")
    assert memory_artifact.factuality == "derived"
    assert "Bearer" not in memory_artifact.summary
    assert "token" not in memory_artifact.summary.lower()
    assert gateway.invocations == []


def test_task_memory_survives_a_fresh_runtime_when_task_store_persists() -> None:
    """MALL-R4: episodic hints are persisted, not only kept in process RAM."""

    shared_store = InMemoryTaskStore()
    first = TaskRuntime(
        store=shared_store,
        provider=ScriptedRuntimeProvider(
            decisions=[_decision(name="finish", summary="已完成合成订单异常核验。")]
        ),
        gateway=RecordingGateway({}),
    )
    first.create_task(
        session_id=SESSION_ID,
        goal="完成合成订单异常核验",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    gateway = RecordingGateway({})
    restarted = TaskRuntime(
        store=shared_store,
        provider=ScriptedRuntimeProvider(
            decisions=[
                _decision(
                    name="call_skill",
                    summary="查询当前账号可安全复用的任务摘要。",
                    calls=[SkillCall(skill_id="search_task_memory", arguments={"query": "订单异常"})],
                ),
                _decision(name="finish", summary="已读取脱敏历史摘要。"),
            ]
        ),
        gateway=gateway,
    )
    result = restarted.create_task(
        session_id=SESSION_ID,
        goal="查找上次的订单异常处理结果",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    assert result.view.status == "completed"
    bundle = shared_store.load_owned(result.view.task_ref, owner_ref_for_member(MEMBER_ID))
    memory = next(item for item in bundle.artifacts if item.kind == "memory_hint")
    assert memory.factuality == "derived"
    assert gateway.invocations == []


def test_task_owner_cannot_read_another_members_task() -> None:
    provider = ScriptedRuntimeProvider(
        decisions=[_decision(name="finish", summary="合成任务已完成。")]
    )
    runtime = _runtime(provider, RecordingGateway({}))
    created = runtime.create_task(
        session_id=SESSION_ID,
        goal="完成合成任务",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )

    with pytest.raises(TaskRuntimeError) as error:
        runtime.get_task(
            task_ref=created.view.task_ref,
            member_id=MEMBER_ID + 1,
            authorization=AUTHORIZATION,
        )

    assert error.value.code == "task_not_found"


def test_runtime_reference_vault_is_task_owner_bound_and_expiry_safe() -> None:
    now = [1000.0]
    vault = RuntimeReferenceVault(now_fn=lambda: now[0])
    vault.put(
        reference="fact-abcdefghijklmnopqrstuvwxyz",
        owner_ref="owner-abcdefghijklmnopqrstuvwxyz",
        task_ref="taskref-abcdefghijklmnop",
        kind="order_sn",
        value="synthetic-order-ref",
        ttl_seconds=5,
    )

    assert vault.resolve(
        reference="fact-abcdefghijklmnopqrstuvwxyz",
        owner_ref="owner-abcdefghijklmnopqrstuvwxyz",
        task_ref="taskref-abcdefghijklmnop",
        kind="order_sn",
    ) == "synthetic-order-ref"
    assert vault.resolve(
        reference="fact-abcdefghijklmnopqrstuvwxyz",
        owner_ref="owner-otherabcdefghijklmnop",
        task_ref="taskref-abcdefghijklmnop",
        kind="order_sn",
    ) is None
    now[0] += 6
    assert vault.resolve(
        reference="fact-abcdefghijklmnopqrstuvwxyz",
        owner_ref="owner-abcdefghijklmnopqrstuvwxyz",
        task_ref="taskref-abcdefghijklmnop",
        kind="order_sn",
    ) is None


def test_java_backed_gateway_rechecks_eligibility_before_confirmed_write() -> None:
    vault = RuntimeReferenceVault()
    gateway = SafeCommerceSkillGateway(reference_vault=vault)
    task_ref = "taskref-abcdefghijklmnop"
    with patch("app.skills.commerce_gateway.get_order_snapshot", return_value={"status": "已支付", "product_names": ["合成商品"]}), patch(
        "app.skills.commerce_gateway.check_after_sales_eligibility",
        return_value=SimpleNamespace(decision="eligible_to_apply"),
    ) as eligibility, patch(
        "app.skills.commerce_gateway.create_after_sales_application",
        return_value=SimpleNamespace(application_id=23, status="pending_review"),
    ) as create:
        fact = gateway.invoke(
            "read_order",
            {"orderRef": "synthetic-order-ref"},
            authorization=AUTHORIZATION,
            member_id=MEMBER_ID,
            task_ref=task_ref,
        )
        committed = gateway.commit(
            "commit_after_sales_action",
            {
                "orderFactRef": fact.reference,
                "applicationType": "return_refund",
                "idempotencyKey": "a" * 32,
            },
            authorization=AUTHORIZATION,
            member_id=MEMBER_ID,
            task_ref=task_ref,
        )

    assert committed.status == "succeeded"
    assert eligibility.call_count == 1
    assert create.call_count == 1
    assert create.call_args.kwargs["idempotency_key"] == "a" * 32


def test_gateway_does_not_write_when_order_reference_belongs_to_another_owner() -> None:
    vault = RuntimeReferenceVault()
    gateway = SafeCommerceSkillGateway(reference_vault=vault)
    task_ref = "taskref-abcdefghijklmnop"
    with patch("app.skills.commerce_gateway.get_order_snapshot", return_value={"status": "已支付", "product_names": []}), patch(
        "app.skills.commerce_gateway.create_after_sales_application"
    ) as create:
        fact = gateway.invoke(
            "read_order",
            {"orderRef": "synthetic-order-ref"},
            authorization=AUTHORIZATION,
            member_id=MEMBER_ID,
            task_ref=task_ref,
        )
        blocked = gateway.commit(
            "commit_after_sales_action",
            {
                "orderFactRef": fact.reference,
                "applicationType": "return_refund",
                "idempotencyKey": "b" * 32,
            },
            authorization=AUTHORIZATION,
            member_id=MEMBER_ID + 1,
            task_ref=task_ref,
        )

    assert blocked.status == "blocked"
    assert blocked.safe_facts["failure_code"] == "order_fact_reference_expired"
    create.assert_not_called()
