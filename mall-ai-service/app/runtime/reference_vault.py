"""Short-lived, server-only references needed by Java-backed Task Skills.

The Task Runtime persists only public-safe projections.  A Java write can still
need an order reference that was supplied during the current authenticated
turn, so this module keeps that value outside Task/Plan/Artifact/Trace records.
It is owner- and task-bound, has a short TTL, and deliberately has no browser
or model-facing read API.  Losing this cache is safe: the Runtime asks the
Agent to re-read the fact instead of replaying a business action.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class _VaultValue:
    owner_ref: str
    task_ref: str
    kind: str
    value: str
    expires_at: float


class RuntimeReferenceVault:
    """In-process TTL vault for one Runtime process.

    This is intentionally a cache rather than an additional source of business
    truth.  Production task persistence remains Mongo; Java re-validates every
    fact and action.  A future Redis implementation may preserve the same
    owner/task/kind/TTL contract, but must never expose values in events or
    public DTOs.
    """

    def __init__(self, *, now_fn=time.time) -> None:
        self._now = now_fn
        self._items: dict[str, _VaultValue] = {}

    def put(
        self,
        *,
        reference: str,
        owner_ref: str,
        task_ref: str,
        kind: str,
        value: str,
        ttl_seconds: int = 900,
    ) -> None:
        if not all(isinstance(item, str) and item.strip() for item in (reference, owner_ref, task_ref, kind, value)):
            raise ValueError("运行时引用不能为空")
        self._purge()
        self._items[reference] = _VaultValue(
            owner_ref=owner_ref,
            task_ref=task_ref,
            kind=kind,
            value=value,
            expires_at=self._now() + max(1, min(ttl_seconds, 3600)),
        )

    def resolve(
        self,
        *,
        reference: str,
        owner_ref: str,
        task_ref: str,
        kind: str,
    ) -> str | None:
        self._purge()
        item = self._items.get(reference)
        if item is None:
            return None
        if item.owner_ref != owner_ref or item.task_ref != task_ref or item.kind != kind:
            return None
        return item.value

    def _purge(self) -> None:
        now = self._now()
        self._items = {
            reference: item
            for reference, item in self._items.items()
            if item.expires_at > now
        }
