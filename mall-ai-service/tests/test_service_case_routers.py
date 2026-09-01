from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.authentication import MemberProfile
from app.schemas.service_case import (
    CustomerServiceCaseView,
    ServiceProcessorCaseView,
    ServiceProcessorProfile,
)
from app.services.mall_client import MallAuthenticationError
from app.services.service_operations_client import ServiceProcessorAuthenticationError


CASE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _customer_case() -> CustomerServiceCaseView:
    return CustomerServiceCaseView(
        case_id=CASE_ID,
        category="tool_failure",
        state="QUEUED",
        state_version=1,
        public_status="已转人工处理",
        customer_information_required=False,
        can_cancel=True,
        can_reopen=False,
    )


def _processor_case() -> ServiceProcessorCaseView:
    return ServiceProcessorCaseView(
        case_id=CASE_ID,
        queue_ref="general_after_sales",
        diagnosis_category="tool_failure",
        priority="normal",
        state="QUEUED",
        state_version=1,
        assigned_to_me=False,
        public_status="已转人工处理",
    )


def test_customer_service_case_route_verifies_member_then_returns_safe_projection():
    with (
        patch("app.routers.customer_service.get_current_member") as current_member,
        patch("app.routers.customer_service.list_my_service_cases") as list_cases,
    ):
        current_member.return_value = MemberProfile(member_id=7, username="member-a")
        list_cases.return_value = [_customer_case()]
        response = TestClient(app).get(
            "/customer-service/service-cases", headers={"Authorization": "Bearer customer-token"}
        )

    assert response.status_code == 200
    assert response.json()[0]["case_id"] == CASE_ID
    for forbidden in ("member_id", "queue_ref", "assignee_ref", "internal_note", "trace"):
        assert forbidden not in response.text
    list_cases.assert_called_once_with("Bearer customer-token")


def test_customer_service_case_write_stops_before_java_on_unauthenticated_request():
    with (
        patch("app.routers.customer_service.get_current_member") as current_member,
        patch("app.routers.customer_service.cancel_my_service_case") as cancel_case,
    ):
        current_member.side_effect = MallAuthenticationError("请先登录后再继续。", 401)
        response = TestClient(app).post(
            f"/customer-service/service-cases/{CASE_ID}/cancel",
            json={"expected_version": 1, "idempotency_key": "a" * 32},
        )

    assert response.status_code == 401
    cancel_case.assert_not_called()


def test_processor_route_requires_its_own_profile_and_never_calls_customer_boundary():
    with (
        patch("app.routers.service_operations.get_current_service_processor") as current_processor,
        patch("app.routers.service_operations.list_service_processor_cases") as list_cases,
    ):
        current_processor.return_value = ServiceProcessorProfile(
            username="processor-a", capabilities=["service_case_handling"]
        )
        list_cases.return_value = [_processor_case()]
        response = TestClient(app).get(
            "/service-operations/cases", headers={"Authorization": "Bearer processor-token"}
        )

    assert response.status_code == 200
    assert response.json()[0]["case_id"] == CASE_ID
    assert "member_id" not in response.text
    list_cases.assert_called_once_with("Bearer processor-token", 30)


def test_customer_or_operations_token_is_rejected_before_processor_case_read():
    with (
        patch("app.routers.service_operations.get_current_service_processor") as current_processor,
        patch("app.routers.service_operations.list_service_processor_cases") as list_cases,
    ):
        current_processor.side_effect = ServiceProcessorAuthenticationError(
            "当前账号没有人工售后处理权限。", status_code=403
        )
        response = TestClient(app).get(
            "/service-operations/cases", headers={"Authorization": "Bearer non-processor-token"}
        )

    assert response.status_code == 403
    list_cases.assert_not_called()
