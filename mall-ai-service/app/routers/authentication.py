from fastapi import APIRouter, Header, HTTPException

from app.schemas.authentication import (
    CustomerLoginRequest,
    CustomerLoginResponse,
    MemberProfile,
)
from app.services.mall_client import (
    MallAuthenticationError,
    get_current_member,
    login_member,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=CustomerLoginResponse)
def login(request: CustomerLoginRequest) -> CustomerLoginResponse:
    """Delegate password verification and JWT signing to the Java mall service."""
    try:
        return login_member(request.username, request.password)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/me", response_model=MemberProfile)
def current_member(authorization: str | None = Header(default=None)) -> MemberProfile:
    """Validate the browser's current Java-issued Bearer Token."""
    try:
        return get_current_member(authorization)
    except MallAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
