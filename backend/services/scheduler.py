import asyncio
import json
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from database import get_db
from services.ai import generate_quiz_question
from services.quiz import get_weak_topics
from services.study_plan import calculate_study_targets, get_exam_plan, is_in_exam_window

_scheduler: BackgroundScheduler | None = None


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _insert_notification(user_id: int, topic: str, message: str, notification_type: str, correct_answer: str = "n/a"):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO scheduled_questions
               (user_id, topic, question, question_type, options_json, correct_answer,
                is_read, notification_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (user_id, topic, message, notification_type, None, correct_answer, notification_type, now),
        )


def study_reminder_job():
    """During exam window: send human-style study reminder with hours target."""
    user_id = 1
    plan = get_exam_plan(user_id)
    if not is_in_exam_window(plan):
        return

    targets = calculate_study_targets(user_id)
    weak = targets.get("weak_topics") or []
    topic = weak[0] if weak else "your materials"
    hours_day = targets.get("hours_per_day", 1)
    expected = targets.get("expected_cgpa", 8)
    remaining = targets.get("hours_remaining", 0)

    message = (
        f"Hey, it is study time. You are aiming for a {expected} CGPA. "
        f"Try to study about {hours_day} hours today. You still have roughly {remaining} hours left before the exam. "
        f"Start with {topic} while your memory is fresh."
    )
    _insert_notification(user_id, topic, message, "study")


def scheduled_question_job():
    """Every 30 min: quiz question (outside exam window) or study reminder (inside)."""
    user_id = 1
    plan = get_exam_plan(user_id)

    if is_in_exam_window(plan):
        study_reminder_job()
        return

    weak = get_weak_topics(user_id, limit=1)
    if not weak:
        with get_db() as conn:
            row = conn.execute(
                "SELECT DISTINCT topic FROM knowledge_chunks WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        if not row:
            return
        topic = row["topic"] or "General"
    else:
        topic = weak[0]["topic"]

    try:
        q = _run_async(generate_quiz_question(user_id, topic, "mcq", "medium"))
    except Exception:
        return

    _insert_notification(
        user_id,
        topic,
        q["question"],
        "quiz",
        q["correct_answer"],
    )


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(scheduled_question_job, "interval", minutes=30, id="study_or_quiz")
    _scheduler.start()
