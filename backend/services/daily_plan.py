"""Adaptive daily study plan, built from weak topics, due flashcards, mock exams and the exam date.

Plans are deterministic (no AI call), stored per day, and keep their ticked-off tasks when rebuilt.
"""
import json
import math
from datetime import date, datetime, timedelta

from database import get_db
from services.flashcards import flashcard_stats
from services.mastery import refresh_mastery
from services.quiz import touch_study_streak
from services.study_plan import calculate_study_targets, log_study_session

DEFAULT_STUDY_MINUTES = 45
MAX_STUDY_MINUTES = 240
FOCUS_TOPICS = 2
MOCK_EXAM_LEAD_DAYS = 14
MOCK_EXAM_GAP_DAYS = 5
NEW_MATERIAL_DAYS = 3


def priority_topics(user_id: int) -> list[str]:
    """Never-practised topics first (in upload order), then lowest mastery."""
    refresh_mastery(user_id)
    with get_db() as conn:
        all_topics = [
            r["topic"]
            for r in conn.execute(
                """SELECT topic, MIN(id) first_id FROM knowledge_chunks
                   WHERE user_id = ? AND topic IS NOT NULL GROUP BY topic ORDER BY first_id""",
                (user_id,),
            ).fetchall()
        ]
        scored = {
            r["topic"]: r["mastery_percentage"]
            for r in conn.execute("SELECT topic, mastery_percentage FROM topic_scores WHERE user_id = ?", (user_id,))
        }
    fresh = [t for t in all_topics if t not in scored]
    practised = sorted((t for t in all_topics if t in scored), key=lambda t: scored[t])
    return fresh + practised


def _study_minutes(targets: dict) -> int:
    hours = targets.get("hours_per_day") if targets.get("has_plan") else None
    if hours:
        return int(min(max(hours * 60, 15), MAX_STUDY_MINUTES))
    return DEFAULT_STUDY_MINUTES


