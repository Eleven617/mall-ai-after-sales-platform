"""Run the registered v3.0 live-synthetic cases with the real P0 model.

The release manifest intentionally keeps live cases free of prompts and model
outputs.  This runner supplies a reviewed, versioned mapping to the existing
task-orchestration semantic fixtures, then invokes ``detect_intent`` exactly
once per independent run.  It never calls Java, Redis, RAG, customer tools or
business-write adapters.  Only safe case identifiers, contract status and
timings are printed.

The six manifest scenarios are mapped to six canonical task-aware fixtures;
the 36 registered cases are six reviewed scenario families with distinct
manifest variation/case IDs.  This makes the scope explicit instead of
pretending that generic manifest metadata is itself a model evaluation.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.runtime.release_manifest import (
    load_release_manifest,
    validate_release_manifest,
)
from app.services.intent_service import IntentServiceError, detect_intent


TASK_SUITE_PATH = SERVICE_ROOT / "evals" / "task_orchestration_cases.v1.json"
REPOSITORY_ROOT = SERVICE_ROOT.parent
DEFAULT_LIVE_MANIFEST_PATH = REPOSITORY_ROOT / "evals" / "v3" / "release-manifest.json"

# These mappings are deliberately data-like and reviewed with the task-aware
# suite.  They are not a keyword router: the actual semantic decision is still
# made by the model and checked against the TurnPlan contract below.
SCENARIO_TEMPLATE_IDS: dict[str, str] = {
    "dynamic_skill_discovery": "live-missing-identifier-is-order-diagnosis",
    "counterfactual_replan": "live-third-long-task-conflict",
    "candidate_comparison": "live-ambiguous-two-task-message-clarifies",
    "safe_abstention": "live-policy-question-does-not-consume-proposal",
    "confirmation_gate": "live-natural-confirmation-for-proposal",
    "memory_reuse": "live-resume-paused-diagnosis",
}


@dataclass(frozen=True)
class LiveRunResult:
    case_id: str
    run: int
    status: str
    elapsed_ms: int
    template_id: str
    violations: tuple[str, ...] = ()


def load_template_cases(path: Path = TASK_SUITE_PATH) -> dict[str, dict[str, Any]]:
    """Load only the safe synthetic P0 fixtures used by the mapping."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("liveModelCases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        raise ValueError("task orchestration live fixture suite is malformed")
    result: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("caseId"), str):
            raise ValueError("task orchestration live fixture has an invalid case")
        result[case["caseId"]] = case
    for template_id in SCENARIO_TEMPLATE_IDS.values():
        template = result.get(template_id)
        if template is None:
            raise ValueError(f"missing mapped task orchestration fixture: {template_id}")
        if not isinstance(template.get("syntheticInput"), str) or not template["syntheticInput"].strip():
            raise ValueError(f"mapped fixture has no synthetic input: {template_id}")
        if template.get("safeContext") is not None and not isinstance(template["safeContext"], dict):
            raise ValueError(f"mapped fixture has unsafe context: {template_id}")
        if not isinstance(template.get("expectedPlan"), dict):
            raise ValueError(f"mapped fixture has no expected plan: {template_id}")
    return result


