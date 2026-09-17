"""Focused contracts for the v3.0.3 capability completion stage.

These tests use only opaque synthetic references and an in-memory Runtime.  In
particular, amendment must never call a commit adapter, while human handoff
must use the existing Java handoff boundary only after confirmation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.runtime.providers import DeterministicRuntimeProvider, RuntimeModelContext, ScriptedRuntimeProvider
from app.runtime.task_runtime import TaskRuntime, TaskRuntimeError
from app.runtime.task_store import InMemoryTaskStore
from app.schemas.agent_task import ExecutorDecision, SkillCall
from app.skills.commerce_gateway import SafeCommerceSkillGateway, SkillObservation


AUTHORIZATION = "Bearer synthetic-capability-credential"
MEMBER_ID = 171
SESSION_ID = "synthetic-capability-session"


def _decision(*, name: str, summary: str, calls=None, action_skill=None, action_arguments=None):
    return ExecutorDecision(
        decision=name,
        reason_summary=summary,
        skill_calls=calls or [],
        action_skill=action_skill,
        action_arguments=action_arguments or {},
    )


def _observation(
    *,
    skill: str,
    reference: str,
    kind: str,
    factuality: str = "verified",
    status: str = "succeeded",
) -> SkillObservation:
    return SkillObservation(
        status=status,
        artifact_kind=kind,
        summary=f"合成环境已返回 {skill} 的安全摘要。",
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


def test_after_sales_amendment_versions_proposal_and_rejects_stale_confirmation() -> None:
    order_ref = "fact-order-amend-contract"
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="先核验当前账号的合成订单事实。",
                calls=[SkillCall(skill_id="read_order", arguments={"orderRef": "ref-order-alpha"})],
            ),
            _decision(
                name="propose_action",
                summary="已形成待确认退货退款草案。",
                action_skill="create_after_sales_draft",
                action_arguments={"orderFactRef": order_ref, "applicationType": "return_refund"},
            ),
        ]
    )
    gateway = RecordingGateway(
        {
            "read_order": _observation(skill="read_order", reference=order_ref, kind="order_fact"),
            "commit_after_sales_action": _observation(
                skill="commit_after_sales_action", reference="action-amend-result", kind="action_result"
            ),
        }
    )
    runtime = TaskRuntime(
        store=InMemoryTaskStore(),
        provider=provider,
        gateway=gateway,
        reference_hints={"orderRef": "ref-order-alpha"},
    )

    original = runtime.create_task(
        session_id=SESSION_ID,
        goal="核验订单后准备售后方案",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )
    assert original.view.action is not None
    old_ref = original.view.action.proposal_ref
    old_revision = original.view.action.revision

    amended = runtime.amend_action(
        task_ref=original.view.task_ref,
        proposal_ref=old_ref,
        revision=old_revision,
        application_type="exchange",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )
    assert amended.view.action is not None
    assert amended.view.action.revision == old_revision + 1
    assert amended.view.action.proposal_ref != old_ref
    assert amended.view.action.application_type == "exchange"
    assert gateway.commits == []

    stored = runtime._store._items[original.view.task_ref]  # type: ignore[attr-defined] # noqa: SLF001
    assert stored.action_proposal_history[-1].proposal_ref == old_ref
    assert stored.action_proposal_history[-1].confirmation_status == "superseded"
    assert any(event.event_type == "action_revised" for event in amended.events)

    with pytest.raises(TaskRuntimeError) as stale:
        runtime.confirm_action(
            task_ref=original.view.task_ref,
            confirmation="confirm",
            proposal_ref=old_ref,
            revision=old_revision,
            member_id=MEMBER_ID,
            authorization=AUTHORIZATION,
        )
    assert stale.value.code == "stale_proposal_revision"
    assert gateway.commits == []

    committed = runtime.confirm_action(
        task_ref=original.view.task_ref,
        confirmation="confirm",
        proposal_ref=amended.view.action.proposal_ref,
        revision=amended.view.action.revision,
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )
    assert committed.view.status == "executing"
    assert len(gateway.commits) == 1
    assert gateway.commits[0][0] == "commit_after_sales_action"
    assert gateway.commits[0][1]["applicationType"] == "exchange"


def test_human_case_confirmation_requires_only_safe_artifacts_and_is_idempotent() -> None:
    policy_ref = "policy-human-evidence"
    provider = ScriptedRuntimeProvider(
        decisions=[
            _decision(
                name="call_skill",
                summary="先读取可引用的合成政策证据。",
                calls=[SkillCall(skill_id="retrieve_policy", arguments={"query": "售后处理规则"})],
            ),
            _decision(
                name="propose_action",
                summary="证据不足，形成待确认人工协同方案。",
                action_skill="open_human_case",
                action_arguments={
                    "artifactRefs": [policy_ref],
                    "reasonCode": "insufficient_evidence",
                },
            ),
        ]
    )
    gateway = RecordingGateway(
        {
            "retrieve_policy": _observation(
                skill="retrieve_policy", reference=policy_ref, kind="policy_evidence", factuality="derived"
            ),
            "commit_human_case": _observation(
                skill="commit_human_case", reference="case-result-opaque", kind="action_result"
            ),
        }
    )
    runtime = TaskRuntime(store=InMemoryTaskStore(), provider=provider, gateway=gateway)

    proposed = runtime.create_task(
        session_id=SESSION_ID,
        goal="政策证据不足时请转人工核验",
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )
    assert proposed.view.status == "ready_to_commit"
    assert proposed.view.action is not None
    assert proposed.view.action.action_skill == "open_human_case"
    assert gateway.commits == []

    confirmed = runtime.confirm_action(
        task_ref=proposed.view.task_ref,
        confirmation="confirm",
        proposal_ref=proposed.view.action.proposal_ref,
        revision=proposed.view.action.revision,
        member_id=MEMBER_ID,
        authorization=AUTHORIZATION,
    )
    assert confirmed.view.status == "executing"
    assert len(gateway.commits) == 1
    commit_skill, commit_args = gateway.commits[0]
    assert commit_skill == "commit_human_case"
    assert commit_args["artifactRefs"] == [policy_ref]
    assert commit_args["reasonCode"] == "insufficient_evidence"
    assert "orderFactRef" not in commit_args
    assert "idempotencyKey" in commit_args

    with pytest.raises(TaskRuntimeError) as duplicate:
        runtime.confirm_action(
            task_ref=proposed.view.task_ref,
            confirmation="confirm",
            proposal_ref=proposed.view.action.proposal_ref,
            revision=proposed.view.action.revision,
            member_id=MEMBER_ID,
            authorization=AUTHORIZATION,
        )
    assert duplicate.value.code == "action_gate_missing"
    assert len(gateway.commits) == 1

    with pytest.raises(TaskRuntimeError) as other_owner:
        runtime.get_task(task_ref=proposed.view.task_ref, member_id=MEMBER_ID + 1, authorization=AUTHORIZATION)
    assert other_owner.value.code == "task_not_found"


def test_human_gateway_reuses_existing_java_handoff_allow_list(monkeypatch) -> None:
    captured = {}

    def fake_register(*, session_id, diagnosis, authorization):
        captured["session_id"] = session_id
        captured["diagnosis"] = diagnosis
        captured["authorization"] = authorization
        return SimpleNamespace(case_id="case-opaque", case_status="OPEN")

    monkeypatch.setattr("app.skills.commerce_gateway.register_case_handoff", fake_register)
    gateway = SafeCommerceSkillGateway()
    result = gateway.commit(
        "commit_human_case",
        {
            "artifactRefs": ["policy-human-evidence"],
            "reasonCode": "tool_failure",
            "diagnosisCategory": "tool_failure",
            "evidenceStatus": "partial",
            "verifiedSourceTypes": ["policy_evidence"],
            "idempotencyKey": "a" * 32,
        },
        authorization=AUTHORIZATION,
        member_id=MEMBER_ID,
        task_ref="taskref-human-handoff",
    )

    assert result.status == "succeeded"
    assert captured["session_id"] == "taskref-human-handoff"
    assert captured["authorization"] == AUTHORIZATION
    diagnosis = captured["diagnosis"]
    assert diagnosis.category == "tool_failure"
    assert diagnosis.handoff is not None
    assert diagnosis.handoff.reason == "tool_failure"
    assert diagnosis.handoff.verified_source_types == ["policy_evidence"]
    assert "case-opaque" not in diagnosis.handoff.summary


def test_deterministic_provider_proposes_only_the_public_after_sales_draft_skill() -> None:
    """Offline field runs must exercise the same executor visibility boundary."""

    decision = DeterministicRuntimeProvider().decide(
        RuntimeModelContext(
            task_ref="taskref-deterministic-after-sales",
            goal="申请取消退款并完成售后闭环",
            task_status="executing",
            plan_version=1,
            plan_summary="已核验订单事实。",
            artifact_details=[
                {
                    "kind": "order_fact",
                    "factuality": "verified",
                    "reference": "fact-order-deterministic",
                }
            ],
            reference_hints={"orderRef": "ref-order-deterministic"},
            model_calls_remaining=2,
            tool_calls_remaining=2,
        )
    )

    assert decision.decision == "propose_action"
    assert decision.action_skill == "create_after_sales_draft"
    assert decision.action_arguments["orderFactRef"] == "fact-order-deterministic"


def test_deterministic_provider_can_only_propose_a_confirmable_human_handoff() -> None:
    decision = DeterministicRuntimeProvider().decide(
        RuntimeModelContext(
            task_ref="taskref-deterministic-human",
            goal="订单事实不足时需要人工复核",
            task_status="executing",
            plan_version=1,
            plan_summary="已核验安全事实。",
            artifact_details=[
                {
                    "kind": "order_fact",
                    "factuality": "verified",
                    "reference": "fact-order-human",
                }
            ],
            model_calls_remaining=2,
            tool_calls_remaining=2,
        )
    )

    assert decision.decision == "propose_action"
    assert decision.action_skill == "open_human_case"
    assert decision.action_arguments == {
        "artifactRefs": ["fact-order-human"],
        "reasonCode": "manual_review",
    }
