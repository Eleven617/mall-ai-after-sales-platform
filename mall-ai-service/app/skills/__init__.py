"""Versioned, domain-limited skills exposed to the Mall v3.0 Runtime."""

from app.skills.catalog import (
    SKILL_CATALOG_VERSION,
    SkillDefinition,
    discover_skills,
    get_skill,
    list_skills,
)

__all__ = [
    "SKILL_CATALOG_VERSION",
    "SkillDefinition",
    "discover_skills",
    "get_skill",
    "list_skills",
]
