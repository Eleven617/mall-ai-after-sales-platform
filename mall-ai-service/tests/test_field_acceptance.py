"""Deterministic contracts for the auditable v3 field-acceptance runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


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
    gate = runner._release_gate(
        results,
        ["fault_injection"],
        {"dockerAvailable": True, "composeConfigValid": True},
        True,
        "abc",
        {"runtimeCommit": "abc", "imageRevision": "abc", "providerMode": "deterministic"},
    )
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
    gate = runner._release_gate(
        results,
        ["browser_e2e"],
        {"dockerAvailable": True, "composeConfigValid": True},
        True,
        "abc",
        {"runtimeCommit": "abc", "imageRevision": "abc", "providerMode": "deterministic"},
    )
    assert gate == {"passed": True, "reasons": []}


def test_release_gate_rejects_runtime_or_image_not_bound_to_tested_commit() -> None:
    gate = runner._release_gate(
        [],
        [],
        {"dockerAvailable": True, "composeConfigValid": True},
        True,
        "current-commit",
        {
            "runtimeCommit": "different-commit",
            "imageRevision": "different-commit",
            "providerMode": "deterministic",
        },
    )

    assert gate["passed"] is False
    assert gate["reasons"] == ["runtime_identity_mismatch"]


def test_durable_recovery_child_receives_an_absolute_report_path(tmp_path: Path, monkeypatch) -> None:
    """A relative parent report directory must not split parent/child evidence."""

    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    report_dir = tmp_path / "relative-parent-report"
    report_dir.mkdir()
    case = {"caseId": "V3-RECOVERY-TEST", "category": "durable_async_recovery"}
    observed: dict[str, Path] = {}

    def fake_run(command, **_kwargs):
        report_path = Path(command[command.index("--report") + 1])
        observed["report"] = report_path
        observed["fixture"] = Path(command[command.index("--fixture") + 1])
        report_path.write_text(
            json.dumps({"cases": [{"caseId": case["caseId"], "status": "passed", "assertions": ["recovered"]}]}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="safe summary", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    results = runner._run_recovery_cases(
        [case],
        "commit",
        "manifest",
        "fixture-hash",
        fixture,
        "process-only-password",
        report_dir,
    )

    assert observed["report"].is_absolute()
    assert observed["fixture"].is_absolute()
    assert results[0].executionStatus == "passed"
    assert results[0].assertions == ["recovered"]


def test_browser_runner_binds_the_disposable_fixture_customer(monkeypatch, tmp_path: Path) -> None:
    """Rotated field fixtures must not fall back to a historic demo login."""

    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"account_a": {"username": "rotated-synthetic-customer"}}), encoding="utf-8")
    observed: dict[str, str] = {}

    class FakeBrowser:
        def __init__(self, *, customer_username: str | None = None, **_kwargs) -> None:
            observed["username"] = customer_username or ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(sys.modules, "field_browser_support", SimpleNamespace(BrowserSession=FakeBrowser))
    results = runner._run_browser_cases(
        [],
        "commit",
        "manifest",
        "fixture-hash",
        fixture,
        "process-only-password",
        tmp_path,
    )

    assert results == []
    assert observed["username"] == "rotated-synthetic-customer"


def test_customer_page_does_not_render_the_authenticated_username() -> None:
    """Browser evidence must not expose a synthetic or real account identifier."""

    source = (ROOT / "mall-ai-web" / "src" / "App.vue").read_text(encoding="utf-8")
    assert 'currentMember.value ? "已登录" : "未登录"' in source
    assert "已登录：${currentMember.value.username}" not in source
    assert "{{ currentMember.username }}" not in source


def test_public_release_validator_accepts_a_dynamic_fastapi_total() -> None:
    """A green report growth must not require a new hard-coded gate value."""

    validator_path = ROOT / "scripts" / "validate_public_release.py"
    spec = importlib.util.spec_from_file_location("public_release_validator_test", validator_path)
    assert spec and spec.loader
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)

    assert validator.fastapi_facts_match(
        {"passed": 437, "failed": 0},
        {"passed": 437, "failures": 0, "errors": 0},
    )
    assert not validator.fastapi_facts_match(
        {"passed": 436, "failed": 0},
        {"passed": 437, "failures": 0, "errors": 0},
    )
