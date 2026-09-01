from app.schemas.agent_ops import CustomerFeedbackRequest, FeedbackCandidateCreateRequest
from app.schemas.quality import EvalCase
from app.services.evaluation_profile_service import get_evaluation_profile
from app.services.feedback_governance_service import (
    FeedbackGovernanceError,
    FeedbackGovernanceStore,
)
from app.services.quality_evaluation_agent import run_quality_evaluation
from app.services.request_context import request_correlation
from pydantic import ValidationError


def _safe_synthetic_case() -> EvalCase:
    return EvalCase.model_validate(
        {
            "caseId": "feedback-synthetic-policy",
            "targetAgent": "customer_diagnosis",
            "syntheticInput": "虚构政策咨询：退货时效如何计算？",
            "expectedContract": {
                "allowedCategories": ["policy_consultation"],
                "forbiddenCategories": ["tool_failure"],
                "caseHandoffAllowed": False,
                "businessWriteAllowed": False,
                "forbiddenFields": ["token", "order_sn"],
            },
            "expectedTrajectory": {"maxSteps": 1},
            "schemaVersion": "1",
        },
        strict=True,
        extra="forbid",
    )


def test_feedback_requires_owner_consent_and_human_approval_before_evalcase():
    store = FeedbackGovernanceStore()
    response_ref = store.register_response(member_id=101, session_id="scoped-session")
    feedback = store.submit_feedback(
        member_id=101,
        request=CustomerFeedbackRequest(
            responseRef=response_ref,
            helpful=False,
            reasonCode="policy_not_supported",
            consent=True,
        ),
    )
    case = _safe_synthetic_case()
    candidate = store.create_candidate(
        FeedbackCandidateCreateRequest(
            feedbackId=feedback.feedback_id,
            sanitizedScenario=case.synthetic_input,
            evalCase=case,
        )
    )

    assert store.approved_eval_cases() == []
    approved = store.approve_candidate(candidate.candidate_id)
    assert approved.review_status == "APPROVED"
    assert [case.case_id for case in store.approved_eval_cases()] == [case.case_id]


def test_feedback_cannot_be_reused_by_another_member_or_contain_customer_like_data():
    store = FeedbackGovernanceStore()
    response_ref = store.register_response(member_id=101, session_id="scoped-session")
    request = CustomerFeedbackRequest(
        responseRef=response_ref,
        helpful=False,
        reasonCode="other",
        consent=True,
    )

    try:
        store.submit_feedback(member_id=202, request=request)
    except FeedbackGovernanceError as exc:
        assert "不属于当前会员" in str(exc)
    else:
        raise AssertionError("cross-member feedback reference must be rejected")

    feedback = store.submit_feedback(member_id=101, request=request)
    unsafe_case = _safe_synthetic_case().model_copy(
        update={"synthetic_input": "订单 20260831001 的真实客户问题"}
    )
    try:
        store.create_candidate(
            FeedbackCandidateCreateRequest(
                feedbackId=feedback.feedback_id,
                sanitizedScenario=unsafe_case.synthetic_input,
                evalCase=unsafe_case,
            )
        )
    except FeedbackGovernanceError as exc:
        assert "合成数据" in str(exc)
    else:
        raise AssertionError("customer-like fixture must be rejected")


def test_profile_run_emits_safe_versioned_manifest_without_fixture_text():
    profile = get_evaluation_profile("contract_mock")
    with request_correlation("0123456789abcdef"):
        report = run_quality_evaluation(profile=profile)

    manifest = report.run_manifest
    assert manifest is not None
    assert report.profile_id == "contract_mock"
    assert manifest.profile_version == "v1"
    assert manifest.correlation_ref != "0123456789abcdef"
    serialized = manifest.model_dump_json()
    assert "syntheticInput" not in serialized
    assert "订单" not in serialized


def test_customer_feedback_reason_code_is_a_closed_product_contract():
    response_ref = "11111111-1111-4111-8111-111111111111"
    allowed = {
        "factual_mismatch",
        "policy_not_supported",
        "unclear_explanation",
        "response_too_slow",
        "tool_unavailable",
        "other",
    }
    for reason_code in allowed:
        request = CustomerFeedbackRequest(
            responseRef=response_ref,
            helpful=False,
            reasonCode=reason_code,
            consent=True,
        )
        assert request.reason_code == reason_code

    try:
        CustomerFeedbackRequest(
            responseRef=response_ref,
            helpful=False,
            reasonCode="evidence_insufficient",
            consent=True,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("legacy feedback code must not remain accepted")


def test_deleting_a_conversation_removes_only_its_ephemeral_feedback_chain():
    store = FeedbackGovernanceStore()
    first_ref = store.register_response(member_id=101, session_id="member-101:conversation-a")
    second_ref = store.register_response(member_id=101, session_id="member-101:conversation-b")
    first_feedback = store.submit_feedback(
        member_id=101,
        request=CustomerFeedbackRequest(
            responseRef=first_ref,
            helpful=False,
            reasonCode="other",
            consent=True,
        ),
    )
    second_feedback = store.submit_feedback(
        member_id=101,
        request=CustomerFeedbackRequest(
            responseRef=second_ref,
            helpful=True,
            reasonCode="unclear_explanation",
            consent=True,
        ),
    )
    first_candidate = store.create_candidate(
        FeedbackCandidateCreateRequest(
            feedbackId=first_feedback.feedback_id,
            sanitizedScenario=_safe_synthetic_case().synthetic_input,
            evalCase=_safe_synthetic_case(),
        )
    )
    second_case = _safe_synthetic_case().model_copy(update={"case_id": "feedback-synthetic-policy-b"})
    second_candidate = store.create_candidate(
        FeedbackCandidateCreateRequest(
            feedbackId=second_feedback.feedback_id,
            sanitizedScenario=second_case.synthetic_input,
            evalCase=second_case,
        )
    )

    deleted = store.delete_session_data(member_id=101, session_id="member-101:conversation-a")

    assert deleted == {"responses": 1, "feedback": 1, "candidates": 1}
    assert [candidate.candidate_id for candidate in store.list_candidates()] == [second_candidate.candidate_id]
    try:
        store.submit_feedback(
            member_id=101,
            request=CustomerFeedbackRequest(
                responseRef=first_ref,
                helpful=False,
                reasonCode="other",
                consent=True,
            ),
        )
    except FeedbackGovernanceError:
        pass
    else:
        raise AssertionError("deleted conversation feedback reference must not be reusable")
    assert first_candidate.candidate_id != second_candidate.candidate_id
