from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.ai import tutor_chat, tutor_chat_stream
from services.search import get_topics

router = APIRouter(prefix="/api/chat", tags=["chat"])

USER_ID = 1


class ChatRequest(BaseModel):
    message: str
    topic: str | None = None


@router.post("")
async def chat(req: ChatRequest):
    return await tutor_chat(USER_ID, req.message, req.topic)


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message required")

    async def event_stream():
        async for chunk in tutor_chat_stream(USER_ID, req.message.strip(), req.topic):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


@router.get("/topics")
def topics():
    return {"topics": get_topics(USER_ID)}
