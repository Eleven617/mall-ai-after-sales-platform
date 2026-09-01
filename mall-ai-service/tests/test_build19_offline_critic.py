from app.services.offline_critic import evaluate_handoff_contract


def _valid_case():
    return {
        "case_id": "12345678-1234-1234-1234-123456789abc",
        "source_flow": "customer_diagnosis",
        "diagnosis_category": "tool_failure",
        "evidence_status": "unavailable",
        "handoff_reason": "tool_failure",
        "requires_human_review": True,
        "case_status": "OPEN",
        "schema_version": "1",
    }


def test_offline_critic_accepts_safe_contract_without_network_or_mutation():
    case = _valid_case()
    report = evaluate_handoff_contract(case, {"flow": "diagnosis", "handoff": True})

    assert report["passed"] is True
    assert case == _valid_case()


def test_offline_critic_rejects_token_and_raw_order_fields():
    payload = _valid_case()
    payload["order_sn"] = "202607240001"
    payload["authorization"] = "Bearer secret"

    report = evaluate_handoff_contract(payload)

    assert report["passed"] is False
    assert "sensitive_case_field" in report["violations"]
