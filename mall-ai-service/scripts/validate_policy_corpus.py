"""Validate the versioned demo policy corpus before re-indexing or evaluation."""
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.knowledge_contract import (  # noqa: E402
    KnowledgeContractError,
    assert_policy_corpus_valid,
)


if __name__ == "__main__":
    try:
        report = assert_policy_corpus_valid(
            PROJECT_ROOT / "app" / "knowledge",
            PROJECT_ROOT / "evals" / "rag_cases.json",
            PROJECT_ROOT / "evals" / "rag_grounding_cases.json",
        )
    except KnowledgeContractError as exc:
        print(
            json.dumps(
                {"status": "invalid", "reason": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)

    print(json.dumps({"status": "valid", **report}, ensure_ascii=False, indent=2))
