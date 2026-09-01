"""Run the committed offline Agent evaluation suite without external services."""
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.agent_evaluation import (  # noqa: E402
    evaluate_agent_cases,
    load_agent_evaluation_cases,
)


if __name__ == "__main__":
    cases_path = PROJECT_ROOT / "evals" / "agent_cases.json"
    report = evaluate_agent_cases(load_agent_evaluation_cases(cases_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["failed_cases"] == 0 else 1)
