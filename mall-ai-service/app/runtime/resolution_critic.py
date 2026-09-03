"""Conditionally triggered candidate-resolution critic."""
from __future__ import annotations

from app.schemas.agent_task import ResolutionCritique, TaskArtifact, TaskPlan
from app.runtime.providers import RuntimeModelError, RuntimeModelProvider


class ResolutionCritic:
    def __init__(self, provider: RuntimeModelProvider) -> None:
        self._provider = provider

    @staticmethod
    def should_trigger(*, artifacts: list[TaskArtifact], skill_calls: int, has_action: bool, has_conflict: bool) -> bool:
        candidate_count = sum(artifact.kind == "resolution_candidate" for artifact in artifacts)
        return candidate_count >= 2 or skill_calls >= 4 or has_action or has_conflict

    def evaluate(self, *, task_ref: str, plan: TaskPlan, artifacts: list[TaskArtifact]) -> ResolutionCritique | None:
        if not self.should_trigger(
            artifacts=artifacts,
            skill_calls=len(artifacts),
            has_action=any(artifact.kind == "resolution_candidate" for artifact in artifacts),
            has_conflict=False,
        ):
            return None
        payload = {
            "taskRef": task_ref,
            "plan": {
                "version": plan.version,
                "objective": plan.objective,
                "openQuestions": plan.open_questions,
                "nodes": [
                    {"goal": node.goal, "status": node.status, "requiredSkills": node.required_skills}
                    for node in plan.nodes[:8]
                ],
            },
            "artifacts": [
                {"kind": artifact.kind, "summary": artifact.summary, "reference": artifact.reference}
                for artifact in artifacts[-12:]
            ],
        }
        try:
            return self._provider.critique(payload)
        except RuntimeModelError:
            # A critic outage must never convert an otherwise valid task into a
            # false success or trigger a write. Keep the result explicitly absent.
            return None
