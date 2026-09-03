"""Owner/task-scoped episodic memory with TTL and conflict handling."""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEntry:
    owner_ref: str
    task_ref: str
    summary: str
    reference: str
    created_at: float
    expires_at: float


class TaskMemory:
    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def remember(self, *, owner_ref: str, task_ref: str, summary: str, reference: str, ttl_seconds: int = 86_400) -> MemoryEntry:
        if len(summary) > 240 or not summary.strip():
            raise ValueError("记忆摘要不合法")
        now = time.time()
        entry = MemoryEntry(
            owner_ref=owner_ref,
            task_ref=task_ref,
            summary=" ".join(summary.split()),
            reference=reference,
            created_at=now,
            expires_at=now + max(1, ttl_seconds),
        )
        self._entries = [item for item in self._entries if item.expires_at > now]
        self._entries.append(entry)
        return entry

    def search(self, *, owner_ref: str, task_ref: str | None = None, query: str = "", limit: int = 6) -> list[MemoryEntry]:
        now = time.time()
        tokens = {token for token in query.lower().split() if token}
        entries = [
            item
            for item in self._entries
            if item.owner_ref == owner_ref
            and item.expires_at > now
            and (task_ref is None or item.task_ref == task_ref)
        ]
        if tokens:
            entries.sort(key=lambda item: (-sum(token in item.summary.lower() for token in tokens), -item.created_at))
        else:
            entries.sort(key=lambda item: -item.created_at)
        return entries[:limit]

    def delete_task(self, *, owner_ref: str, task_ref: str) -> None:
        self._entries = [item for item in self._entries if not (item.owner_ref == owner_ref and item.task_ref == task_ref)]
