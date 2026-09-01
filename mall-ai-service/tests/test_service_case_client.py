import httpx
import pytest

from app.schemas.service_case import (
    CustomerServiceCaseCancelRequest,
    CustomerServiceCaseInformationRequest,
)
from app.services import service_case_client


CASE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=body,
        request=httpx.Request("GET", "http://mall-portal/service-cases/mine"),
    )


def _public_case(**extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "caseId": CASE_ID,
        "category": "tool_failure",
        "state": "QUEUED",
        "stateVersion": 1,
        "publicStatus": "已转人工处理",
        "customerInformationRequired": False,
        "canCancel": True,
        "canReopen": False,
        "lastPublicMessage": "已创建人工协同事项。",
    }
    result.update(extra)
    return result


def test_customer_case_client_rejects_java_private_fields(monkeypatch):
    monkeypatch.setattr(
        service_case_client.httpx,
        "request",
        lambda *args, **kwargs: _response(200, {"code": 200, "data": [_public_case(memberId=7)]}),
    )

    with pytest.raises(service_case_client.ServiceCaseApiError):
        service_case_client.list_my_service_cases("Bearer customer-token")


def test_customer_case_client_maps_conflict_without_replaying_write(monkeypatch):
    called: list[dict] = []

    def fake_request(*args, **kwargs):
        called.append(kwargs["json"])
        return _response(409, {"code": 409, "message": "案件状态已变化"})

    monkeypatch.setattr(service_case_client.httpx, "request", fake_request)
    request = CustomerServiceCaseCancelRequest(expected_version=2, idempotency_key="a" * 32)

    with pytest.raises(service_case_client.ServiceCaseApiError) as exc_info:
        service_case_client.cancel_my_service_case(CASE_ID, request, "Bearer customer-token")

    assert exc_info.value.status_code == 409
    assert called == [{"expectedVersion": 2, "idempotencyKey": "a" * 32}]


def test_customer_case_client_requires_bearer_before_network_call():
    with pytest.raises(service_case_client.ServiceCaseAuthenticationError) as exc_info:
        service_case_client.list_my_service_cases(None)

    assert exc_info.value.status_code == 401


def test_customer_case_client_rejects_awaiting_case_without_server_required_type(monkeypatch):
    monkeypatch.setattr(
        service_case_client.httpx,
        "request",
        lambda *args, **kwargs: _response(
            200,
            {
                "code": 200,
                "data": [
                    _public_case(
                        state="AWAITING_CUSTOMER_INFORMATION",
                        customerInformationRequired=True,
                    )
                ],
            },
        ),
    )

    with pytest.raises(service_case_client.ServiceCaseApiError):
        service_case_client.list_my_service_cases("Bearer customer-token")


def test_customer_information_forwards_only_server_selected_allow_list_type(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(*args, **kwargs):
        captured.update(kwargs["json"])
        return _response(
            200,
            {
                "code": 200,
                "data": _public_case(
                    state="IN_REVIEW",
                    customerInformationRequired=False,
                    requiredInformationType=None,
                ),
            },
        )

    monkeypatch.setattr(service_case_client.httpx, "request", fake_request)
    result = service_case_client.submit_customer_information(
        CASE_ID,
        CustomerServiceCaseInformationRequest(
            expected_version=1,
            idempotency_key="a" * 32,
            information_type="purchase_context",
            information="在签收后第一次使用时发现问题。",
        ),
        "Bearer customer-token",
    )

    assert result.state == "IN_REVIEW"
    assert captured == {
        "expectedVersion": 1,
        "idempotencyKey": "a" * 32,
        "informationType": "purchase_context",
        "information": "在签收后第一次使用时发现问题。",
    }