def mapped_template_for_case(
    manifest_case: dict[str, Any],
    templates: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    fixture = manifest_case.get("fixture")
    scenario = fixture.get("scenario") if isinstance(fixture, dict) else None
    template_id = SCENARIO_TEMPLATE_IDS.get(scenario)
    if template_id is None or template_id not in templates:
        raise ValueError(f"live case scenario is not mapped: {scenario}")
    return template_id, templates[template_id]


def run_manifest_live_synthetic(
    *,
    manifest_path: Path = DEFAULT_LIVE_MANIFEST_PATH,
    max_total_seconds: float = 900.0,
) -> tuple[list[LiveRunResult], dict[str, Any]]:
    """Execute every registered live case three times with the real P0 model."""

    manifest = load_release_manifest(manifest_path)
    report = validate_release_manifest(manifest)
    templates = load_template_cases()
    started = time.monotonic()
    results: list[LiveRunResult] = []

    for raw_case in manifest["liveCases"]:
        case_id = raw_case["caseId"]
        template_id, template = mapped_template_for_case(raw_case, templates)
        required_runs = raw_case.get("requiredRuns")
        if required_runs != 3:
            raise ValueError(f"{case_id} does not require exactly three independent runs")
        for run_number in range(1, required_runs + 1):
            if time.monotonic() - started > max_total_seconds:
                results.append(
                    LiveRunResult(
                        case_id=case_id,
                        run=run_number,
                        status="ENVIRONMENT_BLOCKED",
                        elapsed_ms=0,
                        template_id=template_id,
                        violations=("evaluation_budget_exhausted",),
                    )
                )
                continue
            run_started = time.monotonic()
            try:
                context = template.get("safeContext")
                # Keep the model-facing context limited to the reviewed task
                # snapshot.  Manifest case IDs/variations are runner metadata,
                # not conversation facts; injecting them into the prompt can
                # perturb semantic routing while adding no evaluation value.
                if context is None:
                    context_payload: dict[str, Any] = {}
                elif isinstance(context, dict):
                    context_payload = dict(context)
                else:
                    raise ValueError("mapped fixture context is not an object")
                context_json = (
                    json.dumps(context_payload, ensure_ascii=False, separators=(",", ":"))
                    if context_payload
                    else ""
                )
                actual = detect_intent(template["syntheticInput"], context_json)
                violations = tuple(_plan_violations(actual, template["expectedPlan"]))
                status = "PASSED" if not violations else "FAILED"
            except IntentServiceError:
                # Model/network/structured-output failure remains visible and
                # never turns into a pass or a local keyword fallback.
                status = "ENVIRONMENT_BLOCKED"
                violations = ("p0_unavailable_or_contract_error",)
            except (KeyError, TypeError, ValueError):
                status = "FAILED"
                violations = ("invalid_live_fixture_or_plan",)
            results.append(
                LiveRunResult(
                    case_id=case_id,
                    run=run_number,
                    status=status,
                    elapsed_ms=max(0, round((time.monotonic() - run_started) * 1000)),
                    template_id=template_id,
                    violations=violations,
                )
            )

    summary = {
        "suiteVersion": report.suite_version,
        "manifestLiveCases": report.live_case_total,
        "requiredRunsPerCase": 3,
        "executedRuns": len(results),
        "passed": sum(item.status == "PASSED" for item in results),
        "failed": sum(item.status == "FAILED" for item in results),
        "environmentBlocked": sum(item.status == "ENVIRONMENT_BLOCKED" for item in results),
        "totalElapsedMs": max(0, round((time.monotonic() - started) * 1000)),
        "p95ElapsedMs": _p95([item.elapsed_ms for item in results]),
        "templateFamilies": len(SCENARIO_TEMPLATE_IDS),
    }
    return results, summary


def _plan_violations(actual: Any, expected: dict[str, Any]) -> list[str]:
    values = {
        "businessIntent": actual.business_intent,
        "taskRelation": actual.task_relation,
        "route": actual.route,
        "taskKind": actual.task_kind,
        "confirmationIntent": actual.confirmation_intent,
    }
    violations: list[str] = []
    for key, expected_value in expected.items():
        if key.endswith("AnyOf"):
            actual_key = key[: -len("AnyOf")]
            allowed = expected_value if isinstance(expected_value, list) else []
            if values.get(actual_key) not in allowed:
                violations.append(f"{actual_key}_mismatch")
        elif values.get(key) != expected_value:
            violations.append(f"{key}_mismatch")
    return violations


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, (len(ordered) * 95 + 99) // 100 - 1)
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_LIVE_MANIFEST_PATH)
    parser.add_argument("--max-total-seconds", type=float, default=900.0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        results, summary = run_manifest_live_synthetic(
            manifest_path=args.manifest,
            max_total_seconds=args.max_total_seconds,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"v3_live_synthetic FAILED: {type(exc).__name__}")
        return 1

    payload = {
        **summary,
        "cases": [asdict(item) for item in results],
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "v3_live_synthetic "
            f"{'PASSED' if summary['failed'] == 0 and summary['environmentBlocked'] == 0 else 'FAILED'} "
            f"runs={summary['passed']}/{summary['executedRuns']} "
            f"failed={summary['failed']} blocked={summary['environmentBlocked']} "
            f"p95_ms={summary['p95ElapsedMs']}"
        )
        for item in results:
            print(
                "v3_live_case "
                f"case_id={item.case_id} run={item.run} status={item.status} "
                f"elapsed_ms={item.elapsed_ms} violations={','.join(item.violations) or 'none'}"
            )
    return 0 if summary["failed"] == 0 and summary["environmentBlocked"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
