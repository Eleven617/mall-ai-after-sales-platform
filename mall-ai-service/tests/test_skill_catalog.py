import unittest
from unittest.mock import patch

from app.schemas.intent import IntentToolCall
from app.schemas.tool import ToolCall
from app.schemas.task_orchestration import TurnPlan
from app.services.skill_catalog import (
    SKILL_CATALOG_VERSION,
    SkillPolicyError,
    assert_skill_selected_by_role,
    assert_tool_allowed_for_skill,
    list_skill_definitions,
    select_customer_skill,
)
from app.services.tool_context import ToolExecutionContext
from app.services.tool_registry import ToolAccessDeniedError, call_tool


class SkillCatalogTests(unittest.TestCase):
    def test_committed_catalog_has_the_six_business_skills_and_versions(self) -> None:
        self.assertEqual("mall-business-skills.v1", SKILL_CATALOG_VERSION)
        skills = {skill.skill_id: skill for skill in list_skill_definitions()}
        self.assertEqual(
            {
                "policy_question_answering",
                "order_exception_diagnosis",
                "after_sales_proposal",
                "case_handoff",
                "handoff_operations_analysis",
                "quality_contract_evaluation",
            },
            set(skills),
        )
        self.assertTrue(all(skill.semantic_version.startswith("v") for skill in skills.values()))
        self.assertFalse(any(skill.deprecated_at for skill in skills.values()))

    def test_role_cannot_select_another_role_skill(self) -> None:
        with self.assertRaisesRegex(SkillPolicyError, "不可选择"):
            assert_skill_selected_by_role(
                "operations_analysis", "order_exception_diagnosis"
            )

    def test_tool_registry_denies_tool_not_in_selected_skill_before_execution(self) -> None:
        context = ToolExecutionContext(
            authorization="Bearer synthetic",
            member_id=1,
        ).for_skill("policy_question_answering")
        with patch("app.services.tool_registry.TOOLS") as tools:
            with self.assertRaisesRegex(ToolAccessDeniedError, "不允许"):
                call_tool(
                    ToolCall(name="order_service", arguments={"order_sn": "202608280001"}),
                    context,
                )

        tools.__getitem__.assert_not_called()

    def test_allowed_skill_tool_pair_remains_available(self) -> None:
        skill = assert_tool_allowed_for_skill(
            "unified_after_sales", "order_exception_diagnosis", "order_service"
        )
        self.assertEqual("order_exception_diagnosis", skill.skill_id)

    def test_diagnosis_inventory_tool_matches_the_existing_read_only_allow_list(self) -> None:
        """Avoid a catalog/Agent mismatch that would deny an advertised read."""
        skill = assert_tool_allowed_for_skill(
            "unified_after_sales", "order_exception_diagnosis", "inventory_service"
        )
        self.assertIn("inventory_service", skill.allowed_tool_ids)

    def test_customer_route_to_skill_mapping_is_closed_and_not_keyword_based(self) -> None:
        self.assertEqual(
            "policy_question_answering",
            select_customer_skill(
                plan=_customer_plan(
                    intent="after_sales_policy",
                    route="rag",
                ),
            ),
        )
        self.assertEqual(
            "order_exception_diagnosis",
            select_customer_skill(
                plan=_customer_plan(
                    intent="query_logistics",
                    route="agent",
                    task_kind="order_diagnosis",
                    tool_name="analysis_agent",
                    relation="start_new_task",
                ),
            ),
        )
        self.assertEqual(
            "after_sales_proposal",
            select_customer_skill(
                plan=_customer_plan(
                    intent="apply_after_sales",
                    route="after_sales_flow",
                    task_kind="after_sales_draft",
                    relation="start_new_task",
                ),
            ),
        )
        with self.assertRaisesRegex(SkillPolicyError, "没有可用"):
            select_customer_skill(
                plan=_customer_plan(intent="unknown", route="chat"),
            )


def _customer_plan(
    *,
    intent: str,
    route: str,
    task_kind: str | None = None,
    tool_name: str | None = None,
    relation: str = "standalone_answer",
) -> TurnPlan:
    if route == "agent":
        tool_call = IntentToolCall(name="analysis_agent", arguments={})
        need_tool = True
    elif route == "tool_calling":
        tool_call = IntentToolCall(
            name=tool_name or "order_service",
            arguments={"order_sn": "202608280001"},
        )
        need_tool = True
    else:
        tool_call = None
        need_tool = False
    return TurnPlan(
        business_intent=intent,
        task_relation=relation,
        route=route,
        task_kind=task_kind,
        confirmation_intent="none",
        rationale_code=(
            "new_long_running_goal"
            if relation == "start_new_task"
            else "standalone_question"
        ),
        need_tool=need_tool,
        tool_call=tool_call,
        reply=None,
        chat_scope=None,
    )


if __name__ == "__main__":
    unittest.main()