def build_tasks(user_id: int, today: date) -> list[dict]:
    targets = calculate_study_targets(user_id)
    topics = priority_topics(user_id)
    tasks: list[dict] = []

    with get_db() as conn:
        doc_count = conn.execute("SELECT COUNT(*) c FROM documents WHERE user_id = ?", (user_id,)).fetchone()["c"]
        recent_docs = conn.execute(
            """SELECT id, title FROM documents WHERE user_id = ? AND created_at >= ? AND summary IS NOT NULL
               ORDER BY created_at DESC LIMIT 2""",
            (user_id, (today - timedelta(days=NEW_MATERIAL_DAYS)).isoformat()),
        ).fetchall()
        last_mock = conn.execute(
            "SELECT MAX(started_at) m FROM mock_exams WHERE user_id = ?", (user_id,)
        ).fetchone()["m"]

    if doc_count == 0:
        return [{
            "id": "upload", "kind": "upload", "title": "Upload your first study material",
            "detail": "Add a PDF, slides, notes, or a web/YouTube link to get a personalised plan.",
            "minutes": 5, "link": "/upload", "done": False,
        }]

    due = flashcard_stats(user_id)["due"]
    if due:
        tasks.append({
            "id": "flashcards", "kind": "flashcards", "title": f"Review {due} due flashcard{'s' if due != 1 else ''}",
            "detail": "Spaced repetition works best when you clear the queue every day.",
            "minutes": min(max(math.ceil(due * 0.4), 5), 30), "link": "/flashcards", "done": False,
        })

    budget = _study_minutes(targets)
    focus = topics[:FOCUS_TOPICS]
    for topic in focus:
        tasks.append({
            "id": f"study:{topic}", "kind": "study", "topic": topic, "title": f"Study {topic}",
            "detail": "Read through the material, then ask the AI Tutor about anything unclear.",
            "minutes": max(10, budget // max(len(focus), 1)), "link": "/tutor", "done": False,
        })

    if topics:
        tasks.append({
            "id": f"quiz:{topics[0]}", "kind": "quiz", "topic": topics[0], "title": f"Quiz yourself on {topics[0]}",
            "detail": "Five questions to check what stuck.", "minutes": 10, "link": "/quiz", "done": False,
        })

    days_to_exam = targets.get("days_until_exam_start")
    exam_soon = targets.get("has_plan") and (
        targets.get("in_exam_window") or (days_to_exam is not None and days_to_exam <= MOCK_EXAM_LEAD_DAYS)
    )
    recent_mock = last_mock and datetime.fromisoformat(last_mock).date() > today - timedelta(days=MOCK_EXAM_GAP_DAYS)
    if exam_soon and not recent_mock:
        tasks.append({
            "id": "mock_exam", "kind": "mock_exam", "title": "Take a timed mock exam",
            "detail": "Practise under exam conditions; the report shows what to review next.",
            "minutes": 20, "link": "/mock-exam", "done": False,
        })

    for d in recent_docs:
        tasks.append({
            "id": f"read:{d['id']}", "kind": "read", "title": f"Read the summary of {d['title']}",
            "detail": "Skim the summary and concept map of your newest material.",
            "minutes": 5, "link": "/upload", "done": False,
        })
    return tasks


def _save(user_id: int, day: date, tasks: list[dict]):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO daily_plans (user_id, plan_date, tasks_json, created_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, plan_date) DO UPDATE SET tasks_json = excluded.tasks_json""",
            (user_id, day.isoformat(), json.dumps(tasks), datetime.utcnow().isoformat()),
        )


def _load(user_id: int, day: date) -> list[dict] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT tasks_json FROM daily_plans WHERE user_id = ? AND plan_date = ?", (user_id, day.isoformat())
        ).fetchone()
    return json.loads(row["tasks_json"]) if row else None


def _plan_out(day: date, tasks: list[dict]) -> dict:
    return {
        "date": day.isoformat(),
        "tasks": tasks,
        "total_minutes": sum(t["minutes"] for t in tasks),
        "done_count": sum(1 for t in tasks if t["done"]),
        "complete": bool(tasks) and all(t["done"] for t in tasks),
    }


def get_plan(user_id: int, day: date | None = None) -> dict:
    day = day or date.today()
    tasks = _load(user_id, day)
    if tasks is None:
        tasks = build_tasks(user_id, day)
        _save(user_id, day, tasks)
    return _plan_out(day, tasks)


def regenerate(user_id: int, day: date | None = None) -> dict:
    """Rebuild today's plan; tasks that still apply keep their ticks, finished extras stay listed."""
    day = day or date.today()
    old = {t["id"]: t for t in _load(user_id, day) or []}
    fresh = build_tasks(user_id, day)
    fresh_ids = {t["id"] for t in fresh}
    for t in fresh:
        if t["id"] in old:
            t["done"] = old[t["id"]]["done"]
            t["logged"] = old[t["id"]].get("logged", False)
    fresh += [t for tid, t in old.items() if tid not in fresh_ids and t["done"]]
    _save(user_id, day, fresh)
    return _plan_out(day, fresh)


def toggle_task(user_id: int, task_id: str, day: date | None = None) -> dict | None:
    day = day or date.today()
    tasks = _load(user_id, day)
    if tasks is None:
        return None
    task = next((t for t in tasks if t["id"] == task_id), None)
    if task is None:
        return None
    task["done"] = not task["done"]
    if task["done"]:
        task["completed_at"] = datetime.utcnow().isoformat()
        touch_study_streak(user_id)
        # Study time counts toward the exam-plan hours, once per task.
        if task["kind"] == "study" and not task.get("logged"):
            log_study_session(user_id, task["minutes"], task.get("topic"))
            task["logged"] = True
    else:
        task.pop("completed_at", None)
    _save(user_id, day, tasks)
    return _plan_out(day, tasks)


# ---------------------------------------------------------------- calendar export

def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 lines are at most 75 octets; continuation lines start with a space."""
    out, current = [], ""
    for ch in line:
        if len((current + ch).encode()) > 75:
            out.append(current)
            current = " " + ch
        else:
            current += ch
    out.append(current)
    return "\r\n".join(out)


def calendar_ics(user_id: int, days: int = 7, hour: int = 18, minute: int = 0, start: date | None = None) -> str:
    """Recurring-style study sessions as individual events, ending at the exam if one is set."""
    start = start or date.today()
    targets = calculate_study_targets(user_id)
    topics = priority_topics(user_id) or ["your materials"]
    minutes = _study_minutes(targets)
    end = start + timedelta(days=days - 1)
    if targets.get("has_plan") and targets.get("exam_end"):
        exam_end = datetime.fromisoformat(targets["exam_end"].replace("Z", "")).date()
        end = min(end, exam_end)

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TinyTutor//Study Plan//EN", "CALSCALE:GREGORIAN"]
    day, i = start, 0
    while day <= end:
        focus = [topics[(i + k) % len(topics)] for k in range(min(FOCUS_TOPICS, len(topics)))]
        begin = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
        finish = begin + timedelta(minutes=minutes)
        lines += [
            "BEGIN:VEVENT",
            f"UID:tinytutor-study-{day.isoformat()}@tinytutor.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{begin.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{finish.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_ics_escape('Study: ' + ', '.join(focus))}",
            f"DESCRIPTION:{_ics_escape('Focus topics: ' + ', '.join(focus) + '. Open TinyTutor for today' + chr(39) + 's full plan.')}",
            "BEGIN:VALARM", "TRIGGER:-PT10M", "ACTION:DISPLAY", "DESCRIPTION:Study session soon", "END:VALARM",
            "END:VEVENT",
        ]
        day += timedelta(days=1)
        i += 1
    if targets.get("has_plan") and targets.get("exam_start"):
        exam_start = datetime.fromisoformat(targets["exam_start"].replace("Z", "")).date()
        exam_end = datetime.fromisoformat(targets["exam_end"].replace("Z", "")).date()
        lines += [
            "BEGIN:VEVENT",
            "UID:tinytutor-exam-period@tinytutor.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{exam_start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(exam_end + timedelta(days=1)).strftime('%Y%m%d')}",
            "SUMMARY:Exam period",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
