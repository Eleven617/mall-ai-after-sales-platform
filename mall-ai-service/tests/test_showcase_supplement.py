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


def test_supplement_metrics_accept_ledger_denied_before_network_name(monkeypatch) -> None:
    from scripts import run_showcase_supplement as module

    monkeypatch.setenv("MALL_RELEASE_LEDGER_PATH", "unused")
    monkeypatch.setattr(
        module,
        "read_release_events",
        lambda path, batch_id=None: [],
    )
    monkeypatch.setattr(
        module,
        "summarize_release_events",
        lambda events: {
            "logicalProviderRequests": 14,
            "providerHttpAttempts": 14,
            "providerSuccesses": 14,
            "providerFailures": 0,
            "totalTokens": 48862,
            "reservations": 14,
            "settlements": 14,
            "unresolvedReservations": 0,
            "deniedBeforeNetwork": 0,
        },
    )

    assert module._metrics("batch") == {
        "logicalProviderRequests": 14,
        "providerHttpAttempts": 14,
        "successfulRequests": 14,
        "failedRequests": 0,
        "totalTokens": 48862,
        "reservations": 0,
        "settlements": 0,
        "unresolvedReservations": 0,
        "budgetDenials": 0,
        "ledgerReconciled": True,
    }
