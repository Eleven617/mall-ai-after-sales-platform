"""Run the versioned task-aware conversation evaluation suite.

``contract_mock`` is deterministic and safe for CI.  ``live_model_synthetic``
is manual only: it makes bounded P0 calls using synthetic inputs and safe
task summaries, with no Java/RAG/tool/business-write access.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.task_orchestration_evaluation import run_task_orchestration_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("contract_mock", "live_model_synthetic"),
        default="contract_mock",
    )
    parser.add_argument("--max-total-seconds", type=float, default=180.0)
    args = parser.parse_args()
    report = run_task_orchestration_evaluation(
        mode=args.mode,
        max_total_seconds=args.max_total_seconds,
    )
    print(
        "task_orchestration_evaluation "
        f"suite={report.suite_version} mode={report.mode} total={report.total} "
        f"passed={report.passed} failed={report.failed} "
        f"environment_blocked={report.environment_blocked} "
        f"total_elapsed_ms={report.total_elapsed_ms} p95_elapsed_ms={report.p95_elapsed_ms}"
    )
    for case in report.cases:
        print(
            "task_orchestration_case "
            f"case_id={case.case_id} status={case.status} elapsed_ms={case.elapsed_ms} "
            f"violations={','.join(case.violations) or 'none'}"
        )
    return 1 if report.failed or report.environment_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
