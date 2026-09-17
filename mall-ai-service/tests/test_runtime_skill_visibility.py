from app.skills.catalog import (
    confirmation_executor_skill,
    discover_skills,
    list_backlog_skills,
    list_internal_skills,
    validate_catalog_consistency,
)


def test_model_visible_catalog_has_real_paths_and_no_backlog_or_internal_entries():
    assert validate_catalog_consistency() == []
    visible = {skill.skill_id for skill in discover_skills("人工售后草案")}
    assert "open_human_case" in visible
    assert "create_after_sales_draft" in visible
    assert "commit_after_sales_action" not in visible
    assert "commit_human_case" not in visible
    assert "amend_after_sales_draft" not in visible
    assert "request_customer_evidence" not in visible
    assert "schedule_follow_up" not in visible


def test_internal_mappings_are_exact_and_backlog_is_preserved():
    assert confirmation_executor_skill("create_after_sales_draft").skill_id == "commit_after_sales_action"
    assert confirmation_executor_skill("open_human_case").skill_id == "commit_human_case"
    assert {skill.skill_id for skill in list_internal_skills()} == {
        "amend_after_sales_draft",
        "commit_after_sales_action",
        "commit_human_case",
    }
    assert {skill.skill_id for skill in list_backlog_skills()} == {
        "request_customer_evidence",
        "schedule_follow_up",
    }
