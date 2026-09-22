from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.live_retest_campaign import (
    CampaignBudgetError,
    begin_campaign_batch,
    settle_campaign_batch,
)


def test_campaign_tracks_three_batches_and_cumulative_usage(tmp_path: Path) -> None:
    path = tmp_path / "campaign.json"
    for index, (attempts, tokens) in enumerate(((16, 49_000), (21, 73_000), (10, 30_000)), start=1):
        batch_id = f"batch-{index}"
        attempt_limit, token_limit = begin_campaign_batch(
            path,
            batch_id=batch_id,
            release_id=f"release-{index}",
            runtime_commit="a" * 40,
        )
        assert attempt_limit == 80
        assert token_limit == 200_000
        settle_campaign_batch(
            path,
            batch_id=batch_id,
            status="FAILED" if index < 3 else "PASSED",
            provider_http_attempts=attempts,
            total_tokens=tokens,
            ledger_reconciled=True,
        )

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["batchesUsed"] == 3
    assert state["providerHttpAttempts"] == 47
    assert state["totalTokens"] == 152_000
    with pytest.raises(CampaignBudgetError, match="batch limit"):
        begin_campaign_batch(
            path,
            batch_id="batch-4",
            release_id="release-4",
            runtime_commit="b" * 40,
        )


def test_campaign_running_or_ambiguous_batch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "campaign.json"
    begin_campaign_batch(
        path,
        batch_id="batch-running",
        release_id="release-running",
        runtime_commit="a" * 40,
    )
    with pytest.raises(CampaignBudgetError, match="unsettled"):
        begin_campaign_batch(
            path,
            batch_id="batch-second",
            release_id="release-second",
            runtime_commit="b" * 40,
        )
    with pytest.raises(CampaignBudgetError, match="ambiguous"):
        settle_campaign_batch(
            path,
            batch_id="batch-running",
            status="FAILED",
            provider_http_attempts=1,
            total_tokens=10,
            ledger_reconciled=False,
        )
    with pytest.raises(CampaignBudgetError, match="unsettled"):
        begin_campaign_batch(
            path,
            batch_id="batch-third",
            release_id="release-third",
            runtime_commit="c" * 40,
        )


def test_campaign_rejects_counts_above_reserved_batch_budget(tmp_path: Path) -> None:
    path = tmp_path / "campaign.json"
    begin_campaign_batch(
        path,
        batch_id="batch-over",
        release_id="release-over",
        runtime_commit="a" * 40,
    )
    with pytest.raises(CampaignBudgetError, match="ambiguous"):
        settle_campaign_batch(
            path,
            batch_id="batch-over",
            status="FAILED",
            provider_http_attempts=81,
            total_tokens=1,
            ledger_reconciled=True,
        )
