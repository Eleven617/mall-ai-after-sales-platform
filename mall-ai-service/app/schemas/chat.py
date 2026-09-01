from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, examples=["Redis 是什么？"])


class ChatResponse(BaseModel):
    message: str
    reply: str
