from fastapi import APIRouter

from app.schemas.intent import IntentRequest, IntentResponse
from app.services.intent_service import detect_intent


router = APIRouter(tags=["intent"])


@router.post("/intent")
def intent(request: IntentRequest) -> IntentResponse:
    return detect_intent(request.message)
