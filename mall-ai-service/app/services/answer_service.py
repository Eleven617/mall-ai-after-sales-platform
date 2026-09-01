from app.schemas.intent import IntentResponse
from app.services.fact_presentation_service import (
    build_verified_facts,
    render_verified_facts_summary,
)


def generate_answer_from_tool_result(
    user_message: str,
    intent: IntentResponse,
    tool_result: dict,
) -> str:
    """Render tool facts on the server instead of asking an LLM to restate them."""
    if intent.tool_call is None:
        return "查询完成。"

    facts = build_verified_facts([(intent.tool_call.name, tool_result)])
    return render_verified_facts_summary(facts)
