import httpx
import pytest

from app.services import operations_client


def test_legacy_business_unauthorized_result_maps_to_http_401(monkeypatch):
    def fake_get(*args, **kwargs):
        return httpx.Response(
            200,
            json={
                "code": 401,
                "message": "暂未登录或token已经过期",
                "data": "Full authentication is required",
            },
            request=httpx.Request("GET", "http://mall-admin/ai/operations/cases"),
        )

    monkeypatch.setattr(operations_client.httpx, "get", fake_get)

    with pytest.raises(operations_client.OperationsAuthenticationError) as error:
        operations_client.list_case_handoffs("Bearer expired-token")

    assert error.value.status_code == 401


def test_missing_case_preserves_the_java_not_found_status(monkeypatch):
    def fake_get(*args, **kwargs):
        return httpx.Response(
            404,
            json={"status": 404, "error": "Not Found"},
            request=httpx.Request("GET", "http://mall-admin/ai/operations/cases/missing"),
        )

    monkeypatch.setattr(operations_client.httpx, "get", fake_get)

    with pytest.raises(operations_client.OperationsApiError) as error:
        operations_client.get_case_handoff(
            "00000000-0000-0000-0000-000000000000", "Bearer operator-token"
        )

    assert error.value.status_code == 404
