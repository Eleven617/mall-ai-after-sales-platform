"""Deterministic contracts for the auditable v3 field-acceptance runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "mall-ai-service" / "scripts" / "verify_field_acceptance.py"
SPEC = importlib.util.spec_from_file_location("verify_field_acceptance", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _manifest() -> dict:
    return json.loads((ROOT / "evals" / "v3" / "release-manifest.json").read_text(encoding="utf-8"))


def test_manifest_field_categories_have_expected_case_counts() -> None:
    indexed = runner._index_cases(runner._load_manifest(ROOT / "evals" / "v3" / "release-manifest.json"))
    assert {key: len(value) for key, value in indexed.items()} == runner.EXPECTED_COUNTS


def test_compose_service_state_requires_an_observed_service_line() -> None:
    assert runner._compose_service_state("redis|exited||\nrabbitmq|running|healthy\n", "redis") == "exited"
    assert runner._compose_service_state("rabbitmq|running|healthy\n", "redis") is None


def test_release_gate_rejects_deterministic_fault_contract_as_field_evidence() -> None:
    manifest = _manifest()
    cases = runner._index_cases(manifest)["fault_injection"]
    results = [
        runner._result(
            case,
            "test",
            "test",
            "deterministic_runtime_fault_contract",
            "passed",
            None,
            "abc",
            "manifest",
            "fixture",
            runner._now(),
            ["contract"],
            ["pytest"],
            [],
        )
        for case in cases
    ]
    gate = runner._release_gate(results, ["fault_injection"], {"dockerAvailable": True, "composeConfigValid": True}, True)
    assert gate["passed"] is False
    assert "fault_injection_requires_independent_compose_profile" in gate["reasons"]


def test_release_gate_accepts_only_all_ready_live_cases() -> None:
    manifest = _manifest()
    cases = runner._index_cases(manifest)["browser_e2e"]
    results = [
        runner._result(
            case,
            "test",
            "test",
            "live_browser",
            "passed",
            None,
            "abc",
            "manifest",
            "fixture",
            runner._now(),
            ["page_ready"],
            ["Chrome"],
            [],
        )
        for case in cases
    ]
    gate = runner._release_gate(results, ["browser_e2e"], {"dockerAvailable": True, "composeConfigValid": True}, True)
    assert gate == {"passed": True, "reasons": []}
