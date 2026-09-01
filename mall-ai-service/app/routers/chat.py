from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import generate_chat_reply, stream_chat_reply


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
def chat(request: ChatRequest) -> ChatResponse:
    return generate_chat_reply(request)


@router.post("/stream")
def stream_chat(request: ChatRequest) -> StreamingResponse:
    def event_stream() -> Iterator[str]:
        for char in stream_chat_reply(request):
            yield f"data: {char}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
