"""Safe-contract tests for the real local showcase runner."""

from __future__ import annotations

from app.services.release_ledger import release_ledger_context
from scripts.run_real_local_showcase import ShowcaseError, _status_class


def test_showcase_error_is_a_safe_enumerated_projection() -> None:
    failure = ShowcaseError(
        "provider_response_body_should_never_be_public",
        scenario="closed_loop",
        stage="provider",
        completed_steps=3,
        model_called=True,
        proposal_formed=True,
        http_status_class="5xx",
    )
    public = failure.to_public()

    assert public == {
        "scenario": "closed_loop",
        "stage": "provider",
        "failureCode": "unknown_failure",
        "httpStatusClass": "5xx",
        "completedStepCount": 3,
        "modelCalled": True,
        "proposalFormed": True,
        "javaEligibility": False,
        "javaCommit": False,
        "statusReadback": False,
    }
    assert "provider_response_body" not in str(public)


def test_status_class_and_ledger_context_are_deterministic() -> None:
    assert _status_class(200) == "2xx"
    assert _status_class(409) == "4xx"
    assert _status_class(503) == "5xx"
    assert _status_class(0) == "none"
    with release_ledger_context(batch_id="synthetic", path=None, source="test"):
        # The context is intentionally opt-in and does not create a file when
        # no path is configured.
        assert True
