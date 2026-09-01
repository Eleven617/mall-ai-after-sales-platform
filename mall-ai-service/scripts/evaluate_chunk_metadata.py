"""Run the deterministic synthetic RAG chunk/metadata contract suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.chunk_metadata_evaluation import (  # noqa: E402
    evaluate_chunk_metadata_suite,
    load_chunk_metadata_suite,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    report = evaluate_chunk_metadata_suite(load_chunk_metadata_suite())
    if args.summary:
        report = {key: value for key, value in report.items() if key != "results"}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
