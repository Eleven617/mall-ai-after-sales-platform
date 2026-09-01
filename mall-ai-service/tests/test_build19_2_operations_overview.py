from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.operations import HandoffCategorySummary, HandoffOverview, OperatorProfile
from app.services.operations_client import OperationsAuthenticationError


def _overview(window_days: int = 7) -> HandoffOverview:
    return HandoffOverview(
        window_days=window_days,
        window_start="2026-08-13 12:00:00",
        window_end="2026-08-20 12:00:00",
        total_unique_handoffs=4,
        categories=[
            HandoffCategorySummary(category="delivery_exception", count=3, percentage=75),
            HandoffCategorySummary(category="other_pending_classification", count=1, percentage=25),
        ],
    )


def test_handoff_overview_is_java_aggregate_only_and_accepts_the_selected_window():
    with (
        patch("app.routers.operations.get_current_operator") as get_operator,
        patch("app.routers.operations.get_handoff_overview") as get_overview,
    ):
        get_operator.return_value = OperatorProfile(
            username="operations-user", capabilities=["operations_analysis"]
        )
        get_overview.return_value = _overview(30)

        response = TestClient(app).get(
            "/operations/handoff-overview?windowDays=30",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 200
    assert response.json()["total_unique_handoffs"] == 4
    assert response.json()["categories"][1]["percentage"] == 25
    get_overview.assert_called_once_with(30, "Bearer operator-token")


def test_handoff_overview_rejects_invalid_window_without_contacting_java():
    with patch("app.routers.operations.get_current_operator") as get_operator:
        response = TestClient(app).get(
            "/operations/handoff-overview?windowDays=14",
            headers={"Authorization": "Bearer operator-token"},
        )

    assert response.status_code == 400
    get_operator.assert_not_called()


def test_handoff_overview_keeps_customer_token_out_of_operations_boundary():
    with patch(
        "app.routers.operations.get_current_operator",
        side_effect=OperationsAuthenticationError("请先以运营身份登录。", status_code=401),
    ):
        response = TestClient(app).get(
            "/operations/handoff-overview",
            headers={"Authorization": "Bearer customer-token"},
        )

    assert response.status_code == 401
