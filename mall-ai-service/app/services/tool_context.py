from dataclasses import dataclass, replace
from typing import Literal


@dataclass(frozen=True)
class ToolExecutionContext:
    """一次用户请求中，工具执行所需的可信上下文。"""

    authorization: str | None = None
    # Only the HTTP router sets this after Java validates the Bearer Token.
    member_id: int | None = None
    # These fields are server-owned execution metadata.  Browser and model
    # payloads never populate them; the Skill catalog validates them again at
    # tool execution time.
    actor_role: Literal["unified_after_sales", "operations_analysis", "quality_evaluation"] = "unified_after_sales"
    skill_id: str | None = None

    def for_skill(self, skill_id: str) -> "ToolExecutionContext":
        return replace(self, skill_id=skill_id)
