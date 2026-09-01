"""Separate FastAPI boundary for the dedicated human service-case role."""

from fastapi import APIRouter, Header, HTTPException, Path, Query

from app.schemas.service_case import (
    ServiceProcessorActionRequest,
    ServiceProcessorCaseView,
    ServiceProcessorClaimRequest,
    ServiceProcessorLoginRequest,
    ServiceProcessorLoginResponse,
    ServiceProcessorProfile,
)
from app.services.service_operations_client import (
    ServiceProcessorApiError,
    act_on_service_case,
    claim_service_case,
    get_current_service_processor,
    list_service_processor_cases,
    login_service_processor,
)


router = APIRouter(prefix="/service-operations", tags=["service-operations"])


@router.post("/auth/login", response_model=ServiceProcessorLoginResponse)
def service_processor_login(request: ServiceProcessorLoginRequest) -> ServiceProcessorLoginResponse:
    try:
        return login_service_processor(request.username, request.password)
    except ServiceProcessorApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/me", response_model=ServiceProcessorProfile)
def service_processor_me(authorization: str | None = Header(default=None)) -> ServiceProcessorProfile:
    try:
        return get_current_service_processor(authorization)
    except ServiceProcessorApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/cases", response_model=list[ServiceProcessorCaseView])
def service_processor_cases(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=30, ge=1, le=50),
) -> list[ServiceProcessorCaseView]:
    try:
        get_current_service_processor(authorization)
        return list_service_processor_cases(authorization, limit)
    except ServiceProcessorApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/cases/{case_id}/claim", response_model=ServiceProcessorCaseView)
def service_processor_claim(
    request: ServiceProcessorClaimRequest,
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> ServiceProcessorCaseView:
    try:
        get_current_service_processor(authorization)
        return claim_service_case(case_id, request, authorization)
    except ServiceProcessorApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/cases/{case_id}/actions", response_model=ServiceProcessorCaseView)
def service_processor_action(
    request: ServiceProcessorActionRequest,
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
) -> ServiceProcessorCaseView:
    try:
        get_current_service_processor(authorization)
        return act_on_service_case(case_id, request, authorization)
    except ServiceProcessorApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
