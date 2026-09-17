import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.llm_service import LLMServiceError, generate_text
from app.services.provider_guard import provider_access_context


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "synthetic"}}]}


def _settings():
    return SimpleNamespace(
        deepseek_api_key="fixture-key",
        deepseek_model="deepseek-flash",
        deepseek_base_url="https://provider.invalid",
        deepseek_timeout_seconds=1.0,
    )


def test_key_alone_is_not_authorization_and_http_is_not_called():
    with patch("app.services.llm_service.settings", _settings()), patch("app.services.llm_service.httpx.post") as post:
        with pytest.raises(LLMServiceError) as raised:
            generate_text("synthetic")
    assert raised.value.category == "provider_guard"
    post.assert_not_called()


@pytest.mark.parametrize("missing", ["release_id", "batch_id", "ledger_path", "runtime_commit"])
def test_formal_live_context_missing_one_field_fails_closed(missing):
    values = {
        "release_id": "release-test",
        "batch_id": "batch-test",
        "ledger_path": "C:/fixture/ledger.jsonl",
        "runtime_commit": "a" * 40,
    }
    values[missing] = None
    with patch("app.services.llm_service.settings", _settings()), patch("app.services.llm_service.httpx.post") as post:
        with provider_access_context(mode="live", authorized=True, **values):
            with pytest.raises(LLMServiceError) as raised:
                generate_text("synthetic")
    assert raised.value.category == "provider_guard"
    post.assert_not_called()


def test_complete_mock_context_is_the_only_unit_fixture_that_allows_mock_http():
    with patch("app.services.llm_service.settings", _settings()), patch(
        "app.services.llm_service.httpx.post", return_value=_Response()
    ) as post:
        with provider_access_context(
            mode="mock",
            release_id="release-test",
            batch_id="batch-test",
            ledger_path="C:/fixture/ledger.jsonl",
            runtime_commit="a" * 40,
            authorized=True,
            allow_mock=True,
        ):
            assert generate_text("synthetic") == "synthetic"
    assert post.call_count == 1


def test_environment_key_and_live_mode_without_explicit_auth_stay_blocked():
    with patch.dict(
        os.environ,
        {
            "MALL_RUNTIME_PROVIDER_MODE": "live",
            "MALL_PROVIDER_LIVE_AUTH": "0",
            "MALL_RELEASE_ID": "release-test",
            "MALL_RELEASE_BATCH_ID": "batch-test",
            "MALL_RELEASE_LEDGER_PATH": "C:/fixture/ledger.jsonl",
            "MALL_RUNTIME_COMMIT": "a" * 40,
        },
        clear=False,
    ), patch("app.services.llm_service.settings", _settings()), patch("app.services.llm_service.httpx.post") as post:
        with pytest.raises(LLMServiceError):
            generate_text("synthetic")
    post.assert_not_called()
