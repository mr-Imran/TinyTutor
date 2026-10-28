from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import progress

router = APIRouter(prefix="/api/progress", tags=["progress"])

USER_ID = 1


class GoalBody(BaseModel):
    daily_goal: int = Field(ge=10, le=2000)


@router.get("")
def get_progress():
    return progress.get_progress(USER_ID)


@router.put("/goal")
def set_goal(body: GoalBody):
    progress.set_daily_goal(USER_ID, body.daily_goal)
    return progress.get_progress(USER_ID)


@router.post("/badges/seen")
def badges_seen():
    progress.mark_badges_seen(USER_ID)
    return {"ok": True}
