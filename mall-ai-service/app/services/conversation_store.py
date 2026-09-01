"""Storage adapters for durable customer-service conversation state."""
from typing import Any, Protocol

from app.schemas.conversation import ConversationState


class ConversationStoreError(RuntimeError):
    pass


class ConversationStore(Protocol):
    def load(self, session_id: str) -> ConversationState | None: ...

    def save(self, state: ConversationState, ttl_seconds: int) -> None: ...

    def delete(self, session_id: str) -> None: ...


class InMemoryConversationStore:
    """Local-development and unit-test implementation with Redis-like JSON data."""

    def __init__(self) -> None:
        self._records: dict[str, str] = {}

    def load(self, session_id: str) -> ConversationState | None:
        value = self._records.get(session_id)
        return ConversationState.model_validate_json(value) if value else None

    def save(self, state: ConversationState, ttl_seconds: int) -> None:
        self._records[state.session_id] = state.model_dump_json()

    def delete(self, session_id: str) -> None:
        self._records.pop(session_id, None)

    def clear(self) -> None:
        self._records.clear()


class RedisConversationStore:
    def __init__(
        self,
        redis_url: str,
        key_prefix: str,
        redis_client: Any | None = None,
    ) -> None:
        if redis_client is None:
            try:
                from redis import Redis
            except ImportError as exc:
                raise ConversationStoreError(
                    "未安装 redis 客户端；请安装 requirements.txt 后启用 Redis 会话存储。"
                ) from exc
            self._client = Redis.from_url(redis_url, decode_responses=True)
        else:
            self._client = redis_client
        self._key_prefix = key_prefix.rstrip(":")

    def load(self, session_id: str) -> ConversationState | None:
        try:
            value = self._client.get(self._key(session_id))
        except Exception as exc:
            raise ConversationStoreError("会话存储暂时不可用。") from exc
        return ConversationState.model_validate_json(value) if value else None

    def save(self, state: ConversationState, ttl_seconds: int) -> None:
        try:
            self._client.set(self._key(state.session_id), state.model_dump_json(), ex=ttl_seconds)
        except Exception as exc:
            raise ConversationStoreError("会话状态保存失败。") from exc

    def delete(self, session_id: str) -> None:
        try:
            self._client.delete(self._key(session_id))
        except Exception as exc:
            raise ConversationStoreError("会话状态删除失败。") from exc

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}:{session_id}"
