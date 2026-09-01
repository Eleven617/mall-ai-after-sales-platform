from unittest.mock import patch

import httpx
import pytest

from app.schemas.quality import DeveloperProfile
from app.services.quality_developer_client import (
    QualityDeveloperAuthenticationError,
    get_current_quality_developer,
    login_quality_developer,
)


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "http://mall-admin.test"),
    )


@patch("app.services.quality_developer_client.httpx.get")
def test_get_current_quality_developer_accepts_only_the_safe_profile(get):
    get.return_value = _response(
        200,
        {"code": 200, "data": {"username": "quality-dev", "capabilities": ["quality_evaluation"]}},
    )

    profile = get_current_quality_developer("Bearer developer-token")

    assert profile.username == "quality-dev"
    assert profile.capabilities == ["quality_evaluation"]


@patch("app.services.quality_developer_client.httpx.get")
def test_get_current_quality_developer_rejects_operations_or_customer_boundary(get):
    get.return_value = _response(403, {"code": 403, "message": "forbidden"})

    with pytest.raises(QualityDeveloperAuthenticationError) as exc_info:
        get_current_quality_developer("Bearer non-developer-token")

    assert exc_info.value.status_code == 403


@patch("app.services.quality_developer_client.get_current_quality_developer")
@patch("app.services.quality_developer_client.httpx.post")
def test_login_proves_dedicated_developer_role_before_returning_token(post, get_current):
    post.return_value = _response(
        200,
        {"code": 200, "data": {"token": "java-token", "tokenHead": "Bearer"}},
    )
    get_current.return_value = DeveloperProfile(
        username="quality-dev", capabilities=["quality_evaluation"]
    )

    result = login_quality_developer("quality-dev", "not-a-real-password")

    assert result.authorization == "Bearer java-token"
    assert result.developer.username == "quality-dev"
