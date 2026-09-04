"""Run the explicit live_model_agent_synthetic Task Runtime suite.

This command is developer/manual-only. It makes real provider calls when a
DeepSeek key is configured, but every goal and every Skill result is synthetic
and the gateway is read-only. Exit code 0 means all executed runs passed; 1
means quality failures; 2 means the environment/provider prevented a complete
run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.services.llm_observability import TokenPricing  # noqa: E402
from app.runtime.live_model_agent_evaluation import (  # noqa: E402
    DEFAULT_SUITE_PATH,
    run_live_model_agent_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--max-total-seconds", type=float, default=1200.0)
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--case-ids", nargs="*")
    parser.add_argument("--input-token-price-per-million", type=float)
    parser.add_argument("--output-token-price-per-million", type=float)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if (args.input_token_price_per_million is None) != (args.output_token_price_per_million is None):
        raise SystemExit("Both token price values are required together.")
    pricing = None
    if args.input_token_price_per_million is not None:
        if args.input_token_price_per_million < 0 or args.output_token_price_per_million < 0:
            raise SystemExit("Token prices cannot be negative.")
        pricing = TokenPricing(args.input_token_price_per_million, args.output_token_price_per_million)
    report = run_live_model_agent_evaluation(
        suite_path=args.suite,
        max_total_seconds=args.max_total_seconds,
        timeout_seconds=args.timeout_seconds,
        max_attempts=args.max_attempts,
        pricing=pricing,
        case_ids=set(args.case_ids) if args.case_ids else None,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    printable = dict(report)
    if args.summary:
        printable.pop("cases", None)
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    if report["failed"]:
        return 1
    if report["environmentBlocked"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
