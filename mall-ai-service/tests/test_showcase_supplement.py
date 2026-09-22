from pathlib import Path

from scripts.run_showcase_supplement import run_showcase_supplement


def test_supplement_refuses_wrong_release_or_budget_before_artifacts(tmp_path, monkeypatch) -> None:
    lock = tmp_path / "lock.json"
    report = tmp_path / "report.json"
    monkeypatch.setenv("MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS", "40")
    monkeypatch.setenv("MALL_RELEASE_MAX_TOTAL_TOKENS", "100000")

    assert run_showcase_supplement(
        release_id="mall-v3.0.4-not-a-supplement",
        runtime_commit="0" * 40,
        report_path=report,
        lock_path=lock,
    ) == 3
    assert not lock.exists()
    assert not report.exists()

    monkeypatch.setenv("MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS", "41")
    assert run_showcase_supplement(
        release_id="mall-v3.0.4-showcase-supplement-test",
        runtime_commit="0" * 40,
        report_path=report,
        lock_path=lock,
    ) == 3
    assert not lock.exists()
    assert not report.exists()
