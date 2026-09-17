"""Safety contracts for the local v3.0.3 capability acceptance runner."""
from __future__ import annotations

from pathlib import Path

from scripts import verify_capability_completion_local as runner


def test_runner_requires_the_real_local_nginx_proxy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MALL_FIELD_FIXTURE_PASSWORD", "synthetic-process-only-password")
    monkeypatch.setenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:8000")

    result = runner.run_local_capability_completion(report_path=tmp_path / "report.json")

    assert result["status"] == "environment_blocked"
    assert result["reason"] == "proxy_base_not_local_nginx"
    assert result["externalProviderRequests"] == 0


def test_runner_never_persists_fixture_values_in_safe_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MALL_FIELD_FIXTURE_PASSWORD", raising=False)
    monkeypatch.delenv("MALL_LIVE_DEMO_PASSWORD", raising=False)

    result = runner.run_local_capability_completion(report_path=tmp_path / "report.json")

    assert result["status"] == "environment_blocked"
    assert result["fixture"] == {"kind": "disposable_local_synthetic", "rawValuesPersisted": False}
    # The bounded reason may say a process fixture is absent, but the report
    # must never contain any credential value.
    assert "synthetic-process-only-password" not in str(result)
