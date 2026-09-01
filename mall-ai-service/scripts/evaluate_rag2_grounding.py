"""Explicit live RAG2 grounding/abstention checkpoint; never a customer path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.llm_observability import TokenPricing  # noqa: E402
from app.services.rag2_evaluation import (  # noqa: E402
    evaluate_grounded_answer_suite,
    load_rag2_golden_suite,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dense", "hybrid", "hybrid_rerank"), required=True)
    parser.add_argument(
        "--max-cases",
        type=int,
        default=8,
        help="Explicit live budget; pass a reviewed full-suite count only when intended.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument(
        "--case-ids",
        nargs="+",
        help="Optional reviewed case IDs; replaces --max-cases for a targeted live smoke.",
    )
    parser.add_argument("--input-token-price-per-million", type=float)
    parser.add_argument("--output-token-price-per-million", type=float)
    args = parser.parse_args()
    if (args.input_token_price_per_million is None) != (args.output_token_price_per_million is None):
        raise SystemExit("Both token-price values are required together.")
    pricing = (
        TokenPricing(args.input_token_price_per_million, args.output_token_price_per_million)
        if args.input_token_price_per_million is not None
        else None
    )
    suite = load_rag2_golden_suite(PROJECT_ROOT / "evals" / "rag2_golden_cases.v1.json")
    report = evaluate_grounded_answer_suite(
        suite,
        mode=args.mode,
        pricing=pricing,
        timeout_seconds=args.timeout_seconds,
        max_attempts=args.max_attempts,
        max_cases=args.max_cases,
        case_ids=set(args.case_ids) if args.case_ids else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {"passed": 0, "quality_failed": 1, "environment_blocked": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
