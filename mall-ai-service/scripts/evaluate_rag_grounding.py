"""Run reviewed RAG grounding contracts against the configured live providers."""
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rag_grounding_evaluation import (  # noqa: E402
    evaluate_rag_grounding_cases,
    load_rag_grounding_cases,
)


if __name__ == "__main__":
    cases_path = PROJECT_ROOT / "evals" / "rag_grounding_cases.json"
    report = evaluate_rag_grounding_cases(load_rag_grounding_cases(cases_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "environment_blocked":
        raise SystemExit(2)
    raise SystemExit(0 if report["status"] == "passed" else 1)
