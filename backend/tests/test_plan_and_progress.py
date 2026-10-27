from datetime import date, datetime, timedelta

from database import get_db
from services import daily_plan, progress
from services.study_plan import save_exam_plan
from tests.conftest import add_chunks


def test_empty_library_plan_asks_for_upload(client):
    plan = client.get("/api/plan/today").json()
    assert [t["id"] for t in plan["tasks"]] == ["upload"]


def test_plan_covers_cards_topics_quiz_and_mock_exam(client):
    add_chunks([("Biology", "Cells."), ("Chemistry", "Atoms.")])
    client.post("/api/flashcards", json={"topic": "Biology", "front": "Q", "back": "A"})
    soon = datetime.utcnow() + timedelta(days=5)
    save_exam_plan(1, soon.isoformat(), (soon + timedelta(days=7)).isoformat(), 8.0, 7.0)

    plan = client.get("/api/plan/today").json()
    ids = [t["id"] for t in plan["tasks"]]
    assert ids[:4] == ["flashcards", "study:Biology", "study:Chemistry", "quiz:Biology"]
    assert "mock_exam" in ids
    assert plan["total_minutes"] == sum(t["minutes"] for t in plan["tasks"])


def test_weakest_practised_topic_comes_after_new_ones(db):
    add_chunks([("Strong", "x"), ("Weak", "y"), ("New", "z")])
    from services.mastery import record_event

    record_event(1, "Strong", True)
    record_event(1, "Weak", False)
    assert daily_plan.priority_topics(1) == ["New", "Weak", "Strong"]


def test_toggle_logs_study_time_once_and_regenerate_keeps_ticks(client):
    add_chunks([("Biology", "Cells.")])
    plan = client.get("/api/plan/today").json()
    study = next(t for t in plan["tasks"] if t["kind"] == "study")

    done = client.post(f"/api/plan/tasks/{study['id']}/toggle").json()
    assert done["done_count"] == 1
    client.post(f"/api/plan/tasks/{study['id']}/toggle")  # untick
    client.post(f"/api/plan/tasks/{study['id']}/toggle")  # tick again: no second log
    with get_db() as conn:
        minutes = conn.execute("SELECT SUM(minutes) m FROM study_sessions").fetchone()["m"]
        streak = conn.execute("SELECT study_streak FROM users WHERE id = 1").fetchone()[0]
    assert minutes == study["minutes"] and streak == 1

    regenerated = client.post("/api/plan/today/regenerate").json()
    assert next(t for t in regenerated["tasks"] if t["id"] == study["id"])["done"] is True
    assert client.post("/api/plan/tasks/nope/toggle").status_code == 404


def test_calendar_export_is_valid_ics(client):
    add_chunks([("Biology", "Cells."), ("A very long topic name " * 4, "words")])
    r = client.get("/api/plan/calendar.ics", params={"days": 3, "hour": 7, "minute": 30})
    assert r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert body.count("BEGIN:VEVENT") == 3
    assert f"DTSTART:{date.today().strftime('%Y%m%d')}T073000" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))


def test_level_math():
    assert progress.level_for(0) == 1
    assert progress.level_for(99) == 1
    assert progress.level_for(100) == 2
    assert progress.level_for(300) == 3
    assert progress.level_start(3) == 300


def test_xp_badges_and_goal(client):
    client.post("/api/documents/upload", files={"file": ("bio.txt", b"Cells are small.")})
    for answer in ("2", "3"):
        client.post("/api/quiz/submit", json={
            "topic": "Math", "question_type": "mcq", "difficulty": "easy", "question": "1+1?",
            "options": ["2", "3"], "correct_answer": "2", "user_answer": answer,
        })
    p = client.get("/api/progress").json()
    assert p["xp"] == progress.XP_UPLOAD + progress.XP_CORRECT + progress.XP_WRONG
    assert p["today_xp"] == p["xp"] and p["level"] == 1
    earned = {b["id"]: b for b in p["badges"] if b["earned_at"]}
    assert set(earned) == {"first_upload", "first_answer"}
    assert all(b["new"] for b in earned.values())

    client.post("/api/progress/badges/seen")
    assert not any(b["new"] for b in client.get("/api/progress").json()["badges"])

    assert client.put("/api/progress/goal", json={"daily_goal": 20}).json()["daily_goal"] == 20
    assert client.put("/api/progress/goal", json={"daily_goal": 1}).status_code == 422


def test_longest_streak():
    days = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06"]
    assert progress._longest_streak(days) == 3
