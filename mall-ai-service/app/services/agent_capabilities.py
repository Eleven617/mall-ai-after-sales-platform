"""Explicit capability profiles used to keep the three agents independent."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentCapability:
    name: str
    data_scope: tuple[str, ...]
    tools: tuple[str, ...]
    max_steps: int
    writes: tuple[str, ...]


CUSTOMER_DIAGNOSIS_CAPABILITY = AgentCapability(
    name="customer_diagnosis",
    data_scope=("current_member_orders", "logistics_facts", "policy_evidence"),
    tools=("order_service", "logistics_service", "inventory_service", "rag_search"),
    max_steps=7,
    writes=("confirmed_return_workflow",),
)

OPERATIONS_ANALYSIS_CAPABILITY = AgentCapability(
    name="operations_analysis",
    data_scope=("case_handoff_projection", "aggregate_after_sales_metrics"),
    tools=("read_case_handoff", "read_after_sales_metrics"),
    max_steps=2,
    writes=(),
)

QUALITY_EVALUATION_CAPABILITY = AgentCapability(
    name="quality_evaluation",
    data_scope=("versioned_synthetic_eval_cases", "safe_output_projections"),
    tools=("mock_customer_diagnosis", "mock_operations_analysis", "offline_contract_checks"),
    max_steps=2,
    writes=(),
)


def capability_profiles() -> tuple[AgentCapability, ...]:
    return (
        CUSTOMER_DIAGNOSIS_CAPABILITY,
        OPERATIONS_ANALYSIS_CAPABILITY,
        QUALITY_EVALUATION_CAPABILITY,
    )
