"""Timed mock exams: mixed question types, no feedback until submit, graded report."""
import asyncio
import json
from datetime import datetime, timedelta

from database import get_db, row_to_dict
from services.ai import evaluate_answer, generate_quiz_question
from services.quiz import record_quiz_attempt

QUESTION_TYPES = ("mcq", "true_false", "short_answer")
# Submissions this long after the deadline are still graded but flagged late.
GRACE_SECONDS = 30
# Parallel LLM calls while generating questions (Ollama serialises anyway).
GENERATION_CONCURRENCY = 3


def plan_questions(topics: list[str], count: int, mix: list[str]) -> list[tuple[str, str]]:
    """Round-robin topics and question types: [(topic, question_type), ...]."""
    types = [t for t in mix if t in QUESTION_TYPES] or ["mcq"]
    return [(topics[i % len(topics)], types[i % len(types)]) for i in range(count)]


async def create_exam(
    user_id: int,
    topics: list[str],
    count: int,
    duration_minutes: int,
    difficulty: str,
    mix: list[str],
) -> dict:
    topics = [t for t in (t.strip() for t in topics) if t] or ["General"]
    plan = plan_questions(topics, count, mix)
    sem = asyncio.Semaphore(GENERATION_CONCURRENCY)

    async def make(topic, qtype):
        async with sem:
            return await generate_quiz_question(user_id, topic, qtype, difficulty)

    questions = await asyncio.gather(*(make(t, q) for t, q in plan))

    # The clock starts once questions are ready, not while the AI is writing them.
    started = datetime.utcnow()
    deadline = started + timedelta(minutes=duration_minutes)
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO mock_exams (user_id, topics_json, difficulty, duration_minutes,
                                       started_at, deadline_at, total)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, json.dumps(topics), difficulty, duration_minutes,
             started.isoformat(), deadline.isoformat(), len(questions)),
        )
        exam_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO mock_exam_questions
               (exam_id, position, topic, question_type, question, options_json, correct_answer, explanation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (exam_id, i, q["topic"], q["question_type"], q["question"],
                 json.dumps(q["options"]) if q.get("options") else None,
                 q["correct_answer"], q.get("explanation", ""))
                for i, q in enumerate(questions)
            ],
        )
    return get_exam(user_id, exam_id)


def _question_out(row, reveal: bool) -> dict:
    q = row_to_dict(row)
    q["options"] = json.loads(q.pop("options_json") or "null")
    if not reveal:
        for hidden in ("correct_answer", "explanation", "is_correct", "feedback"):
            q.pop(hidden, None)
    return q


def get_exam(user_id: int, exam_id: int) -> dict | None:
    with get_db() as conn:
        exam = conn.execute(
            "SELECT * FROM mock_exams WHERE id = ? AND user_id = ?", (exam_id, user_id)
        ).fetchone()
        if not exam:
            return None
        rows = conn.execute(
            "SELECT * FROM mock_exam_questions WHERE exam_id = ? ORDER BY position", (exam_id,)
        ).fetchall()
    out = row_to_dict(exam)
    out["topics"] = json.loads(out.pop("topics_json"))
    out["report"] = json.loads(out.pop("report_json") or "null")
    submitted = out["status"] == "submitted"
    out["questions"] = [_question_out(r, reveal=submitted) for r in rows]
    out["server_time"] = datetime.utcnow().isoformat()
    return out


def list_exams(user_id: int, limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, topics_json, difficulty, duration_minutes, status, started_at,
                      submitted_at, score, total, late
               FROM mock_exams WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["topics"] = json.loads(d.pop("topics_json"))
        out.append(d)
    return out


def build_report(graded: list[dict]) -> dict:
    by_topic: dict[str, dict] = {}
    for q in graded:
        t = by_topic.setdefault(q["topic"], {"topic": q["topic"], "correct": 0, "total": 0})
        t["total"] += 1
        t["correct"] += 1 if q["is_correct"] else 0
    topics = []
    for t in by_topic.values():
        t["percentage"] = round(t["correct"] / t["total"] * 100, 1)
        topics.append(t)
    topics.sort(key=lambda t: t["percentage"])
    correct = sum(1 for q in graded if q["is_correct"])
    return {
        "correct": correct,
        "total": len(graded),
        "percentage": round(correct / len(graded) * 100, 1) if graded else 0.0,
        "topics": topics,
        "weakest_topic": topics[0]["topic"] if topics else None,
    }


async def submit_exam(user_id: int, exam_id: int, answers: dict[int, str]) -> dict | None:
    exam = get_exam(user_id, exam_id)
    if not exam:
        return None
    if exam["status"] == "submitted":
        return exam

    now = datetime.utcnow()
    late = now > datetime.fromisoformat(exam["deadline_at"]) + timedelta(seconds=GRACE_SECONDS)
    with get_db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM mock_exam_questions WHERE exam_id = ? ORDER BY position", (exam_id,)
            ).fetchall()
        ]

    graded = []
    for q in rows:
        answer = (answers.get(q["id"]) or "").strip()
        if answer:
            result = await evaluate_answer(q["question"], q["correct_answer"], answer, q["question_type"])
        else:
            result = {"is_correct": False, "feedback": f"Not answered. Correct answer: {q['correct_answer']}"}
        graded.append({**q, "user_answer": answer, **result})

    report = build_report(graded)
    with get_db() as conn:
        conn.executemany(
            "UPDATE mock_exam_questions SET user_answer = ?, is_correct = ?, feedback = ? WHERE id = ?",
            [(g["user_answer"], 1 if g["is_correct"] else 0, g["feedback"], g["id"]) for g in graded],
        )
        conn.execute(
            """UPDATE mock_exams SET status = 'submitted', submitted_at = ?, score = ?, late = ?, report_json = ?
               WHERE id = ?""",
            (now.isoformat(), report["correct"], 1 if late else 0, json.dumps(report), exam_id),
        )

    for g in graded:
        record_quiz_attempt(
            user_id, g["topic"], g["question_type"], exam["difficulty"], g["question"],
            json.loads(g["options_json"]) if g["options_json"] else None,
            g["correct_answer"], g["user_answer"], g["is_correct"], source="mock_exam",
        )
    return get_exam(user_id, exam_id)
