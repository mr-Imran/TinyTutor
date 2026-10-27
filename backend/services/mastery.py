"""Recency-weighted topic mastery.

Each answer is a mastery event. Its weight halves every HALF_LIFE_DAYS and is scaled by
difficulty, so recent and harder answers count more. A small prior pulls topics with
little evidence (or only old evidence) toward 50% instead of 0% or 100%.
"""
from datetime import datetime, timedelta

from database import get_db

HALF_LIFE_DAYS = 14.0
PRIOR_WEIGHT = 1.0
PRIOR_MASTERY = 0.5
DIFFICULTY_WEIGHTS = {"easy": 0.8, "medium": 1.0, "hard": 1.25}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "").split("+")[0])


def compute_mastery(events: list[tuple[bool, float, datetime]], now: datetime) -> float:
    """events: (is_correct, base_weight, created_at). Returns a percentage 0-100."""
    num = PRIOR_WEIGHT * PRIOR_MASTERY
    den = PRIOR_WEIGHT
    for is_correct, weight, created in events:
        age_days = max((now - created).total_seconds() / 86400, 0.0)
        w = weight * 0.5 ** (age_days / HALF_LIFE_DAYS)
        num += w * (1.0 if is_correct else 0.0)
        den += w
    return round(num / den * 100, 1)


def record_event(
    user_id: int, topic: str, is_correct: bool, difficulty: str = "medium", source: str = "quiz"
):
    now = datetime.utcnow()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO mastery_events (user_id, topic, is_correct, weight, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, topic, 1 if is_correct else 0, DIFFICULTY_WEIGHTS.get(difficulty, 1.0), source, now.isoformat()),
        )
        row = conn.execute(
            "SELECT correct_answers, wrong_answers FROM topic_scores WHERE user_id = ? AND topic = ?",
            (user_id, topic),
        ).fetchone()
        correct = (row["correct_answers"] if row else 0) + (1 if is_correct else 0)
        wrong = (row["wrong_answers"] if row else 0) + (0 if is_correct else 1)
        conn.execute(
            """INSERT INTO topic_scores (user_id, topic, correct_answers, wrong_answers, mastery_percentage, updated_at)
               VALUES (?, ?, ?, ?, 0, ?)
               ON CONFLICT(user_id, topic) DO UPDATE SET
                 correct_answers = excluded.correct_answers,
                 wrong_answers = excluded.wrong_answers,
                 updated_at = excluded.updated_at""",
            (user_id, topic, correct, wrong, now.isoformat()),
        )
    refresh_mastery(user_id, topic)


def _events_by_topic(user_id: int, topic: str | None = None) -> dict[str, list[tuple[bool, float, datetime]]]:
    sql = "SELECT topic, is_correct, weight, created_at FROM mastery_events WHERE user_id = ?"
    params: list = [user_id]
    if topic:
        sql += " AND topic = ?"
        params.append(topic)
    with get_db() as conn:
        rows = conn.execute(sql + " ORDER BY created_at", params).fetchall()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["topic"], []).append((bool(r["is_correct"]), r["weight"], _parse(r["created_at"])))
    return out


def refresh_mastery(user_id: int, topic: str | None = None):
    """Recompute stored mastery so decay is reflected even without new answers."""
    now = datetime.utcnow()
    by_topic = _events_by_topic(user_id, topic)
    with get_db() as conn:
        for t, events in by_topic.items():
            conn.execute(
                "UPDATE topic_scores SET mastery_percentage = ? WHERE user_id = ? AND topic = ?",
                (compute_mastery(events, now), user_id, t),
            )


def mastery_trend(user_id: int, weeks: int = 8) -> list[dict]:
    """Mastery at the end of each of the last `weeks` weeks, overall and per topic."""
    by_topic = _events_by_topic(user_id)
    today = datetime.utcnow()
    points = []
    for i in range(weeks - 1, -1, -1):
        at = today - timedelta(weeks=i)
        topics = {}
        for t, events in by_topic.items():
            past = [e for e in events if e[2] <= at]
            if past:
                topics[t] = compute_mastery(past, at)
        overall = round(sum(topics.values()) / len(topics), 1) if topics else None
        points.append({"date": at.date().isoformat(), "overall": overall, "topics": topics})
    return points
