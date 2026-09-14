"""Run one audited DeepSeek release batch.

The ``candidate`` phase is the only new live-model entry point for the v3.0.1
closeout. It keeps the real local showcase and synthetic quality suites in one
redacted ledger and refuses to start when the reviewed model profile is not
active. Historical ``showcase``/``final`` phases remain available only to read
old evidence and must not rewrite the old release lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
if str(SERVICE_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from app.config import settings  # noqa: E402
from app.runtime.live_model_agent_evaluation import (  # noqa: E402
    DEFAULT_SUITE_PATH,
    run_live_model_agent_evaluation,
)
from app.runtime.providers import RUNTIME_PROMPT_VERSION  # noqa: E402
from run_real_local_showcase import run_real_local_showcase  # noqa: E402
from app.services.rag2_evaluation import (  # noqa: E402
    evaluate_grounded_answer_suite,
    load_rag2_golden_suite,
)
from app.services.llm_service import (  # noqa: E402
    DEEPSEEK_REASONING_EFFORT,
    DEEPSEEK_THINKING_MODE,
)
from app.skills.catalog import SKILL_CATALOG_VERSION  # noqa: E402


REPOSITORY_ROOT = SERVICE_ROOT.parent
RELEASE_LOCK_PATH = REPOSITORY_ROOT / "docs" / "evidence" / "deepseek-release-lock.json"
DEFAULT_CANDIDATE_LOCK_PATH = REPOSITORY_ROOT / "docs" / "evidence" / "deepseek-release-lock-v3.0.1.json"
HOLDOUT_SUITE_PATH = SERVICE_ROOT / "evals" / "live_model_agent_holdout_cases.v1.json"
GROUNDING_SUITE_PATH = SERVICE_ROOT / "evals" / "rag2_golden_cases.v1.json"
SHOWCASE_CASES = {
    "main_open_task_closed_loop": "agent-open-020",
    "clarify_pause_resume": "agent-open-001",
    "fact_change_replan": "agent-open-021",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _base_ledger(*, batch_id: str, release_id: str, phase: str, command: str) -> dict[str, object]:
    return {
        "batchId": batch_id,
        "releaseId": release_id,
        "phase": phase,
        "command": command,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": "DeepSeek",
        "model": settings.deepseek_model,
        "thinkingMode": DEEPSEEK_THINKING_MODE,
        "reasoningEffort": DEEPSEEK_REASONING_EFFORT,
        "promptVersion": RUNTIME_PROMPT_VERSION,
        "skillCatalogVersion": SKILL_CATALOG_VERSION,
        "requests": 0,
        "successfulRequests": 0,
        "failedRequests": 0,
        "environmentBlocked": 0,
        "protocolCorrections": 0,
        "networkRetries": 0,
        "promptTokens": 0,
        "reasoningTokens": None,
        "completionTokens": 0,
        "totalTokens": 0,
        "toolCalls": 0,
        "exitCode": None,
    }


def _finish_ledger(ledger: dict[str, object], report: dict[str, object]) -> None:
    llm = report.get("llm") if isinstance(report, dict) else None
    if isinstance(llm, dict):
        ledger["requests"] = int(llm.get("total_calls", 0) or 0)
        ledger["successfulRequests"] = int(llm.get("succeeded_calls", 0) or 0)
        ledger["failedRequests"] = int(llm.get("failed_calls", 0) or 0)
        ledger["promptTokens"] = int(llm.get("prompt_tokens", 0) or 0)
        ledger["completionTokens"] = int(llm.get("completion_tokens", 0) or 0)
        ledger["totalTokens"] = int(llm.get("total_tokens", 0) or 0)
        ledger["networkRetries"] = int(llm.get("network_retries", 0) or 0)
    ledger["toolCalls"] = int(report.get("toolCalls", 0) or 0)
    ledger["environmentBlocked"] = int(report.get("environmentBlocked", 0) or 0)
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ledger["status"] = (
        "environment_blocked"
        if ledger["environmentBlocked"]
        else "failed"
        if int(report.get("failed", 0) or 0)
        else "passed"
    )


def _merge_ledger_metrics(ledger: dict[str, object], reports: list[dict[str, object]]) -> None:
    """Aggregate only numeric provider metadata from one unified batch."""

    totals = {
        "requests": 0,
        "successfulRequests": 0,
        "failedRequests": 0,
        "environmentBlocked": 0,
        "promptTokens": 0,
        "completionTokens": 0,
        "totalTokens": 0,
        "toolCalls": 0,
        "networkRetries": 0,
    }
    for report in reports:
        metric = report.get("llm") or report.get("provider_metrics")
        if isinstance(metric, dict):
            totals["requests"] += int(metric.get("total_calls", 0) or 0)
            totals["successfulRequests"] += int(metric.get("succeeded_calls", 0) or 0)
            totals["failedRequests"] += int(metric.get("failed_calls", 0) or 0)
            totals["promptTokens"] += int(metric.get("prompt_tokens", 0) or 0)
            totals["completionTokens"] += int(metric.get("completion_tokens", 0) or 0)
            totals["totalTokens"] += int(metric.get("total_tokens", 0) or 0)
            totals["networkRetries"] += int(metric.get("network_retries", 0) or 0)
        totals["toolCalls"] += int(report.get("toolCalls", 0) or 0)
        totals["environmentBlocked"] += int(
            report.get("environmentBlocked", report.get("environment_blocked_cases", 0)) or 0
        )
    ledger.update(totals)
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run_showcase(ledger: dict[str, object]) -> dict[str, object]:
    report = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        case_ids=set(SHOWCASE_CASES.values()),
        required_runs=1,
        stop_on_environment_blocked=True,
        max_total_seconds=900.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    _finish_ledger(ledger, report)
    report["showcaseScenarios"] = {
        label: {
            "caseId": case_id,
            "status": next(
                (
                    item["status"]
                    for item in report.get("cases", [])
                    if item.get("caseId") == case_id
                ),
                "not_executed",
            ),
        }
        for label, case_id in SHOWCASE_CASES.items()
    }
    return report


def _run_final(ledger: dict[str, object]) -> dict[str, object]:
    showcase = _run_showcase(ledger)
    reports: dict[str, object] = {"showcase": showcase}
    if showcase.get("environmentBlocked") or showcase.get("failed"):
        _merge_ledger_metrics(ledger, [showcase])
        ledger["status"] = "environment_blocked" if showcase.get("environmentBlocked") else "failed"
        return {
            "status": "environment_blocked" if showcase.get("environmentBlocked") else "failed",
            **reports,
        }

    main = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        required_runs=3,
        stop_on_environment_blocked=True,
        max_total_seconds=1800.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    reports["main"] = main
    if main.get("environmentBlocked"):
        _merge_ledger_metrics(ledger, [value for value in reports.values() if isinstance(value, dict)])
        ledger["status"] = "environment_blocked"
        return {"status": "environment_blocked", **reports}

    holdout = run_live_model_agent_evaluation(
        suite_path=HOLDOUT_SUITE_PATH,
        required_runs=3,
        stop_on_environment_blocked=True,
        max_total_seconds=1800.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    reports["supplemental"] = holdout
    if holdout.get("environmentBlocked"):
        _merge_ledger_metrics(ledger, [value for value in reports.values() if isinstance(value, dict)])
        ledger["status"] = "environment_blocked"
        return {"status": "environment_blocked", **reports}

    grounding_suite = load_rag2_golden_suite(GROUNDING_SUITE_PATH)
    grounding = evaluate_grounded_answer_suite(
        grounding_suite,
        mode="dense",
        timeout_seconds=20.0,
        max_attempts=1,
        stop_on_environment_blocked=True,
    )
    grounding["model"] = {
        "provider": "DeepSeek",
        "model": settings.deepseek_model,
        "thinkingMode": DEEPSEEK_THINKING_MODE,
        "reasoningEffort": DEEPSEEK_REASONING_EFFORT,
        "promptVersion": "rag2_grounding_v1",
        "skillCatalogVersion": SKILL_CATALOG_VERSION,
        "runtimeCommit": ledger["runtimeCommit"],
        "executionBoundary": "synthetic_policy_corpus",
    }
    reports["grounding"] = grounding
    report_list = [value for value in reports.values() if isinstance(value, dict)]
    _merge_ledger_metrics(ledger, report_list)
    statuses = {str(value.get("status")) for value in report_list}
    overall = "environment_blocked" if "environment_blocked" in statuses else "failed" if "failed" in statuses or "quality_failed" in statuses else "passed"
    ledger["status"] = overall
    return {"status": overall, **reports}


def _budget_exceeded(ledger: dict[str, object]) -> bool:
    return int(ledger.get("requests", 0) or 0) > 450 or int(ledger.get("totalTokens", 0) or 0) > 1_100_000


def _run_candidate(ledger: dict[str, object], report_dir: Path) -> dict[str, object]:
    """Run the v3.0.1 batch in one process and one ordered ledger."""

    showcase = run_real_local_showcase(
        report_dir=report_dir / "showcase",
        batch_id=str(ledger["batchId"]),
    )
    reports: dict[str, object] = {"realLocalShowcase": showcase}
    if showcase.get("status") != "passed":
        ledger["status"] = "environment_blocked" if showcase.get("status") == "environment_blocked" else "failed"
        ledger["environmentBlocked"] = 1 if showcase.get("status") == "environment_blocked" else 0
        ledger["failedRequests"] = int(ledger.get("failedRequests", 0) or 0) + (0 if showcase.get("status") == "environment_blocked" else 1)
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"status": ledger["status"], **reports}

    main = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        required_runs=3,
        stop_on_environment_blocked=True,
        max_total_seconds=1800.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    reports["main"] = main
    _merge_ledger_metrics(ledger, [main])
    if main.get("environmentBlocked") or _budget_exceeded(ledger):
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = max(1, int(ledger.get("environmentBlocked", 0) or 0))
        return {"status": "environment_blocked", **reports}

    supplemental = run_live_model_agent_evaluation(
        suite_path=HOLDOUT_SUITE_PATH,
        required_runs=3,
        stop_on_environment_blocked=True,
        max_total_seconds=1800.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    reports["supplemental"] = supplemental
    _merge_ledger_metrics(ledger, [main, supplemental])
    if supplemental.get("environmentBlocked") or _budget_exceeded(ledger):
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = max(1, int(ledger.get("environmentBlocked", 0) or 0))
        return {"status": "environment_blocked", **reports}

    grounding_suite = load_rag2_golden_suite(GROUNDING_SUITE_PATH)
    grounding = evaluate_grounded_answer_suite(
        grounding_suite,
        mode="dense",
        timeout_seconds=20.0,
        max_attempts=1,
        stop_on_environment_blocked=True,
    )
    grounding["model"] = {
        "provider": "DeepSeek",
        "model": settings.deepseek_model,
        "thinkingMode": DEEPSEEK_THINKING_MODE,
        "reasoningEffort": DEEPSEEK_REASONING_EFFORT,
        "promptVersion": "rag2_grounding_v1",
        "skillCatalogVersion": SKILL_CATALOG_VERSION,
        "runtimeCommit": ledger["runtimeCommit"],
        "executionBoundary": "synthetic_policy_corpus",
    }
    reports["grounding"] = grounding
    _merge_ledger_metrics(ledger, [main, supplemental, grounding])
    statuses = [str(main.get("status")), str(supplemental.get("status")), str(grounding.get("status"))]
    if "environment_blocked" in statuses or _budget_exceeded(ledger):
        overall = "environment_blocked"
    elif any(status in {"failed", "quality_failed"} for status in statuses):
        overall = "failed"
    else:
        overall = "passed"
    ledger["status"] = overall
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {"status": overall, **reports}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("showcase", "final", "candidate"), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=RELEASE_LOCK_PATH)
    args = parser.parse_args()

    lock_path = args.lock if args.lock.is_absolute() else REPOSITORY_ROOT / args.lock

    # Once a release has consumed its two paid batches, the release id is
    # permanently closed.  This guard is intentionally checked before any
    # provider configuration or model call so a later accidental rerun cannot
    # spend credits or create a third batch.
    if lock_path.is_file():
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            lock = {}
        if isinstance(lock, dict) and lock.get("releaseId") == args.release_id:
            print(
                json.dumps(
                    {"status": "release_locked", "releaseId": args.release_id},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 4

    if settings.deepseek_model != "deepseek-flash":
        print("deepseek release batch refused: reviewed model is not deepseek-flash", file=sys.stderr)
        return 3

    batch_id = f"{args.phase}-{uuid.uuid4().hex[:12]}"
    ledger = _base_ledger(
        batch_id=batch_id,
        release_id=args.release_id,
        phase=args.phase,
        command=" ".join(sys.argv),
    )
    ledger["runtimeCommit"] = args.runtime_commit
    ledger["suiteHashes"] = {
        "main": _sha256(DEFAULT_SUITE_PATH),
        "supplemental": _sha256(HOLDOUT_SUITE_PATH),
        "grounding": _sha256(GROUNDING_SUITE_PATH),
    }
    if not settings.deepseek_api_key:
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = 1
        ledger["failureCategory"] = "missing_configuration"
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = {"ledger": ledger, "report": {"status": "environment_blocked"}}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "environment_blocked", "batchId": batch_id}, ensure_ascii=False))
        return 2

    report = (
        _run_showcase(ledger)
        if args.phase == "showcase"
        else _run_final(ledger)
        if args.phase == "final"
        else _run_candidate(ledger, args.report.parent / f"{batch_id}-artifacts")
    )
    ledger["testRunComplete"] = bool(
        args.phase == "candidate"
        and isinstance(report, dict)
        and all(key in report for key in ("realLocalShowcase", "main", "supplemental", "grounding"))
    )
    ledger["releaseQualified"] = bool(
        ledger["testRunComplete"]
        and ledger.get("status") == "passed"
        and isinstance(report.get("realLocalShowcase"), dict)
        and report["realLocalShowcase"].get("status") == "passed"
    )
    payload = {"ledger": ledger, "report": report}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": ledger.get("status"),
                "batchId": batch_id,
                "requests": ledger.get("requests"),
                "environmentBlocked": ledger.get("environmentBlocked"),
            },
            ensure_ascii=False,
        )
    )
    if args.phase == "candidate":
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps(
                {
                    "schemaVersion": "deepseek-release-lock.v1",
                    "releaseId": args.release_id,
                    "batchIds": [batch_id],
                    "runtimeCommit": args.runtime_commit,
                    "status": ledger.get("status"),
                    "testRunComplete": ledger.get("testRunComplete"),
                    "releaseQualified": ledger.get("releaseQualified"),
                    "requests": ledger.get("requests"),
                    "totalTokens": ledger.get("totalTokens"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 2 if ledger.get("status") == "environment_blocked" else 1 if ledger.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
