from datetime import datetime, timedelta

from database import get_db, row_to_dict
from services.quiz import get_weak_topics


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", ""))


def get_exam_plan(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM exam_plan WHERE user_id = ?", (user_id,)).fetchone()
    return row_to_dict(row)


def save_exam_plan(
    user_id: int,
    exam_start: str,
    exam_end: str,
    expected_cgpa: float,
    current_cgpa: float,
) -> dict:
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO exam_plan (user_id, exam_start, exam_end, expected_cgpa, current_cgpa, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 exam_start = excluded.exam_start,
                 exam_end = excluded.exam_end,
                 expected_cgpa = excluded.expected_cgpa,
                 current_cgpa = excluded.current_cgpa,
                 updated_at = excluded.updated_at""",
            (user_id, exam_start, exam_end, expected_cgpa, current_cgpa, now),
        )
    return get_exam_plan(user_id)


def get_logged_minutes(user_id: int, since: str | None = None) -> int:
    with get_db() as conn:
        if since:
            row = conn.execute(
                "SELECT COALESCE(SUM(minutes), 0) as m FROM study_sessions WHERE user_id = ? AND created_at >= ?",
                (user_id, since),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(minutes), 0) as m FROM study_sessions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
    return int(row["m"])


def log_study_session(user_id: int, minutes: int, topic: str | None = None):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO study_sessions (user_id, minutes, topic, created_at) VALUES (?, ?, ?, ?)",
            (user_id, minutes, topic, now),
        )


def is_in_exam_window(plan: dict | None) -> bool:
    if not plan:
        return False
    now = datetime.utcnow()
    try:
        start = _parse_dt(plan["exam_start"])
        end = _parse_dt(plan["exam_end"])
        return start <= now <= end
    except (ValueError, KeyError):
        return False


def calculate_study_targets(user_id: int) -> dict:
    plan = get_exam_plan(user_id)
    weak = get_weak_topics(user_id, limit=20)

    with get_db() as conn:
        topic_count = conn.execute(
            "SELECT COUNT(DISTINCT topic) as c FROM knowledge_chunks WHERE user_id = ?",
            (user_id,),
        ).fetchone()["c"]

    now = datetime.utcnow()
    in_window = is_in_exam_window(plan)

    if not plan:
        return {
            "has_plan": False,
            "in_exam_window": False,
            "topic_count": topic_count,
            "weak_topic_count": len(weak),
        }

    try:
        start = _parse_dt(plan["exam_start"])
        end = _parse_dt(plan["exam_end"])
    except ValueError:
        return {"has_plan": True, "in_exam_window": False, "error": "Invalid exam dates"}

    if now < start:
        days_left = max(1, (end - start).days + 1)
    elif now > end:
        days_left = 0
    else:
        days_left = max(1, (end - now).days + 1)

    days_until_start = max(0, (start - now).days)
    expected = float(plan.get("expected_cgpa") or 8.0)
    current = float(plan.get("current_cgpa") or 6.0)
    cgpa_gap = max(0.0, expected - current)

    total_hours_needed = round(topic_count * 2 + cgpa_gap * 12 + len(weak) * 2.5 + 8, 1)
    total_hours_needed = max(total_hours_needed, 10.0)

    logged_minutes = get_logged_minutes(user_id, plan["exam_start"])
    hours_logged = round(logged_minutes / 60, 1)
    hours_remaining = max(0.0, round(total_hours_needed - hours_logged, 1))
    hours_per_day = round(hours_remaining / days_left, 1) if days_left > 0 else hours_remaining

    return {
        "has_plan": True,
        "in_exam_window": in_window,
        "exam_start": plan["exam_start"],
        "exam_end": plan["exam_end"],
        "expected_cgpa": expected,
        "current_cgpa": current,
        "days_until_exam_start": days_until_start,
        "days_left": days_left,
        "topic_count": topic_count,
        "weak_topic_count": len(weak),
        "total_hours_needed": total_hours_needed,
        "hours_logged": hours_logged,
        "hours_remaining": hours_remaining,
        "hours_per_day": hours_per_day,
        "weak_topics": [w["topic"] for w in weak[:5]],
    }


def get_study_overview(user_id: int) -> dict:
    with get_db() as conn:
        docs = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT id, filename, title, topic, file_type, page_count, chunk_count FROM documents WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        ]
        chunks = conn.execute(
            """SELECT id, document_id, title, topic, content, source FROM knowledge_chunks
               WHERE user_id = ? ORDER BY topic, id""",
            (user_id,),
        ).fetchall()

    topics_map: dict[str, dict] = {}
    for row in chunks:
        r = dict(row)
        topic = r.get("topic") or "General"
        if topic not in topics_map:
            topics_map[topic] = {
                "topic": topic,
                "chunk_count": 0,
                "sources": set(),
                "materials": [],
            }
        topics_map[topic]["chunk_count"] += 1
        if r.get("source"):
            topics_map[topic]["sources"].add(r["source"])
        preview = (r.get("content") or "")[:280]
        topics_map[topic]["materials"].append(
            {
                "id": r["id"],
                "title": r.get("title"),
                "source": r.get("source"),
                "preview": preview + ("…" if len(r.get("content", "")) > 280 else ""),
            }
        )

    topics = []
    for t in sorted(topics_map.values(), key=lambda x: x["topic"]):
        t["sources"] = sorted(t["sources"])
        topics.append(t)

    return {
        "documents": docs,
        "topics": topics,
        "study_targets": calculate_study_targets(user_id),
    }
