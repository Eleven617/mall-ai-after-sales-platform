from pydantic import BaseModel, Field

from app.schemas.diagnosis import DiagnosisResult
from app.schemas.facts import VerifiedFactCard, VerifiedFactField, VerifiedFactSource
from app.schemas.rag import RagSource
from app.schemas.tool import ToolCall


class AgentRunResult(BaseModel):
    """Agent 的受控输出：answer 与可验证业务事实分离。"""

    answer: str
    verified_facts: list[VerifiedFactCard] = Field(default_factory=list)
    pending_tool_call: ToolCall | None = None
    # Internal-only signal: the pending read-only diagnosis is owned by a
    # sanitized LangGraph checkpoint, not by the older conversation cache.
    # It is intentionally absent from the public customer DTO.
    durable_checkpoint_pending: bool = False
    diagnosis: DiagnosisResult | None = None
    policy_sources: list[RagSource] = Field(default_factory=list)
