"""Persistent fail-closed budget for the authorized v3.0.4 retest campaign."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = "v304-live-retest-campaign.v1"
MAX_BATCHES = 3
MAX_HTTP_ATTEMPTS = 240
MAX_TOTAL_TOKENS = 600_000
PER_BATCH_HTTP_ATTEMPTS = 80
PER_BATCH_TOTAL_TOKENS = 200_000


class CampaignBudgetError(RuntimeError):
    pass


def begin_campaign_batch(
    path: Path,
    *,
    batch_id: str,
    release_id: str,
    runtime_commit: str,
) -> tuple[int, int]:
    """Consume one batch slot and return its remaining cumulative hard caps."""

    with _update_guard(path):
        state = _read_or_create_state(path)
        batches = state["batches"]
        if any(item.get("status") in {"RUNNING", "AMBIGUOUS"} for item in batches):
            raise CampaignBudgetError("campaign has an unsettled batch")
        if len(batches) >= MAX_BATCHES:
            raise CampaignBudgetError("campaign batch limit exhausted")
        attempts_used, tokens_used = _settled_usage(batches)
        attempts_limit = min(PER_BATCH_HTTP_ATTEMPTS, MAX_HTTP_ATTEMPTS - attempts_used)
        tokens_limit = min(PER_BATCH_TOTAL_TOKENS, MAX_TOTAL_TOKENS - tokens_used)
        if attempts_limit <= 0 or tokens_limit <= 0:
            raise CampaignBudgetError("campaign cumulative budget exhausted")
        batches.append(
            {
                "batchId": batch_id,
                "releaseId": release_id,
                "runtimeCommit": runtime_commit,
                "status": "RUNNING",
                "startedAt": _now_iso(),
                "maxProviderHttpAttempts": attempts_limit,
                "maxTotalTokens": tokens_limit,
                "providerHttpAttempts": None,
                "totalTokens": None,
                "ledgerReconciled": False,
            }
        )
        _refresh_totals(state)
        _atomic_write(path, state)
        return attempts_limit, tokens_limit


def settle_campaign_batch(
    path: Path,
    *,
    batch_id: str,
    status: str,
    provider_http_attempts: int,
    total_tokens: int,
    ledger_reconciled: bool,
) -> None:
    """Settle the current batch; ambiguity permanently blocks automatic reuse."""

    with _update_guard(path):
        state = _read_state(path)
        matches = [item for item in state["batches"] if item.get("batchId") == batch_id]
        if len(matches) != 1 or matches[0].get("status") != "RUNNING":
            raise CampaignBudgetError("campaign running batch does not match")
        item = matches[0]
        valid_counts = (
            isinstance(provider_http_attempts, int)
            and not isinstance(provider_http_attempts, bool)
            and provider_http_attempts >= 0
            and isinstance(total_tokens, int)
            and not isinstance(total_tokens, bool)
            and total_tokens >= 0
        )
        within_reserved = valid_counts and (
            provider_http_attempts <= int(item["maxProviderHttpAttempts"])
            and total_tokens <= int(item["maxTotalTokens"])
        )
        item.update(
            {
                "status": status if ledger_reconciled and within_reserved else "AMBIGUOUS",
                "endedAt": _now_iso(),
                "providerHttpAttempts": provider_http_attempts if valid_counts else None,
                "totalTokens": total_tokens if valid_counts else None,
                "ledgerReconciled": bool(ledger_reconciled),
            }
        )
        _refresh_totals(state)
        _atomic_write(path, state)
        if item["status"] == "AMBIGUOUS":
            raise CampaignBudgetError("campaign batch usage is ambiguous")


def _read_or_create_state(path: Path) -> dict[str, object]:
    if path.exists():
        return _read_state(path)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "limits": {
            "maxBatches": MAX_BATCHES,
            "maxProviderHttpAttempts": MAX_HTTP_ATTEMPTS,
            "maxTotalTokens": MAX_TOTAL_TOKENS,
        },
        "batches": [],
        "batchesUsed": 0,
        "providerHttpAttempts": 0,
        "totalTokens": 0,
    }


def _read_state(path: Path) -> dict[str, object]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignBudgetError("campaign state is unreadable") from exc
    expected_limits = {
        "maxBatches": MAX_BATCHES,
        "maxProviderHttpAttempts": MAX_HTTP_ATTEMPTS,
        "maxTotalTokens": MAX_TOTAL_TOKENS,
    }
    if (
        not isinstance(state, dict)
        or state.get("schemaVersion") != SCHEMA_VERSION
        or state.get("limits") != expected_limits
        or not isinstance(state.get("batches"), list)
    ):
        raise CampaignBudgetError("campaign state contract is invalid")
    _settled_usage(state["batches"])
    return state


def _settled_usage(batches: list[dict[str, object]]) -> tuple[int, int]:
    attempts = 0
    tokens = 0
    seen: set[str] = set()
    for item in batches:
        if not isinstance(item, dict) or not isinstance(item.get("batchId"), str):
            raise CampaignBudgetError("campaign batch entry is invalid")
        if item["batchId"] in seen:
            raise CampaignBudgetError("campaign batch id is duplicated")
        seen.add(item["batchId"])
        if item.get("status") in {"RUNNING", "AMBIGUOUS"}:
            continue
        item_attempts = item.get("providerHttpAttempts")
        item_tokens = item.get("totalTokens")
        if (
            not isinstance(item_attempts, int)
            or isinstance(item_attempts, bool)
            or item_attempts < 0
            or not isinstance(item_tokens, int)
            or isinstance(item_tokens, bool)
            or item_tokens < 0
            or item.get("ledgerReconciled") is not True
        ):
            raise CampaignBudgetError("campaign settled usage is invalid")
        attempts += item_attempts
        tokens += item_tokens
    if attempts > MAX_HTTP_ATTEMPTS or tokens > MAX_TOTAL_TOKENS:
        raise CampaignBudgetError("campaign cumulative usage exceeds limits")
    return attempts, tokens


def _refresh_totals(state: dict[str, object]) -> None:
    batches = state["batches"]
    attempts, tokens = _settled_usage(batches)
    state["batchesUsed"] = len(batches)
    state["providerHttpAttempts"] = attempts
    state["totalTokens"] = tokens
    state["updatedAt"] = _now_iso()


@contextmanager
def _update_guard(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    guard = path.with_suffix(path.suffix + ".update.lock")
    try:
        descriptor = os.open(str(guard), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CampaignBudgetError("campaign update is already in progress") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        guard.unlink(missing_ok=True)


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
