"""Run the offline v3.0.4 v2 Runtime + holdout contract replay once."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.runtime.contract_replay_evaluation import run_contract_replay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("tmp/v304-contract-replay/replay.json"))
    args = parser.parse_args()
    report = run_contract_replay(report_path=args.report)
    print(json.dumps({key: report[key] for key in ("status", "caseCount", "passed", "failed", "environmentBlocked", "providerCalls", "providerTokens", "fixtureSha256", "report") if key in report}, ensure_ascii=False))
    print(f"report={args.report.as_posix()}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
