from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from routers.chat import ChatRequest, run_chat, stream_chat
from services.study_plan import (
    calculate_study_targets,
    get_exam_plan,
    get_study_overview,
    log_study_session,
    save_exam_plan,
)

router = APIRouter(prefix="/api/study", tags=["study"])

USER_ID = 1


class ExamPlanBody(BaseModel):
    exam_start: str
    exam_end: str
    expected_cgpa: float = Field(ge=0, le=10)
    current_cgpa: float = Field(ge=0, le=10)


class LogSessionBody(BaseModel):
    minutes: int = Field(ge=1, le=600)
    topic: str | None = None


@router.get("/overview")
def study_overview():
    return get_study_overview(USER_ID)


@router.get("/exam-plan")
def exam_plan_get():
    plan = get_exam_plan(USER_ID)
    targets = calculate_study_targets(USER_ID)
    return {"plan": plan, "targets": targets}


@router.post("/exam-plan")
def exam_plan_save(body: ExamPlanBody):
    if body.exam_start >= body.exam_end:
        raise HTTPException(400, "Exam end must be after exam start")
    plan = save_exam_plan(
        USER_ID,
        body.exam_start,
        body.exam_end,
        body.expected_cgpa,
        body.current_cgpa,
    )
    return {"plan": plan, "targets": calculate_study_targets(USER_ID)}


@router.post("/sessions")
def log_session(body: LogSessionBody):
    log_study_session(USER_ID, body.minutes, body.topic)
    return {"targets": calculate_study_targets(USER_ID)}


@router.post("/mentor/chat")
async def mentor_chat_endpoint(body: ChatRequest):
    return await run_chat("mentor", body)


@router.post("/mentor/stream")
async def mentor_stream(body: ChatRequest):
    return await stream_chat("mentor", body)
