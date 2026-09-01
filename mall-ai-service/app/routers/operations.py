from fastapi import APIRouter, Header, HTTPException, Path, Query

from app.schemas.operations import (
    CaseHandoffView,
    HandoffOverview,
    OperationsAnalysisResponse,
    OperatorLoginRequest,
    OperatorLoginResponse,
    OperatorProfile,
)
from app.services.operations_agent import OperationsAnalysisError, analyze_case
from app.services.operations_client import (
    OperationsApiError,
    get_case_handoff,
    get_current_operator,
    get_handoff_overview,
    list_case_handoffs,
    login_operator,
)


router = APIRouter(prefix="/operations", tags=["operations"])


@router.post("/auth/login", response_model=OperatorLoginResponse)
def operations_login(request: OperatorLoginRequest) -> OperatorLoginResponse:
    try:
        return login_operator(request.username, request.password)
    except OperationsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/me", response_model=OperatorProfile)
def operations_me(
    authorization: str | None = Header(default=None),
) -> OperatorProfile:
    try:
        return get_current_operator(authorization)
    except OperationsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/cases", response_model=list[CaseHandoffView])
def operations_cases(
    authorization: str | None = Header(default=None),
) -> list[CaseHandoffView]:
    try:
        get_current_operator(authorization)
        return list_case_handoffs(authorization)
    except OperationsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/handoff-overview", response_model=HandoffOverview)
def operations_handoff_overview(
    authorization: str | None = Header(default=None),
    window_days: int = Query(default=7, alias="windowDays"),
) -> HandoffOverview:
    if window_days not in {7, 30}:
        raise HTTPException(status_code=400, detail="仅支持 7 或 30 天运营聚合窗口。")
    try:
        get_current_operator(authorization)
        return get_handoff_overview(window_days, authorization)
    except OperationsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/cases/{case_id}/analysis",
    response_model=OperationsAnalysisResponse,
)
def operations_case_analysis(
    case_id: str = Path(pattern=r"^[a-f0-9-]{36}$"),
    authorization: str | None = Header(default=None),
    window_days: int = Query(default=7, alias="windowDays"),
) -> OperationsAnalysisResponse:
    if window_days not in {7, 30}:
        raise HTTPException(status_code=400, detail="仅支持 7 或 30 天运营聚合窗口。")
    try:
        get_current_operator(authorization)
        case = get_case_handoff(case_id, authorization)
        result = analyze_case(
            case=case,
            authorization=authorization,
            preferred_window_days=window_days,
        )
        return OperationsAnalysisResponse(
            case=result.case,
            metrics=result.metrics,
            draft=result.draft,
        )
    except OperationsAnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OperationsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
