import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    # DeepSeek — 聊天/LLM（国内直连，不用 VPN）
    deepseek_api_key: str | None = os.getenv("DEEPSEEK_API_KEY")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_base_url: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    deepseek_timeout_seconds: float = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))

    # The policy index always uses the packaged local model. This keeps the
    # customer demo independent from a cloud embedding API and VPN routing.
    local_embedding_model: str = os.getenv(
        "LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
    )
    local_embedding_model_path: str = os.getenv(
        "LOCAL_EMBEDDING_MODEL_PATH", "models/embedding/bge-small-zh-v1.5"
    )
    local_embedding_dimension: int = int(
        os.getenv("LOCAL_EMBEDDING_DIMENSION", "512")
    )
    local_embedding_threads: int = int(os.getenv("LOCAL_EMBEDDING_THREADS", "1"))

    # Java mall 后端
    mall_api_base_url: str = os.getenv("MALL_API_BASE_URL", "http://127.0.0.1:8085")
    mall_api_timeout_seconds: float = float(os.getenv("MALL_API_TIMEOUT_SECONDS", "10"))
    mall_admin_api_base_url: str = os.getenv(
        "MALL_ADMIN_API_BASE_URL", "http://127.0.0.1:8080"
    )
    mall_admin_api_timeout_seconds: float = float(
        os.getenv("MALL_ADMIN_API_TIMEOUT_SECONDS", "10")
    )
    ai_case_handoff_service_key: str = os.getenv(
        "AI_CASE_HANDOFF_SERVICE_KEY", "local-build19-service-key"
    )
    ai_after_sales_service_key: str = os.getenv(
        "AI_AFTER_SALES_SERVICE_KEY", "local-build21-after-sales-key"
    )

    # Conversation state. Memory is intentionally the local-development default;
    # deployed environments set CONVERSATION_STORE_BACKEND=redis.
    conversation_store_backend: str = os.getenv("CONVERSATION_STORE_BACKEND", "memory")
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    redis_key_prefix: str = os.getenv("REDIS_KEY_PREFIX", "mall-ai:conversation")
    conversation_ttl_seconds: int = int(os.getenv("CONVERSATION_TTL_SECONDS", "86400"))
    conversation_recent_message_limit: int = int(
        os.getenv("CONVERSATION_RECENT_MESSAGE_LIMIT", "6")
    )
    conversation_context_token_budget: int = int(
        os.getenv("CONVERSATION_CONTEXT_TOKEN_BUDGET", "1800")
    )
    conversation_summary_max_chars: int = int(
        os.getenv("CONVERSATION_SUMMARY_MAX_CHARS", "1600")
    )

    # Build 21 durable Human-in-the-Loop diagnosis checkpoints.  Docker uses
    # Redis so a FastAPI restart can recover a safe waiting state; memory is
    # intentionally restricted to unit tests and simple local development.
    diagnosis_checkpoint_backend: str = os.getenv(
        "DIAGNOSIS_CHECKPOINT_BACKEND",
        os.getenv("CONVERSATION_STORE_BACKEND", "memory"),
    )
    diagnosis_checkpoint_key_prefix: str = os.getenv(
        "DIAGNOSIS_CHECKPOINT_KEY_PREFIX", "mall-ai:diagnosis-checkpoint"
    )
    diagnosis_checkpoint_ttl_seconds: int = int(
        os.getenv("DIAGNOSIS_CHECKPOINT_TTL_SECONDS", "1800")
    )
    diagnosis_checkpoint_lock_seconds: int = int(
        os.getenv("DIAGNOSIS_CHECKPOINT_LOCK_SECONDS", "20")
    )
    diagnosis_checkpoint_max_bytes: int = int(
        os.getenv("DIAGNOSIS_CHECKPOINT_MAX_BYTES", "32768")
    )
    diagnosis_checkpoint_secret: str = os.getenv(
        "DIAGNOSIS_CHECKPOINT_SECRET", "local-build21-diagnosis-checkpoint-secret"
    )

    # RAG evidence and no-evidence policy.
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))
    rag_max_distance: float = float(os.getenv("RAG_MAX_DISTANCE", "0.48"))
    # Build 20 keeps dense retrieval as the reviewed default until the same
    # versioned golden suite proves a safer/better local alternative.
    rag_retrieval_mode: str = os.getenv("RAG_RETRIEVAL_MODE", "dense")
    rag_hybrid_candidate_k: int = int(os.getenv("RAG_HYBRID_CANDIDATE_K", "8"))
    rag_bm25_min_score: float = float(os.getenv("RAG_BM25_MIN_SCORE", "0.1"))
    rag_rrf_k: int = int(os.getenv("RAG_RRF_K", "60"))
    rag_reranker_top_n: int = int(os.getenv("RAG_RERANKER_TOP_N", "8"))
    rag_reranker_model: str = os.getenv(
        "RAG_RERANKER_MODEL", "BAAI/bge-reranker-base"
    )
    rag_reranker_model_path: str = os.getenv(
        "RAG_RERANKER_MODEL_PATH", "models/reranker/bge-reranker-base"
    )
    rag_reranker_threads: int = int(os.getenv("RAG_RERANKER_THREADS", "1"))

    # Trusted publication scope for the customer policy corpus.  Publishing a
    # new policy revision requires changing this server configuration together
    # with re-ingesting the reviewed documents; an LLM may never select a
    # policy version.  Product category is intentionally absent here because
    # the current Java order snapshot exposes no authoritative category field.
    rag_active_policy_version: str | None = (
        os.getenv("RAG_ACTIVE_POLICY_VERSION", "V1.1").strip() or None
    )
    rag_policy_language: str = os.getenv("RAG_POLICY_LANGUAGE", "zh-CN")
    rag_policy_document_type: str = os.getenv("RAG_POLICY_DOCUMENT_TYPE", "policy")

    # Explicit developer/CI quality checkpoints. These settings are never
    # consulted by customer request handlers.
    quality_checkpoint_max_cases: int = int(
        os.getenv("QUALITY_CHECKPOINT_MAX_CASES", "60")
    )
    quality_checkpoint_max_total_seconds: float = float(
        os.getenv("QUALITY_CHECKPOINT_MAX_TOTAL_SECONDS", "300")
    )
    quality_checkpoint_llm_timeout_seconds: float = float(
        os.getenv("QUALITY_CHECKPOINT_LLM_TIMEOUT_SECONDS", "20")
    )
    quality_checkpoint_llm_max_attempts: int = int(
        os.getenv("QUALITY_CHECKPOINT_LLM_MAX_ATTEMPTS", "1")
    )

    # Reliability controls. Docker switches the shared controls to Redis;
    # in-memory is deliberately limited to isolated local/unit-test runs.
    reliability_backend: str = os.getenv("RELIABILITY_BACKEND", "memory")
    reliability_key_prefix: str = os.getenv("RELIABILITY_KEY_PREFIX", "mall-ai:reliability")
    reliability_circuit_failure_threshold: int = int(
        os.getenv("RELIABILITY_CIRCUIT_FAILURE_THRESHOLD", "3")
    )
    reliability_circuit_cooldown_seconds: int = int(
        os.getenv("RELIABILITY_CIRCUIT_COOLDOWN_SECONDS", "20")
    )


settings = Settings()
