"""Hydrate short-lived AI context from an owner-approved history transcript."""
from app.schemas.conversation import ConversationMessage, ConversationState
from app.schemas.conversation_history import ConversationHistoryMessage
from app.services.conversation_state import save_conversation_state


def restore_history_context(
    session_id: str,
    messages: list[ConversationHistoryMessage],
) -> None:
    """Restore only the latest safe turns, never a pending write workflow.

    A history record lets a customer continue a prior discussion after Redis has
    expired. Pending return confirmations intentionally do not survive this
    restore; the customer must restart or explicitly confirm through the normal
    deterministic workflow instead of reviving a stale write action.
    """
    latest = messages[-6:]
    state = ConversationState(
        session_id=session_id,
        recent_messages=[
            ConversationMessage(role=message.role, content=message.content)
            for message in latest
        ],
    )
    save_conversation_state(state)
