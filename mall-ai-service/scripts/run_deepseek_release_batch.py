"""Run one audited DeepSeek release batch.

This is the only live-model entry point used by the release closeout.  It
keeps a single, redacted ledger for the batch and refuses to start when the
reviewed model profile is not active.  The canary is intentionally one run per
showcase case and aborts the whole batch on a provider/environment block;
the final batch runs the reviewed main and supplemental suites only after the
canary has been handled by the caller.
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

from app.config import settings  # noqa: E402
from app.runtime.live_model_agent_evaluation import (  # noqa: E402
    DEFAULT_SUITE_PATH,
    run_live_model_agent_evaluation,
)
from app.runtime.providers import RUNTIME_PROMPT_VERSION  # noqa: E402
from app.services.llm_service import (  # noqa: E402
    DEEPSEEK_REASONING_EFFORT,
    DEEPSEEK_THINKING_MODE,
)
from app.skills.catalog import SKILL_CATALOG_VERSION  # noqa: E402


REPOSITORY_ROOT = SERVICE_ROOT.parent
HOLDOUT_SUITE_PATH = SERVICE_ROOT / "evals" / "live_model_agent_holdout_cases.v1.json"
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
    main = run_live_model_agent_evaluation(
        suite_path=DEFAULT_SUITE_PATH,
        required_runs=3,
        stop_on_environment_blocked=True,
        max_total_seconds=1800.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    reports: dict[str, object] = {"main": main}
    if main.get("environmentBlocked") or main.get("failed"):
        _finish_ledger(ledger, main)
        return {"status": "environment_blocked" if main.get("environmentBlocked") else "failed", **reports}

    holdout = run_live_model_agent_evaluation(
        suite_path=HOLDOUT_SUITE_PATH,
        required_runs=3,
        stop_on_environment_blocked=True,
        max_total_seconds=1800.0,
        timeout_seconds=25.0,
        max_attempts=1,
    )
    reports["supplemental"] = holdout
    _finish_ledger(ledger, holdout)
    if holdout.get("environmentBlocked") or holdout.get("failed"):
        return {"status": "environment_blocked" if holdout.get("environmentBlocked") else "failed", **reports}

    # Grounding is deliberately left to the dedicated, versioned runner.  It
    # is only entered after both runtime suites have completed successfully,
    # so provider blocks cannot fan out into a second hidden batch.
    reports["grounding"] = {"status": "not_executed", "reason": "dedicated grounding runner required"}
    ledger["status"] = "passed"
    return {"status": "passed", **reports}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("showcase", "final"), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

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

    report = _run_showcase(ledger) if args.phase == "showcase" else _run_final(ledger)
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
    return 2 if ledger.get("status") == "environment_blocked" else 1 if ledger.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
