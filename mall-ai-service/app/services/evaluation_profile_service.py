"""Versioned, fixed evaluation profiles for synthetic quality experiments.

Profiles are purposely not selected in the customer request path.  They make
offline comparisons reproducible without claiming an online multi-model router.
"""
from __future__ import annotations

from app.schemas.agent_ops import EvaluationProfile


PROFILE_CATALOG_VERSION = "mall-evaluation-profiles.v1"

_PROFILES: tuple[EvaluationProfile, ...] = (
    EvaluationProfile(
        profile_id="contract_mock",
        version="v1",
        execution_mode="contract_mock",
        model_ref="none",
        prompt_version="quality-contract-v1",
        rag_profile_version="rag2-dense-v1",
        tool_schema_version="readonly-tools-v1",
        max_model_calls=0,
        max_tool_calls=7,
        timeout_seconds=60,
        max_attempts=1,
    ),
    EvaluationProfile(
        profile_id="live_model_synthetic",
        version="v1",
        execution_mode="live_model_synthetic",
        model_ref="configured_deepseek",
        prompt_version="quality-live-synthetic-v1",
        rag_profile_version="rag2-dense-v1",
        tool_schema_version="readonly-tools-v1",
        max_model_calls=7,
        max_tool_calls=7,
        timeout_seconds=60,
        max_attempts=1,
    ),
)
_PROFILE_BY_ID = {profile.profile_id: profile for profile in _PROFILES}


class EvaluationProfileError(ValueError):
    pass


def list_evaluation_profiles() -> tuple[EvaluationProfile, ...]:
    return _PROFILES


def get_evaluation_profile(profile_id: str) -> EvaluationProfile:
    try:
        return _PROFILE_BY_ID[profile_id]
    except KeyError as exc:
        raise EvaluationProfileError("未知或未启用的评测 Profile。") from exc
