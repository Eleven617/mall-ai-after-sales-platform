from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.quality import DeveloperProfile
from app.services.quality_developer_client import QualityDeveloperAuthenticationError
from app.services.quality_evaluation_agent import run_quality_evaluation
from app.services.quality_run_store import QualityRunStore


def test_quality_run_requires_a_developer_identity_before_running_suite():
    with (
        patch(
            "app.routers.quality.get_current_quality_developer",
            side_effect=QualityDeveloperAuthenticationError("forbidden", status_code=403),
        ),
        patch("app.routers.quality.run_quality_evaluation") as run_evaluation,
    ):
        response = TestClient(app).post(
            "/quality/evaluations/run",
            json={"enable_ai_failure_analysis": False},
            headers={"Authorization": "Bearer operations-token"},
        )

    assert response.status_code == 403
    run_evaluation.assert_not_called()


def test_quality_run_and_review_only_return_safe_result_projection(monkeypatch):
    store = QualityRunStore()
    report = run_quality_evaluation()
    monkeypatch.setattr("app.routers.quality.quality_run_store", store)
    with (
        patch("app.routers.quality.get_current_quality_developer") as get_developer,
        patch("app.routers.quality.run_quality_evaluation", return_value=report) as run_evaluation,
    ):
        get_developer.return_value = DeveloperProfile(
            username="quality-dev", capabilities=["quality_evaluation"]
        )
        client = TestClient(app)
        response = client.post(
            "/quality/evaluations/run",
            json={
                "execution_mode": "contract_mock",
                "enable_ai_failure_analysis": False,
            },
            headers={"Authorization": "Bearer developer-token"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["failed"] == 0
        assert "synthetic raw input" not in response.text
        assert "synthetic-order-value" not in response.text
        run_evaluation.assert_called_once()
        call = run_evaluation.call_args.kwargs
        assert call["execution_mode"] == "contract_mock"
        assert call["profile"].profile_id == "contract_mock"
        assert call["additional_cases"] == []
        assert call["enable_ai_failure_analysis"] is False

        reviewed = client.post(
            f"/quality/evaluations/{payload['run_id']}/cases/customer-pure-policy-consultation/review",
            json={"review_status": "APPROVED"},
            headers={"Authorization": "Bearer developer-token"},
        )

    assert reviewed.status_code == 200
    selected = next(
        item for item in reviewed.json()["cases"] if item["case_id"] == "customer-pure-policy-consultation"
    )
    assert selected["review_status"] == "APPROVED"


def test_quality_developer_can_explicitly_select_manual_live_synthetic_mode(monkeypatch):
    store = QualityRunStore()
    report = run_quality_evaluation().model_copy(
        update={"execution_mode": "live_model_synthetic"}
    )
    monkeypatch.setattr("app.routers.quality.quality_run_store", store)
    with (
        patch("app.routers.quality.get_current_quality_developer") as get_developer,
        patch("app.routers.quality.run_quality_evaluation", return_value=report) as run_evaluation,
    ):
        get_developer.return_value = DeveloperProfile(
            username="quality-dev", capabilities=["quality_evaluation"]
        )
        response = TestClient(app).post(
            "/quality/evaluations/run",
            json={
                "execution_mode": "live_model_synthetic",
                "enable_ai_failure_analysis": False,
            },
            headers={"Authorization": "Bearer developer-token"},
        )

    assert response.status_code == 200
    assert response.json()["execution_mode"] == "live_model_synthetic"
    run_evaluation.assert_called_once()
    call = run_evaluation.call_args.kwargs
    assert call["execution_mode"] == "live_model_synthetic"
    assert call["profile"].profile_id == "live_model_synthetic"
    assert call["additional_cases"] == []
    assert call["enable_ai_failure_analysis"] is False


def test_contract_mock_run_exposes_safe_replay_status_and_replays_retained_fixture(monkeypatch):
    store = QualityRunStore()
    monkeypatch.setattr("app.routers.quality.quality_run_store", store)
    developer = DeveloperProfile(username="quality-replay-dev", capabilities=["quality_evaluation"])

    with patch("app.routers.quality.get_current_quality_developer", return_value=developer):
        client = TestClient(app)
        original = client.post(
            "/quality/evaluations/run",
            json={"execution_mode": "contract_mock"},
            headers={"Authorization": "Bearer developer-token"},
        )
        assert original.status_code == 200
        original_payload = original.json()
        status = client.get(
            f"/quality/evaluations/{original_payload['run_id']}/replay-status",
            headers={"Authorization": "Bearer developer-token"},
        )
        replayed = client.post(
            f"/quality/evaluations/{original_payload['run_id']}/replay",
            headers={"Authorization": "Bearer developer-token"},
        )

    assert status.status_code == 200
    assert status.json() == {
        "run_id": original_payload["run_id"],
        "replayable": True,
        "reason_code": "synthetic_contract_fixture_retained",
    }
    assert replayed.status_code == 200
    replayed_payload = replayed.json()
    assert replayed_payload["run_id"] != original_payload["run_id"]
    assert replayed_payload["run_manifest"]["fixture_hash"] == original_payload["run_manifest"]["fixture_hash"]
    assert replayed_payload["run_manifest"]["replay_of_ref"]
    assert "syntheticInput" not in replayed.text
    assert "synthetic-order-value" not in replayed.text


def test_live_or_unretained_quality_run_cannot_be_replayed(monkeypatch):
    store = QualityRunStore()
    report = run_quality_evaluation()
    assert report.run_manifest is not None
    live_manifest = report.run_manifest.model_copy(
        update={
            "execution_mode": "live_model_synthetic",
            "replayable": False,
            "replay_reason_code": "live_model_requires_explicit_evaluation",
        }
    )
    live_report = report.model_copy(
        update={"execution_mode": "live_model_synthetic", "run_manifest": live_manifest}
    )
    store.save(live_report)
    monkeypatch.setattr("app.routers.quality.quality_run_store", store)
    developer = DeveloperProfile(username="quality-replay-dev", capabilities=["quality_evaluation"])

    with patch("app.routers.quality.get_current_quality_developer", return_value=developer):
        client = TestClient(app)
        status = client.get(
            f"/quality/evaluations/{live_report.run_id}/replay-status",
            headers={"Authorization": "Bearer developer-token"},
        )
        replayed = client.post(
            f"/quality/evaluations/{live_report.run_id}/replay",
            headers={"Authorization": "Bearer developer-token"},
        )

    assert status.status_code == 200
    assert status.json()["replayable"] is False
    assert status.json()["reason_code"] == "live_model_requires_explicit_evaluation"
    assert replayed.status_code == 409
