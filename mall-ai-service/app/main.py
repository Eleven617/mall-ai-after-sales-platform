import os

from fastapi import FastAPI, Request

from app.routers import (
    authentication,
    agent_tasks,
    chat,
    customer_service,
    health,
    intent,
    mcp,
    operations,
    quality,
    service_operations,
)
from app.services.request_context import request_correlation
from app.services.release_ledger import release_ledger_context
from app.services.provider_guard import provider_access_context


app = FastAPI(
    title="mall-ai-service",
    description="Minimal AI service for ecommerce customer support learning.",
    version="0.1.0",
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    """Create/propagate an opaque request correlation without trusting identity headers."""

    with release_ledger_context(
        batch_id=request.headers.get("x-mall-release-batch-id"),
        source="fastapi",
        scenario=request.headers.get("x-mall-release-scenario"),
    ):
        with provider_access_context(
            mode=request.headers.get(
                "x-mall-provider-mode",
                os.getenv("MALL_RUNTIME_PROVIDER_MODE", "offline"),
            ),
            release_id=request.headers.get("x-mall-release-id") or os.getenv("MALL_RELEASE_ID"),
            batch_id=request.headers.get("x-mall-release-batch-id") or os.getenv("MALL_RELEASE_BATCH_ID"),
            ledger_path=request.headers.get("x-mall-release-ledger-path") or os.getenv("MALL_RELEASE_LEDGER_PATH"),
            runtime_commit=request.headers.get("x-mall-runtime-commit") or os.getenv("MALL_RUNTIME_COMMIT"),
            authorized=os.getenv("MALL_PROVIDER_LIVE_AUTH", "0") == "1",
        ):
            with request_correlation(
                request.headers.get("x-correlation-id"),
                request.headers.get("traceparent"),
            ) as (correlation_id, traceparent):
                response = await call_next(request)
                response.headers["X-Correlation-Id"] = correlation_id
                response.headers["traceparent"] = traceparent
                return response

app.include_router(health.router)
app.include_router(authentication.router)
app.include_router(agent_tasks.router)
app.include_router(chat.router)
app.include_router(intent.router)
app.include_router(customer_service.router)
app.include_router(operations.router)
app.include_router(quality.router)
app.include_router(service_operations.router)
app.include_router(mcp.router)
