"""Run the committed offline AI quality-evaluation suite for development/CI."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.quality_evaluation_agent import run_quality_evaluation


def main() -> int:
    # CI must stay deterministic and must never invoke a provider. The live
    # synthetic profile is developer/manual only and is selected explicitly
    # through the protected quality page or a local invocation.
    report = run_quality_evaluation(
        execution_mode="contract_mock",
        enable_ai_failure_analysis=False,
    )
    print(
        "quality_evaluation "
        f"suite={report.suite_version} total={report.total} "
        f"passed={report.passed} failed={report.failed}"
    )
    for case in report.cases:
        print(
            "quality_case "
            f"case_id={case.case_id} target={case.target_agent} "
            f"status={case.status} violations={','.join(case.violations) or 'none'}"
        )
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
