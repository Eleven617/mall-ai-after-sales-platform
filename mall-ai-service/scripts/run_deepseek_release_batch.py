"""Run one audited DeepSeek release batch.

The historical phases remain for immutable evidence. ``portfolio_a`` and
``portfolio_b`` are the controlled v3.0.3 entry points: A consumes exactly one
batch for the three end-to-end live showcase chains; B is allowed exactly once
after A passes and consumes the final evaluation batch. If A has already
failed and a Runtime fix has passed offline acceptance, ``portfolio_final``
creates one new Release ID and consumes its one permitted final batch. Every
path uses an immutable lock and a metadata-only shared ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx


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
from app.services.release_ledger import read_release_events, summarize_release_events  # noqa: E402


REPOSITORY_ROOT = SERVICE_ROOT.parent
RELEASE_LOCK_PATH = REPOSITORY_ROOT / "docs" / "evidence" / "deepseek-release-lock.json"
DEFAULT_CANDIDATE_LOCK_PATH = REPOSITORY_ROOT / "docs" / "evidence" / "deepseek-release-lock-v3.0.1.json"
HOLDOUT_SUITE_PATH = SERVICE_ROOT / "evals" / "live_model_agent_holdout_cases.v2.json"
GROUNDING_SUITE_PATH = SERVICE_ROOT / "evals" / "rag2_golden_cases.v1.json"
SHOWCASE_CASES = {
    "main_open_task_closed_loop": "agent-open-020",
    "clarify_pause_resume": "agent-open-001",
    "fact_change_replan": "agent-open-021",
}


def _atomic_create_json(path: Path, payload: dict[str, object]) -> None:
    """Create a lock without allowing an existing release to be overwritten."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _atomic_replace_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _runtime_identity(runtime_commit: str) -> tuple[bool, str]:
    """Check the already-running container without making a provider call."""

    expected = {
        "runtimeCommit": runtime_commit,
        "imageRevision": runtime_commit,
        "providerMode": "live",
        "model": "deepseek-flash",
        "thinkingMode": DEEPSEEK_THINKING_MODE,
        "reasoningEffort": DEEPSEEK_REASONING_EFFORT,
        "promptVersion": RUNTIME_PROMPT_VERSION,
        "skillCatalogVersion": SKILL_CATALOG_VERSION,
    }
    try:
        response = httpx.get(
            os.getenv("MALL_RUNTIME_VERSION_URL", "http://127.0.0.1:8000/health/version"),
            timeout=5,
            trust_env=False,
        )
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return False, "runtime_identity_unavailable"
    if response.status_code != 200 or not isinstance(payload, dict):
        return False, "runtime_identity_unavailable"
    if any(payload.get(key) != value for key, value in expected.items()):
        return False, "runtime_identity_mismatch"
    return True, "ok"


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
        "providerRequests": 0,
        "successfulRequests": 0,
        "failedRequests": 0,
        "providerFailures": 0,
        "scenarioFailures": 0,
        "testFailures": 0,
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
    """Merge non-provider report counters without overriding the event ledger.

    Provider requests and token usage are authoritative only in the shared
    JSONL event ledger.  A suite report may legitimately contain zero model
    calls (for example an offline replay) and must never erase live events.
    """
    tool_calls = 0
    environment_blocked = 0
    for report in reports:
        tool_calls += int(report.get("toolCalls", 0) or 0)
        environment_blocked += int(
            report.get("environmentBlocked", report.get("environment_blocked_cases", 0)) or 0
        )
    ledger["toolCalls"] = tool_calls
    ledger["environmentBlocked"] = environment_blocked
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sync_process_ledger(ledger: dict[str, object]) -> bool:
    """Merge container and host JSONL events without mixing failure classes."""

    path = os.getenv("MALL_RELEASE_LEDGER_PATH")
    if not path:
        ledger["ledgerReconciled"] = False
        ledger["failureCategory"] = "ledger_mismatch"
        return False
    summary = summarize_release_events(read_release_events(path, batch_id=str(ledger["batchId"])))
    ledger["providerRequests"] = summary["providerRequests"]
    ledger["requests"] = summary["providerRequests"]
    ledger["successfulRequests"] = summary["providerSuccesses"]
    ledger["failedRequests"] = summary["providerFailures"]
    ledger["providerFailures"] = summary["providerFailures"]
    ledger["scenarioFailures"] = summary["scenarioFailures"]
    ledger["testFailures"] = summary["testFailures"]
    ledger["promptTokens"] = summary["promptTokens"]
    ledger["completionTokens"] = summary["completionTokens"]
    ledger["totalTokens"] = summary["totalTokens"]
    ledger["networkRetries"] = summary["networkRetries"]
    ledger["protocolCorrections"] = summary["protocolCorrections"]
    ledger["ledgerReconciled"] = True
    return True


