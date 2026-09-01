import httpx
import pytest

from app.schemas.service_case import ServiceProcessorClaimRequest
from app.services import service_operations_client


CASE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=body,
        request=httpx.Request("GET", "http://mall-admin/ai/service-operations/me"),
    )


def test_processor_client_accepts_only_dedicated_processor_profile(monkeypatch):
    monkeypatch.setattr(
        service_operations_client.httpx,
        "request",
        lambda *args, **kwargs: _response(
            200,
            {"code": 200, "data": {"username": "processor-a", "capabilities": ["service_case_handling"]}},
        ),
    )

    profile = service_operations_client.get_current_service_processor("Bearer processor-token")

    assert profile.username == "processor-a"
    assert profile.capabilities == ["service_case_handling"]


def test_processor_client_rejects_operations_role_boundary(monkeypatch):
    monkeypatch.setattr(
        service_operations_client.httpx,
        "request",
        lambda *args, **kwargs: _response(403, {"code": 403, "message": "forbidden"}),
    )

    with pytest.raises(service_operations_client.ServiceProcessorAuthenticationError) as exc_info:
        service_operations_client.get_current_service_processor("Bearer operations-token")

    assert exc_info.value.status_code == 403


def test_processor_claim_forwards_only_version_and_idempotency(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(*args, **kwargs):
        captured.update(kwargs["json"])
        return _response(
            200,
            {
                "code": 200,
                "data": {
                    "caseId": CASE_ID,
                    "queueRef": "general_after_sales",
                    "diagnosisCategory": "tool_failure",
                    "priority": "normal",
                    "state": "CLAIMED",
                    "stateVersion": 2,
                    "assignedToMe": True,
                    "publicStatus": "人工处理人员已领取",
                },
            },
        )

    monkeypatch.setattr(service_operations_client.httpx, "request", fake_request)
    result = service_operations_client.claim_service_case(
        CASE_ID,
        ServiceProcessorClaimRequest(expected_version=1, idempotency_key="a" * 32),
        "Bearer processor-token",
    )

    assert result.assigned_to_me is True
    assert captured == {"expectedVersion": 1, "idempotencyKey": "a" * 32}
