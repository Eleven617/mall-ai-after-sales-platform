from fastapi import FastAPI, Request

from app.routers import (
    authentication,
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


app = FastAPI(
    title="mall-ai-service",
    description="Minimal AI service for ecommerce customer support learning.",
    version="0.1.0",
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    """Create/propagate an opaque request correlation without trusting identity headers."""

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
app.include_router(chat.router)
app.include_router(intent.router)
app.include_router(customer_service.router)
app.include_router(operations.router)
app.include_router(quality.router)
app.include_router(service_operations.router)
app.include_router(mcp.router)
