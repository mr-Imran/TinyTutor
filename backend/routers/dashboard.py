from datetime import datetime, timedelta

from fastapi import APIRouter

from database import get_db, row_to_dict
from services.quiz import get_strong_topics, get_weak_topics
from services.study_plan import calculate_study_targets

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

USER_ID = 1


@router.get("")
def dashboard():
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (USER_ID,)).fetchone())
        doc_count = conn.execute(
            "SELECT COUNT(*) as c FROM documents WHERE user_id = ?", (USER_ID,)
        ).fetchone()["c"]
        quiz_count = conn.execute(
            "SELECT COUNT(*) as c FROM quiz_attempts WHERE user_id = ?", (USER_ID,)
        ).fetchone()["c"]
        chunk_count = conn.execute(
            "SELECT COUNT(*) as c FROM knowledge_chunks WHERE user_id = ?", (USER_ID,)
        ).fetchone()["c"]

    weak = get_weak_topics(USER_ID)
    strong = get_strong_topics(USER_ID)

    # Readiness = average mastery across topics (or 0)
    with get_db() as conn:
        scores = conn.execute(
            "SELECT mastery_percentage FROM topic_scores WHERE user_id = ?", (USER_ID,)
        ).fetchall()
    if scores:
        readiness = round(sum(s["mastery_percentage"] for s in scores) / len(scores), 1)
    else:
        readiness = 0.0

    return {
        "user": user,
        "study_streak": user.get("study_streak", 0) if user else 0,
        "total_documents": doc_count,
        "total_quizzes": quiz_count,
        "total_chunks": chunk_count,
        "weak_topics": weak,
        "strong_topics": strong,
        "readiness_score": readiness,
        "study_targets": calculate_study_targets(USER_ID),
    }


@router.get("/analytics")
def analytics():
    with get_db() as conn:
        topic_scores = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT topic, correct_answers, wrong_answers, mastery_percentage, updated_at FROM topic_scores WHERE user_id = ?",
                (USER_ID,),
            ).fetchall()
        ]
        quiz_history = [
            row_to_dict(r)
            for r in conn.execute(
                """SELECT topic, is_correct, created_at FROM quiz_attempts
                   WHERE user_id = ? ORDER BY created_at DESC LIMIT 100""",
                (USER_ID,),
            ).fetchall()
        ]

    # Activity by day (last 14 days)
    activity = {}
    for i in range(14):
        day = (datetime.utcnow() - timedelta(days=i)).date().isoformat()
        activity[day] = 0
    for q in quiz_history:
        day = (q.get("created_at") or "")[:10]
        if day in activity:
            activity[day] += 1

    return {
        "topic_scores": topic_scores,
        "quiz_history": quiz_history,
        "activity": [{"date": k, "count": activity[k]} for k in sorted(activity.keys())],
        "weak_topics": get_weak_topics(USER_ID, 10),
    }


@router.get("/notifications")
def notifications():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM scheduled_questions WHERE user_id = ? AND is_read = 0
               ORDER BY created_at DESC LIMIT 20""",
            (USER_ID,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.post("/notifications/{notif_id}/read")
def mark_read(notif_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE scheduled_questions SET is_read = 1 WHERE id = ? AND user_id = ?",
            (notif_id, USER_ID),
        )
    return {"ok": True}
