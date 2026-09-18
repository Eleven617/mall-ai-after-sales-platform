"""Offline semantic audit for versioned live-agent evaluation suites.

The audit is intentionally provider-free.  It validates that a case's stated
post-checks and proposal contract are reachable from its reviewed fixture and
does not execute a model, Java service, or business write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.runtime.live_model_agent_evaluation import fixture_hash, load_live_agent_suite  # noqa: E402
from app.skills.catalog import get_skill  # noqa: E402


_APPLICATION_TYPES = ("取消退款", "退货退款", "换货", "维修", "cancel_refund", "return_refund", "exchange", "repair")


def _has_explicit_type(goal: str) -> bool:
    return any(value in goal for value in _APPLICATION_TYPES)


def audit_suite(path: Path) -> list[str]:
    errors: list[str] = []
    suite = load_live_agent_suite(path)
    seen_ids: set[str] = set()
    seen_goals: set[str] = set()
    for case in suite["cases"]:
        case_id = str(case["caseId"])
        if case_id in seen_ids:
            errors.append(f"{case_id}: duplicate caseId")
        seen_ids.add(case_id)
        goal = str(case.get("goal", ""))
        if goal in seen_goals:
            errors.append(f"{case_id}: goal duplicated within suite")
        seen_goals.add(goal)
        fixture = case.get("fixture")
        if not isinstance(fixture, Mapping):
            errors.append(f"{case_id}: fixture missing")
            continue
        if case.get("fixtureHash") != fixture_hash(fixture):
            errors.append(f"{case_id}: fixtureHash mismatch")
        expect = case.get("expect") or {}
        observations = fixture.get("observations") or {}
        proposal_mode = expect.get("proposal", "not_required")
        if proposal_mode == "required":
            if not _has_explicit_type(goal):
                errors.append(f"{case_id}: required proposal without explicit application type")
            if "read_order" not in observations:
                errors.append(f"{case_id}: required proposal without order_fact observation")
            if "build_service_resolution" not in observations:
                errors.append(f"{case_id}: required proposal without resolution_candidate observation")
        if "expire_proposal" in (expect.get("post") or ()) or "duplicate_confirmation" in (expect.get("post") or ()):
            if proposal_mode != "required":
                errors.append(f"{case_id}: proposal post-check requires proposal=required")
        if expect.get("safe_stop") and expect.get("allowed_proposal_skills"):
            for skill_id in expect["allowed_proposal_skills"]:
                skill = get_skill(skill_id)
                if skill is None or skill.model_visible is not True:
                    errors.append(f"{case_id}: safe-stop proposal skill is not model-visible: {skill_id}")
        allowed = set(expect.get("allowed_skills") or ())
        for skill_id in allowed:
            skill = get_skill(skill_id)
            if skill_id == "ask_user":
                continue
            if skill is None:
                errors.append(f"{case_id}: unknown allowed skill: {skill_id}")
            elif skill.model_visible is not True and not (
                proposal_mode == "required" and skill_id == "commit_after_sales_action"
            ):
                errors.append(f"{case_id}: internal skill exposed in allowed_skills: {skill_id}")
        required = set(expect.get("required_skills_all") or ())
        required.update(item for group in (expect.get("required_skills_any") or ()) for item in group if isinstance(group, list))
        if not required.issubset(set(observations) | set(expect.get("allowed_skills") or ())):
            errors.append(f"{case_id}: required skill has no fixture or allow-list support")
        if expect.get("business_write_count") == 0 and fixture.get("commit_observation", {}).get("status") == "succeeded":
            errors.append(f"{case_id}: zero-write contract has successful commit observation")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", action="append", type=Path, required=True)
    args = parser.parse_args()
    all_errors: list[str] = []
    for path in args.suite:
        errors = audit_suite(path)
        print(json.dumps({"suite": str(path), "errors": errors, "semanticAuditErrors": len(errors)}, ensure_ascii=False))
        all_errors.extend(errors)
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
