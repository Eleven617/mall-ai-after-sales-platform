"""Run the committed RAG retrieval evaluation set."""
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rag_evaluation import (  # noqa: E402
    evaluate_rag_cases,
    load_rag_cases,
)
from app.services.embedding_service import EmbeddingServiceError  # noqa: E402
from app.services.vector_store import search_similar_batch  # noqa: E402


if __name__ == "__main__":
    cases_path = PROJECT_ROOT / "evals" / "rag_cases.json"
    try:
        report = evaluate_rag_cases(
            load_rag_cases(cases_path),
            batch_search=search_similar_batch,
        )
    except EmbeddingServiceError:
        # Provider availability is not a retrieval-quality result.  Keep this
        # report intentionally generic so API/provider diagnostics do not leak
        # into committed evaluation artifacts.
        report = {
            "mode": "live_vector",
            "status": "environment_blocked",
            "reason": "embedding_provider_unavailable",
            "next_action": "检查本地 Embedding 模型文件和索引配置后重试。",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
