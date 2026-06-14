import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db, row_to_dict
from services.ai import (
    check_broad_answer,
    evaluate_answer,
    generate_ai_help,
    generate_broad_question,
    generate_quiz_question,
)
from services.quiz import record_quiz_attempt

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

USER_ID = 1


class GenerateRequest(BaseModel):
    topic: str
    question_type: str = "mcq"
    difficulty: str = "medium"


class SubmitRequest(BaseModel):
    topic: str
    question_type: str
    difficulty: str
    question: str
    options: list[str] | None = None
    correct_answer: str
    user_answer: str


class ExamRequest(BaseModel):
    topics: list[str]
    count: int = 5
    difficulty: str = "medium"


class BroadGenerateRequest(BaseModel):
    topic: str
    difficulty: str = "medium"


class BroadCheckRequest(BaseModel):
    question: str
    user_answer: str
    topic: str | None = None


class AiHelpRequest(BaseModel):
    question: str
    user_answer: str | None = None
    topic: str | None = None


@router.post("/generate")
async def generate(req: GenerateRequest):
    if req.question_type not in ("mcq", "true_false", "short_answer"):
        raise HTTPException(400, "Invalid question_type")
    if req.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(400, "Invalid difficulty")
    return await generate_quiz_question(USER_ID, req.topic, req.question_type, req.difficulty)


@router.post("/submit")
async def submit(req: SubmitRequest):
    result = await evaluate_answer(
        req.question, req.correct_answer, req.user_answer, req.question_type
    )
    record_quiz_attempt(
        USER_ID,
        req.topic,
        req.question_type,
        req.difficulty,
        req.question,
        req.options,
        req.correct_answer,
        req.user_answer,
        result["is_correct"],
    )
    return result


@router.post("/exam")
async def simulate_exam(req: ExamRequest):
    questions = []
    topics = req.topics or ["General"]
    for i in range(req.count):
        topic = topics[i % len(topics)]
        q = await generate_quiz_question(USER_ID, topic, "mcq", req.difficulty)
        questions.append(q)
    return {"questions": questions}


@router.post("/broad/generate")
async def broad_generate(req: BroadGenerateRequest):
    if not req.topic.strip():
        raise HTTPException(400, "Topic is required")
    if req.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(400, "Invalid difficulty")
    return await generate_broad_question(USER_ID, req.topic.strip(), req.difficulty)


@router.post("/broad/check")
async def broad_check(req: BroadCheckRequest):
    if not req.question.strip() or not req.user_answer.strip():
        raise HTTPException(400, "Question and answer are required")
    result = await check_broad_answer(USER_ID, req.question.strip(), req.user_answer.strip(), req.topic)
    topic = req.topic or "General"
    if result.get("matched") and result.get("is_correct") is not None:
        record_quiz_attempt(
            USER_ID,
            topic,
            "broad",
            "medium",
            req.question.strip(),
            None,
            "materials-based",
            req.user_answer.strip(),
            result["is_correct"],
        )
    return result


@router.post("/broad/ai-help")
async def broad_ai_help(req: AiHelpRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question is required")
    return await generate_ai_help(
        USER_ID,
        req.question.strip(),
        req.user_answer.strip() if req.user_answer else None,
        req.topic,
    )


@router.get("/history")
def history(limit: int = 50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM quiz_attempts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (USER_ID, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        if d.get("options_json"):
            d["options"] = json.loads(d["options_json"])
        out.append(d)
    return out
