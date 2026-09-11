"""Context Pack construction and memory-safe compression."""
from __future__ import annotations

import json
import time
from typing import Iterable

from pydantic import ValidationError

from app.schemas.agent_task import (
    AgentTask,
    ContextPack,
    TaskArtifact,
    TaskPlan,
    ensure_safe_summary,
)
from app.runtime.providers import ContextCuratorInput, RuntimeModelError, RuntimeModelProvider
from app.runtime.task_planner import new_context_id


def estimate_tokens(text: str) -> int:
    if not isinstance(text, str):
        return 0
    return max(0, (len(text) + 1) // 2)


class ContextCurator:
    def __init__(self, provider: RuntimeModelProvider) -> None:
        self._provider = provider

    def build_pack(
        self,
        *,
        task: AgentTask,
        plan: TaskPlan,
        artifacts: Iterable[TaskArtifact],
        memory_hints: list[str],
        available_skills: list[str],
    ) -> ContextPack:
        live_artifacts = [artifact for artifact in artifacts if artifact.expires_at > time.time()]
        summaries = [artifact.summary for artifact in live_artifacts]
        plan_snapshot = "；".join(f"{node.goal}:{node.status}" for node in plan.nodes[:8])
        safe_memory_hints = _safe_values(memory_hints, 8)
        before_payload = {
            "goal": task.normalized_goal,
            "plan": plan_snapshot,
            "artifacts": summaries,
            "memory": safe_memory_hints,
            "skills": available_skills[:8],
        }
        before = estimate_tokens(json.dumps(before_payload, ensure_ascii=False))
        try:
            curated = self._provider.curate(
                ContextCuratorInput(
                    task_ref=task.task_ref,
                    goal=task.normalized_goal,
                    plan_snapshot=plan_snapshot,
                    artifact_summaries=summaries,
                    existing_memory_hints=safe_memory_hints,
                    available_skills=available_skills[:8],
                    token_estimate_before=before,
                )
            )
            verified_facts = curated.verified_facts
            unresolved = curated.unresolved_assumptions
            candidates = curated.candidate_actions
            effects = curated.executed_effects
            hints = curated.memory_hints
        except RuntimeModelError:
            # Context compression is useful but not a reason to leak data or
            # fail a read-only task. A deterministic bounded projection is safe.
            verified_facts = summaries[:8]
            unresolved = []
            candidates = []
            effects = []
            hints = safe_memory_hints[:4]
        # Curator output is still model-authored and its output model only
        # checks list sizes.  Apply the same privacy-safe summary contract as
        # ContextPack before persisting it.  An invalid item is discarded;
        # it must never turn a read-only task into a Runtime ValidationError.
        verified_facts = _safe_values(verified_facts, 8)
        unresolved = _safe_values(unresolved, 6)
        candidates = _safe_values(candidates, 4)
        effects = _safe_values(effects, 6)
        hints = _safe_values(hints, 4)
        after_payload = {
            "goal": task.normalized_goal,
            "plan": plan_snapshot,
            "verified": verified_facts[:8],
            "unresolved": unresolved[:6],
            "candidates": candidates[:4],
            "effects": effects[:6],
            "memory": hints[:4],
            "skills": available_skills[:8],
        }
        after = estimate_tokens(json.dumps(after_payload, ensure_ascii=False))
        retention = 1.0 if not summaries else min(1.0, len(verified_facts) / max(1, len(summaries)))
        try:
            return ContextPack(
                pack_id=new_context_id(),
                task_id=task.task_id,
                version=max(1, task.plan_version),
                goal=task.normalized_goal,
                plan_snapshot=plan_snapshot or "无计划",
                verified_facts=verified_facts[:12],
                unresolved_assumptions=unresolved[:8],
                candidate_actions=candidates[:4],
                executed_effects=effects[:8],
                memory_hints=hints[:6],
                available_skills=available_skills[:8],
                token_estimate_before=before,
                token_estimate_after=after,
                fact_reference_retention=retention,
                source_artifact_refs=[artifact.reference for artifact in live_artifacts[:16]],
                expires_at=min(task.expires_at, time.time() + 3600),
            )
        except (ValidationError, TypeError, ValueError):
            # Keep the executor usable if a future schema adds a stricter
            # context field.  This fallback contains only already validated
            # server-owned Artifact summaries and references.
            safe_verified = _safe_values(summaries, 8)
            return ContextPack(
                pack_id=new_context_id(),
                task_id=task.task_id,
                version=max(1, task.plan_version),
                goal=task.normalized_goal,
                plan_snapshot=plan_snapshot or "无计划",
                verified_facts=safe_verified,
                unresolved_assumptions=[],
                candidate_actions=[],
                executed_effects=[],
                memory_hints=[],
                available_skills=available_skills[:8],
                token_estimate_before=before,
                token_estimate_after=estimate_tokens(json.dumps({"verified": safe_verified}, ensure_ascii=False)),
                fact_reference_retention=1.0 if not summaries else min(1.0, len(safe_verified) / max(1, len(summaries))),
                source_artifact_refs=[artifact.reference for artifact in live_artifacts[:16]],
                expires_at=min(task.expires_at, time.time() + 3600),
            )


def _safe_values(values: Iterable[object], limit: int) -> list[str]:
    """Keep only bounded, non-sensitive summaries from a model projection."""

    safe: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            normalized = ensure_safe_summary(value)
        except (TypeError, ValueError):
            continue
        if normalized not in safe:
            safe.append(normalized)
        if len(safe) >= limit:
            break
    return safe
