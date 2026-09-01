import unittest
from unittest.mock import patch

from app.schemas.tool import ToolCall
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

    def test_customer_route_to_skill_mapping_is_closed_and_not_keyword_based(self) -> None:
        self.assertEqual(
            "policy_question_answering",
            select_customer_skill(
                intent_name="after_sales_policy",
                route="after_sales_flow",
            ),
        )
        self.assertEqual(
            "order_exception_diagnosis",
            select_customer_skill(
                intent_name="query_logistics",
                route="tool_calling",
                tool_name="logistics_service",
            ),
        )
        with self.assertRaisesRegex(SkillPolicyError, "没有可用"):
            select_customer_skill(intent_name="unknown", route="chat")


if __name__ == "__main__":
    unittest.main()
