"""Closed handoff projection; no arbitrary text or model-selected identity."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Reason = Literal['human_preference','intent_misunderstood','repeated_questions','answer_or_evidence_insufficient','tool_or_system_error','capability_or_permission_limit','business_dispute','delay_or_complex_process','unspecified']
Topic = Literal['logistics','policy','refund','return','exchange','repair','application_follow_up','general','unknown']

class HandoffPrepare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: str = Field(min_length=1,max_length=128)
    task_ref: str | None = Field(default=None,pattern=r'^taskref-[a-z0-9]{8,32}$')
    reason: Reason = 'unspecified'
    topic: Topic = 'general'
    new_issue: bool = False
    problem_description: str = Field(default='', max_length=240, exclude=True, repr=False)

class HandoffContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_ref: str = Field(pattern=r'^[a-f0-9]{64}$')
    scope_key: str = Field(pattern=r'^[a-f0-9]{64}$')
    source: Literal['customer_requested','system_suggested_accepted'] = 'customer_requested'
    channel: Literal['button','chat','legacy'] = 'button'
    topic: Topic = 'general'
    reason: Reason = 'unspecified'
    stage: str
    linked_task_ref: str | None = None
    plan_version: int = Field(default=0,ge=0,le=99)
    completed_steps: int = Field(default=0,ge=0,le=12)
    verified_evidence_count: int = Field(default=0,ge=0,le=1000)
    case_ref: str | None = None
    problem_projection: dict | None = None
    safe_input_snapshot: dict | None = None

class HandoffResult(BaseModel):
    model_config = ConfigDict(extra='ignore')
    caseRef: str = Field(pattern=r'^[a-f0-9-]{36}$')
    state: str = Field(max_length=48)
    version: int
