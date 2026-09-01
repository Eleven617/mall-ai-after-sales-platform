from types import SimpleNamespace

import httpx

from app.schemas.diagnosis import DiagnosisHandoff, DiagnosisResult
from app.services import case_handoff_service


def _diagnosis():
    return DiagnosisResult(
        category="tool_failure",
        evidence_status="unavailable",
        handoff=DiagnosisHandoff(
            reason="tool_failure",
            summary="需要人工核实",
            verified_source_types=[],
        ),
    )


def test_case_key_is_stable_without_raw_message():
    first = case_handoff_service._build_case_key("member-scoped-session", _diagnosis())
    second = case_handoff_service._build_case_key("member-scoped-session", _diagnosis())

    assert first == second
    assert len(first) == 64
    assert "需要人工核实" not in first


def test_register_handoff_sends_only_allow_listed_fields(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "caseId": "12345678-1234-1234-1234-123456789abc",
                    "sourceFlow": "customer_diagnosis",
                    "diagnosisCategory": "tool_failure",
                    "evidenceStatus": "unavailable",
                    "handoffReason": "tool_failure",
                    "requiresHumanReview": True,
                    "caseStatus": "OPEN",
                    "schemaVersion": "1",
                },
            },
            request=httpx.Request("POST", "http://mall"),
        )

    monkeypatch.setattr(case_handoff_service.httpx, "post", fake_post)
    result = case_handoff_service.register_case_handoff(
        session_id="member-scoped-session",
        diagnosis=_diagnosis(),
        authorization="Bearer customer-token",
    )

    assert result.case_id.startswith("12345678")
    assert set(captured["json"]) == {
        "caseKey",
        "sourceFlow",
        "diagnosisCategory",
        "evidenceStatus",
        "handoffReason",
        "requiresHumanReview",
        "schemaVersion",
    }
    assert "Authorization" in captured["headers"]
    assert captured["headers"]["Authorization"] == "Bearer customer-token"
