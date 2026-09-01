from app.services.agent_capabilities import (
    CUSTOMER_DIAGNOSIS_CAPABILITY,
    OPERATIONS_ANALYSIS_CAPABILITY,
    QUALITY_EVALUATION_CAPABILITY,
    capability_profiles,
)


def test_build19_profiles_have_independent_scopes_and_writes():
    profiles = {profile.name: profile for profile in capability_profiles()}

    assert profiles["customer_diagnosis"].tools
    assert profiles["customer_diagnosis"].writes == ("confirmed_return_workflow",)
    assert profiles["operations_analysis"].writes == ()
    assert profiles["quality_evaluation"].writes == ()
    assert "member_orders" not in profiles["operations_analysis"].data_scope
    assert "synthetic_cases" not in profiles["operations_analysis"].data_scope
    assert CUSTOMER_DIAGNOSIS_CAPABILITY.name != OPERATIONS_ANALYSIS_CAPABILITY.name
    assert QUALITY_EVALUATION_CAPABILITY.max_steps == 2
    assert "production_trace" not in profiles["quality_evaluation"].data_scope
