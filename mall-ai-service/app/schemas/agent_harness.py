"""Versioned, server-owned business Skill contracts for the three agents."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AgentRole = Literal["unified_after_sales", "operations_analysis", "quality_evaluation"]


class StrictHarnessModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SkillDefinition(StrictHarnessModel):
    skill_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    semantic_version: str = Field(min_length=2, max_length=32, pattern=r"^v[0-9]+(?:\.[0-9]+){0,2}$")
    owner_role: AgentRole
    input_contract: str = Field(min_length=3, max_length=160)
    output_contract: str = Field(min_length=3, max_length=160)
    allowed_tool_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    allowed_state_transitions: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    required_evidence_kinds: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    max_model_calls: int = Field(ge=0, le=7)
    max_tool_calls: int = Field(ge=0, le=7)
    timeout_seconds: int = Field(ge=1, le=120)
    guard_profile_version: str = Field(min_length=3, max_length=64)
    prompt_fragment_version: str = Field(min_length=3, max_length=64)
    eval_suite_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    deprecated_at: str | None = None


class CapabilityProfile(StrictHarnessModel):
    role: AgentRole
    allowed_skill_ids: tuple[str, ...] = Field(min_length=1, max_length=12)
    allowed_tool_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    business_writes_allowed: bool = False
