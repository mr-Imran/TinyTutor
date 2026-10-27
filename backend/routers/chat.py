import base64
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import agent, chat_history, grounding, llm
from services.ai import chat_reply, llm_chat_stream, prepare_chat
from services.search import _chunks_by_id, get_topics
from services.text_style import humanize_text

router = APIRouter(prefix="/api/chat", tags=["chat"])

USER_ID = 1


class ChatRequest(BaseModel):
    message: str
    topic: str | None = None
    session_id: int | None = None


class RenameBody(BaseModel):
    title: str


def _open_session(kind: str, req: ChatRequest) -> tuple[int, list[dict]]:
    """Returns (session_id, prior history), creating a session on the first message."""
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Message required")
    if req.session_id is None:
        return chat_history.create_session(USER_ID, kind, message), []
    session = chat_history.get_session(USER_ID, req.session_id)
    if not session:
        raise HTTPException(404, "Chat session not found")
    return session["id"], chat_history.history_for_llm(session["id"])


async def run_chat(kind: str, req: ChatRequest) -> dict:
    session_id, history = _open_session(kind, req)
    message = req.message.strip()
    result = await chat_reply(USER_ID, kind, message, req.topic, history)
    # A failed turn is not saved, so error text never becomes context for later turns.
    if not result.pop("failed"):
        chat_history.add_message(session_id, "user", message)
        chat_history.add_message(session_id, "assistant", result["reply"], result["sources"])
    return {**result, "session_id": session_id}


async def stream_chat(kind: str, req: ChatRequest) -> StreamingResponse:
    """Streams plain text. Session id and citation sources travel in response headers."""
    session_id, history = _open_session(kind, req)
    message = req.message.strip()
    prompt, system, history, sources = await prepare_chat(USER_ID, kind, message, req.topic, history)

    async def event_stream():
        full, errors = "", []
        async for chunk in llm_chat_stream(prompt, system=system, history=history, errors=errors):
            full += chunk
            yield chunk
        # A failed turn is not saved, so error text never becomes context for later turns.
        if not errors:
            chat_history.add_message(session_id, "user", message)
            chat_history.add_message(session_id, "assistant", humanize_text(full), sources)

    encoded = base64.b64encode(json.dumps(sources).encode()).decode()
    return StreamingResponse(
        event_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Session-Id": str(session_id), "X-Sources": encoded},
    )


@router.post("/agent")
async def agent_chat(req: ChatRequest):
    """Agent mode: newline-delimited JSON events (see services.agent). Session id is in a header."""
    session_id, history = _open_session("tutor", req)
    message = req.message.strip()

    async def events():
        result: dict = {}
        async for event in agent.run_agent(USER_ID, message, req.topic, history, result):
            yield json.dumps(event) + "\n"
        # A failed turn is not saved, so error text never becomes context for later turns.
        if not result.get("failed") and result.get("text"):
            chat_history.add_message(session_id, "user", message)
            chat_history.add_message(session_id, "assistant", result["text"], result["sources"], result.get("cards"))

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"X-Session-Id": str(session_id)})


@router.get("/agent/status")
async def agent_status():
    cfg = llm.get_llm_config()
    return {"provider": cfg["provider"], "model": cfg["model"], "supported": await llm.supports_tools(cfg)}


@router.post("/sessions/{session_id}/check")
async def check_latest(session_id: int, use_ai: bool | None = None):
    """Check the latest answer in a chat against the notes it was built from."""
    if not chat_history.get_session(USER_ID, session_id):
        raise HTTPException(404, "Chat session not found")
    msg = chat_history.latest_assistant_message(session_id)
    if not msg:
        raise HTTPException(404, "No answer to check yet")
    ids = [s["chunk_id"] for s in msg["sources"] if s.get("chunk_id")]
    by_id = _chunks_by_id(ids)
    chunks = [{"n": s["n"], "content": by_id[s["chunk_id"]]["content"]}
              for s in msg["sources"] if s.get("chunk_id") in by_id]
    settings = grounding.settings()
    result = await grounding.check_answer(msg["content"], chunks, settings["ai_check"] if use_ai is None else use_ai)
    chat_history.save_grounding(msg["id"], result)
    return {"message_id": msg["id"], **result}


@router.post("")
async def chat(req: ChatRequest):
    return await run_chat("tutor", req)


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    return await stream_chat("tutor", req)


@router.get("/topics")
def topics():
    return {"topics": get_topics(USER_ID)}


@router.get("/sessions")
def sessions(kind: str | None = None):
    return chat_history.list_sessions(USER_ID, kind)


@router.get("/sessions/{session_id}")
def session_detail(session_id: int):
    session = chat_history.get_session(USER_ID, session_id)
    if not session:
        raise HTTPException(404, "Chat session not found")
    return {**session, "messages": chat_history.get_messages(session_id)}


@router.patch("/sessions/{session_id}")
def rename(session_id: int, body: RenameBody):
    chat_history.rename_session(USER_ID, session_id, body.title)
    return chat_history.get_session(USER_ID, session_id)


@router.delete("/sessions/{session_id}")
def delete(session_id: int):
    chat_history.delete_session(USER_ID, session_id)
    return {"ok": True}
