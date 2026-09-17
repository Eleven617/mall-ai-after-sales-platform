import os

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.runtime.providers import RUNTIME_PROMPT_VERSION
from app.services.readiness import get_readiness
from app.skills.catalog import SKILL_CATALOG_VERSION


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check() -> dict[str, str]:
    report = get_readiness()
    if report["status"] != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=report,
        )
    return report


@router.get("/health/version")
def runtime_version() -> dict[str, str]:
    """Expose only the reviewed runtime identity needed by release checks."""

    return {
        "runtimeCommit": os.getenv("MALL_RUNTIME_COMMIT", "unknown"),
        "imageRevision": os.getenv("MALL_IMAGE_REVISION", "unknown"),
        "providerMode": os.getenv("MALL_RUNTIME_PROVIDER_MODE", "offline"),
        "model": settings.deepseek_model,
        "thinkingMode": "enabled",
        "reasoningEffort": "high",
        "promptVersion": os.getenv("MALL_PROMPT_VERSION", RUNTIME_PROMPT_VERSION),
        "skillCatalogVersion": SKILL_CATALOG_VERSION,
    }
