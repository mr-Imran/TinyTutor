import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from services import grading
from services.document_processor import IMAGE_TYPES

router = APIRouter(prefix="/api/grading", tags=["grading"])

USER_ID = 1
MAX_PHOTO_BYTES = 15 * 1024 * 1024


class Criterion(BaseModel):
    name: str
    description: str = ""
    points: int = 1


class RubricBody(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    topic: str | None = None


class EssayBody(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    answer: str = Field(min_length=1, max_length=grading.MAX_ANSWER_CHARS)
    rubric: list[Criterion] | None = None
    topic: str | None = None


class TeachBackBody(BaseModel):
    concept: str = Field(min_length=2, max_length=300)
    explanation: str = Field(min_length=1, max_length=grading.MAX_ANSWER_CHARS)
    topic: str | None = None


@router.post("/rubric")
async def rubric(body: RubricBody):
    try:
        return {"criteria": await grading.make_rubric(USER_ID, body.question, body.topic)}
    except grading.GradingError as e:
        raise HTTPException(400, str(e))


@router.post("/essay")
async def essay(body: EssayBody):
    try:
        return await grading.grade_answer(
            USER_ID, body.question, body.answer,
            [c.model_dump() for c in body.rubric] if body.rubric else None, body.topic,
        )
    except grading.GradingError as e:
        raise HTTPException(400, str(e))


@router.post("/essay/photo")
async def essay_photo(
    file: UploadFile = File(...),
    question: str = Form(...),
    rubric: str | None = Form(None),
    topic: str | None = Form(None),
):
    """Grade a photographed handwritten answer: transcribe with the vision model, then grade."""
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_TYPES:
        raise HTTPException(400, f"Upload a photo ({', '.join(IMAGE_TYPES)})")
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(400, "Photo too large (max 15MB)")
    try:
        criteria = json.loads(rubric) if rubric else None
    except json.JSONDecodeError:
        raise HTTPException(400, "Rubric must be JSON")
    try:
        text = await grading.transcribe_answer(data, IMAGE_TYPES[ext])
        return await grading.grade_answer(USER_ID, question, text, criteria, topic, transcription=text)
    except grading.GradingError as e:
        raise HTTPException(400, str(e))


@router.post("/teach-back")
async def teach_back(body: TeachBackBody):
    try:
        return await grading.teach_back(USER_ID, body.concept, body.explanation, body.topic)
    except grading.GradingError as e:
        raise HTTPException(400, str(e))


@router.get("/history")
def history(kind: str | None = None, limit: int = 30):
    return grading.history(USER_ID, kind, min(max(limit, 1), 200))