def _reconciled_report_metrics(ledger: dict[str, object]) -> dict[str, object]:
    """Return the only provider counters allowed into a public batch report."""

    return {
        "providerRequests": int(ledger.get("providerRequests", 0) or 0),
        "successfulRequests": int(ledger.get("successfulRequests", 0) or 0),
        "failedRequests": int(ledger.get("failedRequests", 0) or 0),
        "promptTokens": int(ledger.get("promptTokens", 0) or 0),
        "completionTokens": int(ledger.get("completionTokens", 0) or 0),
        "totalTokens": int(ledger.get("totalTokens", 0) or 0),
        "ledgerReconciled": ledger.get("ledgerReconciled") is True,
    }


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


def _budget_failure_category(ledger: dict[str, object]) -> str | None:
    if int(ledger.get("requests", 0) or 0) > 450:
        return "budget_exhausted"
    if int(ledger.get("totalTokens", 0) or 0) > 1_100_000:
        return "budget_exhausted"
    return None


def _run_candidate(ledger: dict[str, object], report_dir: Path) -> dict[str, object]:
    """Run the v3.0.1 batch in one process and one ordered ledger."""

    showcase = run_real_local_showcase(
        report_dir=report_dir / "showcase",
        batch_id=str(ledger["batchId"]),
    )
    reports: dict[str, object] = {"realLocalShowcase": showcase}
    if showcase.get("status") != "passed":
        reconciled = _sync_process_ledger(ledger)
        ledger["status"] = (
            "failed"
            if not reconciled
            else "environment_blocked"
            if showcase.get("status") == "environment_blocked"
            else "failed"
        )
        ledger["environmentBlocked"] = 1 if showcase.get("status") == "environment_blocked" else 0
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"status": ledger["status"], **reports}

    # A live showcase must have produced provider events in the shared ledger.
    # This catches a deterministic/replay container accidentally serving the
    # public endpoints before any paid evaluation is started.
    if not _sync_process_ledger(ledger):
        ledger["status"] = "failed"
        ledger["failureCategory"] = "ledger_mismatch"
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"status": "failed", "failureCategory": "ledger_mismatch", **reports}
    if int(ledger.get("providerRequests", 0) or 0) <= 0:
        ledger["status"] = "failed"
        ledger["failureCategory"] = "ledger_mismatch"
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"status": "failed", "failureCategory": "ledger_mismatch", **reports}
    if int(ledger.get("providerFailures", 0) or 0) > 0:
        ledger["status"] = "failed"
        ledger["failureCategory"] = "provider_failure"
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"status": "failed", "failureCategory": "provider_failure", **reports}

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
    if main.get("environmentBlocked"):
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = max(1, int(ledger.get("environmentBlocked", 0) or 0))
        return {"status": "environment_blocked", **reports}
    if _budget_exceeded(ledger):
        ledger["status"] = "budget_exhausted"
        ledger["failureCategory"] = _budget_failure_category(ledger)
        return {"status": "budget_exhausted", **reports}

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
    if supplemental.get("environmentBlocked"):
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = max(1, int(ledger.get("environmentBlocked", 0) or 0))
        return {"status": "environment_blocked", **reports}
    if _budget_exceeded(ledger):
        ledger["status"] = "budget_exhausted"
        ledger["failureCategory"] = _budget_failure_category(ledger)
        return {"status": "budget_exhausted", **reports}

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
    if "environment_blocked" in statuses:
        overall = "environment_blocked"
    elif _budget_exceeded(ledger):
        overall = "budget_exhausted"
        ledger["failureCategory"] = _budget_failure_category(ledger)
    elif any(status in {"failed", "quality_failed"} for status in statuses):
        overall = "failed"
    else:
        overall = "passed"
    ledger["status"] = overall
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not _sync_process_ledger(ledger):
        ledger["status"] = "failed"
        ledger["failureCategory"] = "ledger_mismatch"
    return {"status": overall, **reports}


def _run_portfolio_showcase(ledger: dict[str, object], report_dir: Path) -> dict[str, object]:
    """Run and reconcile the three real public chains for one paid batch."""

    showcase = run_real_local_showcase(
        report_dir=report_dir / "showcase",
        batch_id=str(ledger["batchId"]),
    )
    reports: dict[str, object] = {"realLocalShowcase": showcase}
    if showcase.get("status") != "passed":
        _sync_process_ledger(ledger)
        ledger["status"] = "environment_blocked" if showcase.get("status") == "environment_blocked" else "failed"
        ledger["environmentBlocked"] = 1 if showcase.get("status") == "environment_blocked" else 0
        ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"status": ledger["status"], **reports}

    if not _sync_process_ledger(ledger):
        ledger["status"] = "failed"
        ledger["failureCategory"] = "ledger_mismatch"
    elif int(ledger.get("providerRequests", 0) or 0) <= 0:
        ledger["status"] = "failed"
        ledger["failureCategory"] = "ledger_mismatch"
    elif int(ledger.get("providerFailures", 0) or 0) > 0:
        ledger["status"] = "failed"
        ledger["failureCategory"] = "provider_failure"
    else:
        ledger["status"] = "passed"
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {"status": ledger["status"], **reports}


def _run_portfolio_b(ledger: dict[str, object], report_dir: Path) -> dict[str, object]:
    """Run the final batch once after a successful live core-chain canary."""

    first = _run_portfolio_showcase(ledger, report_dir)
    reports: dict[str, object] = dict(first)
    reports.pop("status", None)
    if first.get("status") != "passed":
        return {"status": first.get("status", "failed"), **reports}

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
    if main.get("environmentBlocked"):
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = max(1, int(ledger.get("environmentBlocked", 0) or 0))
        return {"status": "environment_blocked", **reports}
    if _budget_exceeded(ledger):
        ledger["status"] = "budget_exhausted"
        ledger["failureCategory"] = _budget_failure_category(ledger)
        return {"status": "budget_exhausted", **reports}

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
    if supplemental.get("environmentBlocked"):
        ledger["status"] = "environment_blocked"
        ledger["environmentBlocked"] = max(1, int(ledger.get("environmentBlocked", 0) or 0))
        return {"status": "environment_blocked", **reports}
    if _budget_exceeded(ledger):
        ledger["status"] = "budget_exhausted"
        ledger["failureCategory"] = _budget_failure_category(ledger)
        return {"status": "budget_exhausted", **reports}

    grounding = evaluate_grounded_answer_suite(
        load_rag2_golden_suite(GROUNDING_SUITE_PATH),
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
    if "environment_blocked" in statuses:
        overall = "environment_blocked"
    elif _budget_exceeded(ledger):
        overall = "budget_exhausted"
        ledger["failureCategory"] = _budget_failure_category(ledger)
    elif any(status in {"failed", "quality_failed"} for status in statuses):
        overall = "failed"
    else:
        overall = "passed"
    ledger["status"] = overall
    ledger["endedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not _sync_process_ledger(ledger):
        ledger["status"] = "failed"
        ledger["failureCategory"] = "ledger_mismatch"
    return {"status": ledger["status"], **reports}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("showcase", "final", "candidate", "portfolio_a", "portfolio_b", "portfolio_final"),
        required=True,
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=None)
    args = parser.parse_args()

    if args.lock is None:
        lock_path = (
            REPOSITORY_ROOT / f"docs/evidence/deepseek-release-lock-v3.0.1-final-{args.runtime_commit}.json"
            if args.phase == "candidate"
            else RELEASE_LOCK_PATH
        )
    else:
        lock_path = args.lock if args.lock.is_absolute() else REPOSITORY_ROOT / args.lock

    portfolio_phase = args.phase in {"portfolio_a", "portfolio_b", "portfolio_final"}
    existing_lock: dict[str, object] | None = None
    # A portfolio release has exactly two distinct consumed states. A records
    # its own batch before it can make a request; B may proceed only from a
    # recorded A success and records its own consumption before calling the
    # provider. Any other lock state is final.
    if lock_path.is_file():
        try:
            parsed = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            existing_lock = parsed
        if not portfolio_phase and existing_lock is not None and existing_lock.get("releaseId") == args.release_id:
            print(
                json.dumps(
                    {"status": "release_locked", "releaseId": args.release_id},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 4
        if portfolio_phase:
            if existing_lock is None or existing_lock.get("releaseId") != args.release_id:
                print(json.dumps({"status": "release_locked", "releaseId": args.release_id}, ensure_ascii=False), file=sys.stderr)
                return 4
            batches = existing_lock.get("batchIds")
            if not isinstance(batches, list):
                print(json.dumps({"status": "release_locked", "releaseId": args.release_id}, ensure_ascii=False), file=sys.stderr)
                return 4
            if args.phase == "portfolio_final":
                print(json.dumps({"status": "release_locked", "releaseId": args.release_id}, ensure_ascii=False), file=sys.stderr)
                return 4
            if args.phase == "portfolio_a" or existing_lock.get("status") != "BATCH_A_PASSED" or len(batches) != 1:
                print(json.dumps({"status": "release_locked", "releaseId": args.release_id}, ensure_ascii=False), file=sys.stderr)
                return 4
    elif args.phase == "portfolio_b":
        print(json.dumps({"status": "release_locked", "releaseId": args.release_id}, ensure_ascii=False), file=sys.stderr)
        return 4

    if settings.deepseek_model != "deepseek-flash":
        print("deepseek release batch refused: reviewed model is not deepseek-flash", file=sys.stderr)
        return 3

    if args.phase in {"candidate", "portfolio_a", "portfolio_b", "portfolio_final"}:
        if not re.fullmatch(r"[0-9a-f]{40}", args.runtime_commit):
            print("deepseek release batch refused: runtime commit must be a full SHA", file=sys.stderr)
            return 3
        identity_ok, identity_reason = _runtime_identity(args.runtime_commit)
        if not identity_ok:
            print(f"deepseek release batch refused: {identity_reason}", file=sys.stderr)
            return 3
    if portfolio_phase and not os.getenv("MALL_RELEASE_LEDGER_PATH"):
        print("deepseek release batch refused: shared ledger path is missing", file=sys.stderr)
        return 3

    batch_id = f"{args.phase}-{uuid.uuid4().hex[:12]}"
    # The formal entry point binds every required authorization dimension in
    # the host process.  The FastAPI container receives the same values through
    # Compose environment and request headers; a key by itself never unlocks
    # the shared HTTP guard.
    os.environ["MALL_RELEASE_BATCH_ID"] = batch_id
    os.environ["MALL_RELEASE_ID"] = args.release_id
    os.environ["MALL_PROVIDER_LIVE_AUTH"] = "1"
    os.environ["MALL_RUNTIME_PROVIDER_MODE"] = "live"
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
        if not _sync_process_ledger(ledger):
            ledger["status"] = "failed"
            ledger["failureCategory"] = "ledger_mismatch"
        payload = {"ledger": ledger, "report": {"status": ledger["status"], "ledgerMetrics": _reconciled_report_metrics(ledger)}}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": ledger["status"], "batchId": batch_id}, ensure_ascii=False))
        return 2 if ledger["status"] == "environment_blocked" else 1
    lock_payload: dict[str, object] = {
        "schemaVersion": "deepseek-release-lock.v2",
        "releaseId": args.release_id,
        "batchIds": [batch_id],
        "runtimeCommit": args.runtime_commit,
        "status": "RUNNING",
        "testRunComplete": False,
        "releaseQualified": False,
        "requests": 0,
        "totalTokens": 0,
    }
    lock_created = False
    if args.phase in {"candidate", "portfolio_a", "portfolio_final"}:
        try:
            if args.phase == "portfolio_a":
                lock_payload["status"] = "BATCH_A_RUNNING"
                lock_payload["phase"] = args.phase
            elif args.phase == "portfolio_final":
                lock_payload["status"] = "FINAL_RUNNING"
                lock_payload["phase"] = args.phase
            _atomic_create_json(lock_path, lock_payload)
            lock_created = True
        except FileExistsError:
            print(json.dumps({"status": "release_locked", "releaseId": args.release_id}, ensure_ascii=False), file=sys.stderr)
            return 4
    elif args.phase == "portfolio_b" and existing_lock is not None:
        lock_payload = dict(existing_lock)
        batch_ids = list(existing_lock.get("batchIds", []))
        batch_ids.append(batch_id)
        lock_payload.update({"batchIds": batch_ids, "status": "BATCH_B_RUNNING", "phase": args.phase})
        _atomic_replace_json(lock_path, lock_payload)
        lock_created = True

    report: dict[str, object]
    try:
        report = (
            _run_showcase(ledger)
            if args.phase == "showcase"
            else _run_final(ledger)
            if args.phase == "final"
            else _run_candidate(ledger, args.report.parent / f"{batch_id}-artifacts")
            if args.phase == "candidate"
            else _run_portfolio_showcase(ledger, args.report.parent / f"{batch_id}-artifacts")
            if args.phase == "portfolio_a"
            else _run_portfolio_b(ledger, args.report.parent / f"{batch_id}-artifacts")
        )
    except KeyboardInterrupt:
        ledger["status"] = "interrupted"
        ledger["failureCategory"] = "interrupted"
        report = {"status": "interrupted", "failureCategory": "interrupted"}
    except Exception:
        # The release record is intentionally safe even when a local runner
        # implementation raises unexpectedly.  Do not write a traceback or
        # provider response into the report.
        ledger["status"] = "failed"
        ledger["failureCategory"] = "runner_exception"
        report = {"status": "failed", "failureCategory": "runner_exception"}
    # Batch helpers normally set the ledger status themselves. Keep the
    # top-level contract defensive so a future helper cannot emit a completed
    # report while leaving an immutable lock with an undefined status.
    if ledger.get("status") is None and isinstance(report, dict) and isinstance(report.get("status"), str):
        ledger["status"] = report["status"]
    # Always reconcile before either the report or the immutable lock is
    # written.  A missing host path is a gate failure, never a silent zero.
    if args.phase in {"candidate", "final", "showcase", "portfolio_a", "portfolio_b", "portfolio_final"}:
        if not _sync_process_ledger(ledger):
            ledger["status"] = "failed"
            ledger["failureCategory"] = "ledger_mismatch"
    if isinstance(report, dict):
        report["ledgerMetrics"] = _reconciled_report_metrics(ledger)
    ledger["testRunComplete"] = bool(
        args.phase in {"candidate", "portfolio_b", "portfolio_final"}
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
    if lock_created:
        lock_payload.update({
            "status": (
                "BATCH_A_PASSED" if args.phase == "portfolio_a" and ledger.get("status") == "passed"
                else "PASSED" if args.phase in {"portfolio_b", "portfolio_final"} and ledger.get("status") == "passed"
                else "INTERRUPTED" if ledger.get("status") == "interrupted"
                else "FAILED"
            ),
            "testRunComplete": ledger.get("testRunComplete"),
            "releaseQualified": ledger.get("releaseQualified"),
            "requests": ledger.get("requests"),
            "totalTokens": ledger.get("totalTokens"),
        })
        _atomic_replace_json(lock_path, lock_payload)
    return 2 if ledger.get("status") == "environment_blocked" else 1 if ledger.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
