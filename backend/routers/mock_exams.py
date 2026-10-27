from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import mock_exams

router = APIRouter(prefix="/api/mock-exams", tags=["mock-exams"])

USER_ID = 1


class CreateExamBody(BaseModel):
    topics: list[str] = Field(min_length=1)
    count: int = Field(default=10, ge=1, le=40)
    duration_minutes: int = Field(default=20, ge=1, le=240)
    difficulty: str = "medium"
    mix: list[str] = ["mcq", "true_false", "short_answer"]


class SubmitExamBody(BaseModel):
    answers: dict[int, str] = {}


@router.post("")
async def create(body: CreateExamBody):
    if body.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(400, "Invalid difficulty")
    return await mock_exams.create_exam(
        USER_ID, body.topics, body.count, body.duration_minutes, body.difficulty, body.mix
    )


@router.get("")
def history(limit: int = 20):
    return mock_exams.list_exams(USER_ID, min(max(limit, 1), 100))


@router.get("/{exam_id}")
def detail(exam_id: int):
    exam = mock_exams.get_exam(USER_ID, exam_id)
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam


@router.post("/{exam_id}/submit")
async def submit(exam_id: int, body: SubmitExamBody):
    exam = await mock_exams.submit_exam(USER_ID, exam_id, body.answers)
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam
