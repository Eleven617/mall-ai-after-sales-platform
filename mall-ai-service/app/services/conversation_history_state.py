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
    # Java 展示历史不回灌模型记忆；旧确认、原文及摘要均不自动恢复。
    state = ConversationState(
        session_id=session_id,
    )
    save_conversation_state(state)
