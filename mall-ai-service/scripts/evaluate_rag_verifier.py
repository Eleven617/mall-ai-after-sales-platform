"""Run the reviewed retrieval cases through the semantic evidence verifier."""
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embedding_service import EmbeddingServiceError  # noqa: E402
from app.services.rag_evidence_verifier import EvidenceVerificationError  # noqa: E402
from app.services.rag_evaluation import load_rag_cases  # noqa: E402
from app.services.rag_verifier_evaluation import evaluate_rag_verifier_cases  # noqa: E402


if __name__ == "__main__":
    try:
        report = evaluate_rag_verifier_cases(
            load_rag_cases(PROJECT_ROOT / "evals" / "rag_cases.json")
        )
    except (EmbeddingServiceError, EvidenceVerificationError):
        report = {
            "mode": "semantic_evidence_verifier",
            "status": "environment_blocked",
            "reason": "embedding_or_verifier_provider_unavailable",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
