from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import misconceptions as mc

router = APIRouter(prefix="/api/misconceptions", tags=["misconceptions"])

USER_ID = 1


class AnswerBody(BaseModel):
    index: int
    answer: str


class StatusBody(BaseModel):
    status: str


@router.get("")
def overview():
    return {
        "misconceptions": mc.list_misconceptions(USER_ID),
        "pending": mc.pending_count(USER_ID),
        "recent_mistakes": mc.recent_mistakes(USER_ID),
        "min_mistakes": mc.MIN_MISTAKES,
        "resolve_streak": mc.RESOLVE_STREAK,
    }


@router.post("/analyze")
async def analyze():
    try:
        result = await mc.analyze(USER_ID)
    except mc.MisconceptionError as e:
        raise HTTPException(400, str(e))
    return {**result, **overview()}


@router.post("/{misconception_id}/drill")
async def drill(misconception_id: int):
    try:
        return await mc.new_drill(USER_ID, misconception_id)
    except mc.MisconceptionError as e:
        raise HTTPException(400, str(e))


@router.post("/{misconception_id}/answer")
def answer(misconception_id: int, body: AnswerBody):
    try:
        return mc.answer_drill(USER_ID, misconception_id, body.index, body.answer)
    except mc.MisconceptionError as e:
        raise HTTPException(400, str(e))


@router.put("/{misconception_id}/status")
def status(misconception_id: int, body: StatusBody):
    try:
        mc.set_status(USER_ID, misconception_id, body.status)
    except mc.MisconceptionError as e:
        raise HTTPException(400, str(e))
    return mc.get(USER_ID, misconception_id)
