"""Run local RAG 2.0 retrieval measurements for selected pipeline modes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rag2_evaluation import (  # noqa: E402
    evaluate_retrieval_suite,
    load_rag2_golden_suite,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("dense", "hybrid", "hybrid_rerank"),
        default=["dense", "hybrid", "hybrid_rerank"],
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print aggregate mode metrics without synthetic per-case detail.",
    )
    args = parser.parse_args()
    suite = load_rag2_golden_suite(PROJECT_ROOT / "evals" / "rag2_golden_cases.v1.json")
    reports = [
        evaluate_retrieval_suite(suite, mode=mode, top_k=args.top_k)
        for mode in args.modes
    ]
    printable_reports = (
        [{key: value for key, value in report.items() if key != "results"} for report in reports]
        if args.summary
        else reports
    )
    print(json.dumps({"suite_version": suite["suite_version"], "reports": printable_reports}, ensure_ascii=False, indent=2))
    statuses = {report["status"] for report in reports}
    if "environment_blocked" in statuses:
        return 2
    return 1 if "quality_failed" in statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
