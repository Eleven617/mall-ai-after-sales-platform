"""Server-side conversation keys derived from a public chat ID and owner scope."""
import hashlib


def build_conversation_state_key(
    public_session_id: str,
    member_id: int | None,
) -> str:
    """Return an opaque key so identical browser chat IDs cannot share state.

    `member_id` is obtained from Java's authenticated `/sso/info` endpoint, never
    from the browser request body. Anonymous conversations deliberately use a
    separate scope and therefore cannot resume a logged-in member's workflow.
    """
    normalized_session_id = public_session_id.strip()
    if not normalized_session_id:
        raise ValueError("会话标识不能为空。")
    if member_id is not None and member_id <= 0:
        raise ValueError("会员标识不合法。")

    owner_scope = f"member:{member_id}" if member_id is not None else "anonymous"
    raw_key = f"v1\0{owner_scope}\0{normalized_session_id}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"conversation-v1-{digest}"
