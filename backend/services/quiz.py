import json
from datetime import datetime, date

from database import get_db


def update_topic_score(user_id: int, topic: str, is_correct: bool):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM topic_scores WHERE user_id = ? AND topic = ?",
            (user_id, topic),
        ).fetchone()

        if row:
            correct = row["correct_answers"] + (1 if is_correct else 0)
            wrong = row["wrong_answers"] + (0 if is_correct else 1)
        else:
            correct = 1 if is_correct else 0
            wrong = 0 if is_correct else 1

        total = correct + wrong
        mastery = round((correct / total) * 100, 1) if total else 0

        conn.execute(
            """INSERT INTO topic_scores (user_id, topic, correct_answers, wrong_answers, mastery_percentage, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, topic) DO UPDATE SET
                 correct_answers = excluded.correct_answers,
                 wrong_answers = excluded.wrong_answers,
                 mastery_percentage = excluded.mastery_percentage,
                 updated_at = excluded.updated_at""",
            (user_id, topic, correct, wrong, mastery, now),
        )


def record_quiz_attempt(
    user_id: int,
    topic: str,
    question_type: str,
    difficulty: str,
    question: str,
    options: list | None,
    correct_answer: str,
    user_answer: str,
    is_correct: bool,
):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO quiz_attempts
               (user_id, topic, question_type, difficulty, question, options_json,
                correct_answer, user_answer, is_correct, score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                topic,
                question_type,
                difficulty,
                question,
                json.dumps(options) if options else None,
                correct_answer,
                user_answer,
                1 if is_correct else 0,
                1.0 if is_correct else 0.0,
                now,
            ),
        )
    update_topic_score(user_id, topic, is_correct)
    _touch_study_streak(user_id)


def _touch_study_streak(user_id: int):
    today = date.today().isoformat()
    with get_db() as conn:
        user = conn.execute("SELECT study_streak, last_study_date FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return
        streak = user["study_streak"] or 0
        last = user["last_study_date"]
        if last == today:
            return
        from datetime import timedelta

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last == yesterday:
            streak += 1
        else:
            streak = 1
        conn.execute(
            "UPDATE users SET study_streak = ?, last_study_date = ? WHERE id = ?",
            (streak, today, user_id),
        )


def get_weak_topics(user_id: int, limit: int = 5) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT topic, correct_answers, wrong_answers, mastery_percentage
               FROM topic_scores WHERE user_id = ?
               ORDER BY mastery_percentage ASC, wrong_answers DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_strong_topics(user_id: int, limit: int = 5) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT topic, correct_answers, wrong_answers, mastery_percentage
               FROM topic_scores WHERE user_id = ?
               ORDER BY mastery_percentage DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
