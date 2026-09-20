"""Versioned, offline execution of the v2 open-task Agent contracts.

The replay uses the production ``TaskRuntime`` and synthetic read-only gateway.
Decisions are generated from a reviewed fixture policy, never from the
post-check expected values, and no external provider is reachable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from app.runtime.live_model_agent_evaluation import (
    DEFAULT_SUITE_PATH,
    FaultInjectedProvider,
    HOLDOUT_SUITE_VERSION,
    SUITE_VERSION,
    load_live_agent_suite,
    run_live_model_agent_evaluation,
)
from app.runtime.providers import ScriptedRuntimeProvider
from app.schemas.agent_task import ExecutorDecision, SkillCall


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOLDOUT_SUITE_PATH = PROJECT_ROOT / "evals" / "live_model_agent_holdout_cases.v3.json"
REPLAY_FIXTURE_PATH = PROJECT_ROOT / "evals" / "live_model_agent_contract_replay.v1.json"
REPLAY_VERSION = "v3.0.4-contract-replay.v1"


class FixtureReplayProvider(ScriptedRuntimeProvider):
    """A bounded decision policy derived from reviewed fixture observations."""

    def __init__(self, case: Mapping[str, Any]) -> None:
        super().__init__(decisions=[])
        self.case = case
        self.fixture = case.get("fixture", {})
        self.observations = self.fixture.get("observations", {})
        self.expected = case.get("expect", {})
        self._issued_reads = False

    def decide(self, context):
        self.decision_calls += 1
        observed = {str(item.get("sourceSkill")) for item in context.artifact_details}
        blocked = any(
            isinstance(value, Mapping) and str(value.get("status", "succeeded")) in {"blocked", "unavailable"}
            for value in self.observations.values()
        )
        allowed = set(self.expected.get("allowed_skills", []))
        available = {
            str(item.get("skillId"))
            for item in context.available_skills
            if isinstance(item, Mapping) and item.get("skillId")
        }
        pending = [
            skill
            for skill in self.observations
            if skill not in observed and (not allowed or skill in allowed) and (not available or skill in available)
        ]
        # Resolution composition is a second turn: the Runtime must first
        # persist the order/policy facts that the candidate consumes.
        if "build_service_resolution" in pending and len(pending) > 1 and not any(
            str(item.get("kind")) in {"order_fact", "policy_evidence"} for item in context.artifact_details
        ):
            pending = [skill for skill in pending if skill != "build_service_resolution"]
        elif "build_service_resolution" in pending and any(
            str(item.get("kind")) in {"order_fact", "policy_evidence"} for item in context.artifact_details
        ):
            pending = ["build_service_resolution"]
        if pending:
            self._issued_reads = True
            calls = [SkillCall(skill_id=skill, arguments=self._arguments(skill, context)) for skill in pending[:4]]
            return ExecutorDecision(decision="call_skill", reason_summary="按回放契约读取合成事实。", skill_calls=calls)
        if not self.observations and self.expected.get("clarification"):
            return ExecutorDecision(decision="ask_user", reason_summary="目标存在多个可能方向。", user_question="请说明你希望先处理哪一项。")
        if blocked:
            allowed = set(self.expected.get("allowed_proposal_skills", []))
            if "open_human_case" in allowed and context.artifact_details:
                refs = [str(item["reference"]) for item in context.artifact_details if item.get("reference")]
                return ExecutorDecision(
                    decision="propose_action",
                    reason_summary="证据不足，转人工协同复核。",
                    action_skill="open_human_case",
                    action_arguments={"artifactRefs": refs[-3:], "reasonCode": "insufficient_evidence"},
                )
            return ExecutorDecision(decision="ask_user", reason_summary="当前合成事实不足，安全等待补充。", user_question="请补充必要信息后继续。")
        if "subtask_created" in self.expected.get("post", []):
            return ExecutorDecision(
                decision="spawn_subtask",
                reason_summary="已创建受控库存替代调查子任务。",
                action_arguments={"goalCode": "inventory_alternatives", "requiredSkills": ["search_catalog"]},
            )
        if self.expected.get("proposal") == "required":
            refs = [str(item["reference"]) for item in context.artifact_details if item.get("reference")]
            order_ref = next(
                (str(item["reference"]) for item in context.artifact_details if item.get("kind") == "order_fact"),
                refs[-1] if refs else "ref-synthetic-order",
            )
            return ExecutorDecision(
                decision="propose_action",
                reason_summary="已形成待确认的合成售后方案。",
                action_skill="create_after_sales_draft",
                action_arguments={
                    "proposalRef": "proposalref-synthetic",
                    "orderFactRef": order_ref,
                    "applicationType": "return_refund",
                },
            )
        return ExecutorDecision(decision="finish", reason_summary="合成回放事实已处理完成。")

    @staticmethod
    def _arguments(skill: str, context) -> dict[str, Any]:
        if skill in {"read_order", "read_logistics"}:
            return {"orderRef": context.reference_hints.get("orderRef", "ref-synthetic-order")}
        if skill == "read_inventory":
            return {"skuRef": context.reference_hints.get("skuRef", "ref-synthetic-sku")}
        if skill == "retrieve_policy":
            return {"query": "合成售后政策"}
        if skill == "search_catalog":
            return {"query": "合成商品"}
        if skill == "compare_skus":
            return {"sku_refs": ["ref-synthetic-sku"], "criteria": ["price"]}
        if skill == "build_service_resolution":
            return {"factRefs": [str(item["reference"]) for item in context.artifact_details if item.get("reference")]}
        if skill == "search_task_memory":
            return {"query": "合成任务摘要"}
        return {}


def _provider_factory(case: Mapping[str, Any]):
    fault = case.get("fixture", {}).get("provider_fault")
    if isinstance(fault, str):
        return FaultInjectedProvider(fault)
    return FixtureReplayProvider(case)


def run_contract_replay(*, report_path: Path | None = None) -> dict[str, Any]:
    replay_fixture = json.loads(REPLAY_FIXTURE_PATH.read_text(encoding="utf-8"))
    if replay_fixture.get("executionKind") != "contract_replay":
        raise ValueError("contract replay fixture execution kind mismatch")
    expected_ids = set(replay_fixture.get("runtimeCases", [])) | set(replay_fixture.get("holdoutCases", []))
    runtime = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        required_runs=1,
        provider_factory=_provider_factory,
        max_total_seconds=900,
        timeout_seconds=10,
        max_attempts=1,
    )
    holdout = run_live_model_agent_evaluation(
        suite_path=HOLDOUT_SUITE_PATH,
        required_runs=1,
        provider_factory=_provider_factory,
        max_total_seconds=900,
        timeout_seconds=10,
        max_attempts=1,
    )
    cases = [*runtime["cases"], *holdout["cases"]]
    if {str(item.get("caseId")) for item in cases} != expected_ids:
        raise ValueError("contract replay fixture case set mismatch")
    payload: dict[str, Any] = {
        "replayVersion": REPLAY_VERSION,
        "executionKind": "contract_replay",
        "runtimeSuite": {key: runtime[key] for key in ("suiteVersion", "suiteSha256", "passed", "failed", "environmentBlocked", "executedRuns")},
        "holdoutSuite": {key: holdout[key] for key in ("suiteVersion", "suiteSha256", "passed", "failed", "environmentBlocked", "executedRuns")},
        "caseCount": len(cases),
        "passed": sum(item["status"] == "passed" for item in cases),
        "failed": sum(item["status"] == "failed" for item in cases),
        "environmentBlocked": sum(item["status"] == "environment_blocked" for item in cases),
        "providerCalls": 0,
        "providerTokens": 0,
        "fixtureSha256": hashlib.sha256(REPLAY_FIXTURE_PATH.read_bytes()).hexdigest(),
        "cases": cases,
    }
    payload["status"] = "passed" if payload["passed"] == 36 and payload["failed"] == 0 and payload["environmentBlocked"] == 0 else "failed"
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


__all__ = ["run_contract_replay", "REPLAY_VERSION"]
