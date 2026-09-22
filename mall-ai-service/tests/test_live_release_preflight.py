"""Offline contracts for the v3.0.4 live-batch environment gate."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.runtime.live_release_preflight import (
    LiveReleasePreflightError,
    PASSWORD_ENV_NAME,
    require_demo_password,
    verify_local_demo_accounts,
)
from scripts import run_deepseek_release_batch as batch_runner


def test_missing_password_fails_closed_without_secret_in_error() -> None:
    with pytest.raises(LiveReleasePreflightError) as caught:
        require_demo_password({})
    assert caught.value.code == "missing_live_demo_password"
    assert "MALL_LIVE_DEMO_PASSWORD" not in str(caught.value)


def test_present_password_runs_local_account_preflight_without_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "only-for-offline-test-123"
    monkeypatch.setenv("MALL_LIVE_DEMO_PASSWORD", secret)
    calls: list[tuple[str, str]] = []

    def fake_login(client: object, java_base: str, account: object) -> tuple[str, int]:
        calls.append((java_base, getattr(account, "label")))
        return "opaque-token", len(calls)

    monkeypatch.setattr("app.runtime.live_release_preflight._ensure_login", fake_login)
    result = verify_local_demo_accounts(java_base="http://127.0.0.1:8085")
    assert result.status == "passed"
    assert result.account_count == 2
    assert [label for _, label in calls] == ["preflight_a", "preflight_b"]


def test_runner_preflight_blocks_before_batch_lock_or_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "release-lock.json"
    report = tmp_path / "report.json"
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.delenv("MALL_LIVE_DEMO_PASSWORD", raising=False)
    monkeypatch.setenv("MALL_RELEASE_LEDGER_PATH", str(ledger))
    monkeypatch.setattr(batch_runner, "_runtime_identity", lambda _commit: (True, "ok"))
    monkeypatch.setattr(batch_runner, "settings", SimpleNamespace(deepseek_model="deepseek-flash", deepseek_api_key="fixture"))
    with patch.object(sys, "argv", [
        "runner",
        "--phase", "portfolio_final",
        "--release-id", "mall-v3.0.4-preflight-test",
        "--runtime-commit", "a" * 40,
        "--report", str(report),
        "--lock", str(lock),
    ]):
        assert batch_runner.main() == 2
    assert not lock.exists()
    assert not report.exists()
    assert not ledger.exists()


def test_preflight_failure_text_never_contains_password_or_provider_payload() -> None:
    secret = "only-for-offline-test-123"
    with pytest.raises(LiveReleasePreflightError) as caught:
        require_demo_password({"MALL_LIVE_DEMO_PASSWORD": "password"})
    serialized = json.dumps({"failureCode": caught.value.code})
    assert secret not in serialized


def test_environment_name_is_consistent_across_runner_compose_and_powershell() -> None:
    root = Path(__file__).resolve().parents[2]
    sources = [
        root / "mall-ai-service" / "scripts" / "run_real_local_showcase.py",
        root / "mall-ai-service" / "scripts" / "run_live_release_preflight.py",
        root / "mall-ai-service" / "app" / "runtime" / "live_release_preflight.py",
        root / "scripts" / "Run-V3_0_4-Portfolio-Release.ps1",
        root / "docker-compose.yml",
    ]
    for source in sources:
        assert PASSWORD_ENV_NAME in source.read_text(encoding="utf-8")


def test_compose_prompt_identity_matches_runtime_protocol() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "MALL_PROMPT_VERSION: ${MALL_PROMPT_VERSION:-agent_runtime_v3_5}" in compose


def test_v304_final_entry_is_a_real_single_batch_path_with_ephemeral_password() -> None:
    root = Path(__file__).resolve().parents[2]
    content = (root / "scripts" / "Run-V3_0_4-Portfolio-Release.ps1").read_text(encoding="utf-8")
    assert "New-TemporaryDemoPassword" in content
    assert "MALL_FIELD_FIXTURE_PASSWORD" in content
    assert "run_live_release_preflight.py" in content
    assert "run_deepseek_release_batch.py" in content
    assert "FINAL_ONLINE_BATCH_REQUIRES_EXPLICIT_AUTHORIZATION" not in content
    assert "MALL_RELEASE_LEDGER_PATH" in content
    assert "release_entry_contract.py" in content
    assert "ledger_initialization_failed" in content
    assert "ledger_mount_missing" in content
    assert "ledger_container_not_readwrite" in content
    assert "docker compose exec -T mall-ai-service" in content
    assert "deepseek-release-lock-$ReleaseId.json" in content
    assert "--phase minimal_retest" in content
    assert "--campaign $campaignPath" in content
    assert "Get-BoundedReleaseLimit $previousMaxAttempts 80" in content
    assert "Get-BoundedReleaseLimit $previousMaxTokens 200000" in content
    assert "GetEnvironmentVariable('MALL_LIVE_DEMO_PASSWORD', 'User')" in content
    assert "docker compose up -d --no-deps --force-recreate mall-ai-service" in content


def test_v304_final_entry_restores_frozen_offline_runtime_identity() -> None:
    root = Path(__file__).resolve().parents[2]
    content = (root / "scripts" / "Run-V3_0_4-Portfolio-Release.ps1").read_text(encoding="utf-8")

    restore_marker = "# Compose build args and container identity default to"
    restore = content[content.index(restore_marker) :]
    assert "SetEnvironmentVariable('MALL_RUNTIME_PROVIDER_MODE', 'deterministic', 'Process')" in restore
    assert "SetEnvironmentVariable('MALL_PROVIDER_LIVE_AUTH', '0', 'Process')" in restore
    assert "SetEnvironmentVariable('MALL_RUNTIME_COMMIT', $RuntimeCommit, 'Process')" in restore
    assert "SetEnvironmentVariable('MALL_IMAGE_REVISION', $RuntimeCommit, 'Process')" in restore
    assert "restoredVersion.runtimeCommit -eq $RuntimeCommit" in restore
    assert "restoredVersion.imageRevision -eq $RuntimeCommit" in restore
    assert "restoredVersion.providerMode -eq 'deterministic'" in restore
    assert restore.index("docker compose up -d --no-deps --force-recreate mall-ai-service") < restore.index(
        "Remove-Item Env:MALL_RUNTIME_PROVIDER_MODE"
    )
