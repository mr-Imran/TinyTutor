"""Gamification: XP, levels, a daily XP goal and badges, all derived from study activity.

XP is recomputed from existing records (answers, reviews, uploads, exams, plan tasks), so it
can never drift out of sync. Badges are stored when first earned so they can be announced once.
"""
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from database import get_db
from services.settings_store import get_setting, set_setting

XP_CORRECT = 10
XP_WRONG = 4  # effort still counts
XP_FLASHCARD = 3
XP_UPLOAD = 15
XP_MOCK_EXAM = 25
XP_MOCK_EXAM_HIGH_SCORE = 25  # bonus at 80% or more
XP_PLAN_TASK = 20
XP_PLAN_COMPLETE = 30
LEVEL_STEP = 100  # level n starts at LEVEL_STEP * n * (n - 1) / 2 XP
DEFAULT_DAILY_GOAL = 100


def level_for(xp: int) -> int:
    return int((1 + math.sqrt(1 + 8 * xp / LEVEL_STEP)) // 2)


def level_start(level: int) -> int:
    return LEVEL_STEP * level * (level - 1) // 2


def _day(ts: str) -> str:
    return ts[:10]


def xp_by_day(user_id: int) -> dict[str, int]:
    days: dict[str, int] = defaultdict(int)
    with get_db() as conn:
        for r in conn.execute(
            "SELECT source, is_correct, created_at FROM mastery_events WHERE user_id = ?", (user_id,)
        ):
            if r["source"] == "flashcard":
                days[_day(r["created_at"])] += XP_FLASHCARD
            else:
                days[_day(r["created_at"])] += XP_CORRECT if r["is_correct"] else XP_WRONG
        # Notes written in the app are not uploads: saving an empty note should not earn XP.
        for r in conn.execute("SELECT created_at FROM documents WHERE user_id = ? AND file_type != 'note'", (user_id,)):
            days[_day(r["created_at"])] += XP_UPLOAD
        for r in conn.execute(
            "SELECT submitted_at, score, total FROM mock_exams WHERE user_id = ? AND status = 'submitted'", (user_id,)
        ):
            bonus = XP_MOCK_EXAM_HIGH_SCORE if r["total"] and r["score"] / r["total"] >= 0.8 else 0
            days[_day(r["submitted_at"])] += XP_MOCK_EXAM + bonus
        for r in conn.execute("SELECT plan_date, tasks_json FROM daily_plans WHERE user_id = ?", (user_id,)):
            tasks = json.loads(r["tasks_json"])
            done = sum(1 for t in tasks if t.get("done"))
            days[r["plan_date"]] += done * XP_PLAN_TASK + (XP_PLAN_COMPLETE if tasks and done == len(tasks) else 0)
    return dict(days)


def _longest_streak(active_days: list[str]) -> int:
    best = run = 0
    prev = None
    for d in sorted(set(active_days)):
        cur = date.fromisoformat(d)
        run = run + 1 if prev and cur - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = cur
    return best


def gather_stats(user_id: int) -> dict:
    by_day = xp_by_day(user_id)
    goal = daily_goal(user_id)
    with get_db() as conn:
        one = lambda sql: conn.execute(sql, (user_id,)).fetchone()[0] or 0  # noqa: E731
        stats = {
            "documents": one("SELECT COUNT(*) FROM documents WHERE user_id = ? AND file_type != 'note'"),
            "answers": one("SELECT COUNT(*) FROM mastery_events WHERE user_id = ? AND source != 'flashcard'"),
            "reviews": one("SELECT COUNT(*) FROM mastery_events WHERE user_id = ? AND source = 'flashcard'"),
            "mock_exams": one("SELECT COUNT(*) FROM mock_exams WHERE user_id = ? AND status = 'submitted'"),
            "best_mock": one(
                """SELECT MAX(CAST(score AS REAL) / total) FROM mock_exams
                   WHERE user_id = ? AND status = 'submitted' AND total > 0"""
            ),
            "best_mastery": one(
                """SELECT MAX(mastery_percentage) FROM topic_scores
                   WHERE user_id = ? AND correct_answers + wrong_answers >= 5"""
            ),
            "current_streak": one("SELECT study_streak FROM users WHERE id = ?"),
            "plans_completed": sum(
                1 for r in conn.execute("SELECT tasks_json FROM daily_plans WHERE user_id = ?", (user_id,))
                if (tasks := json.loads(r["tasks_json"])) and all(t.get("done") for t in tasks)
            ),
        }
    stats["longest_streak"] = max(_longest_streak([d for d, xp in by_day.items() if xp > 0]), stats["current_streak"])
    stats["goal_days"] = sum(1 for xp in by_day.values() if xp >= goal)
    stats["xp"] = sum(by_day.values())
    stats["by_day"] = by_day
    return stats


@dataclass(frozen=True)
class Badge:
    id: str
    name: str
    description: str
    icon: str
    earned: Callable[[dict], bool]


BADGES = [
    Badge("first_upload", "Bookworm", "Upload your first study material", "book", lambda s: s["documents"] >= 1),
    Badge("library_10", "Librarian", "Build a library of 10 materials", "library", lambda s: s["documents"] >= 10),
    Badge("first_answer", "First Step", "Answer your first practice question", "sparkles", lambda s: s["answers"] >= 1),
    Badge("answers_100", "Century", "Answer 100 practice questions", "target", lambda s: s["answers"] >= 100),
    Badge("reviews_50", "Card Shark", "Review 50 flashcards", "layers", lambda s: s["reviews"] >= 50),
    Badge("reviews_500", "Memory Palace", "Review 500 flashcards", "brain", lambda s: s["reviews"] >= 500),
    Badge("streak_3", "Warming Up", "Study 3 days in a row", "flame", lambda s: s["longest_streak"] >= 3),
    Badge("streak_7", "On Fire", "Study 7 days in a row", "flame", lambda s: s["longest_streak"] >= 7),
    Badge("streak_30", "Unstoppable", "Study 30 days in a row", "flame", lambda s: s["longest_streak"] >= 30),
    Badge("mastery_80", "Topic Master", "Reach 80% mastery in a topic (5+ answers)", "trophy",
          lambda s: s["best_mastery"] >= 80),
    Badge("mock_first", "Exam Ready", "Finish your first mock exam", "timer", lambda s: s["mock_exams"] >= 1),
    Badge("mock_90", "Top Marks", "Score 90% or more on a mock exam", "medal", lambda s: s["best_mock"] >= 0.9),
    Badge("plan_complete", "Planner", "Finish every task in a daily plan", "check", lambda s: s["plans_completed"] >= 1),
    Badge("goal_7", "Goal Getter", "Hit your daily XP goal on 7 days", "star", lambda s: s["goal_days"] >= 7),
]


def daily_goal(user_id: int) -> int:
    try:
        return int(get_setting(f"daily_xp_goal_{user_id}", str(DEFAULT_DAILY_GOAL)))
    except ValueError:
        return DEFAULT_DAILY_GOAL


def set_daily_goal(user_id: int, goal: int):
    set_setting(f"daily_xp_goal_{user_id}", str(goal))


def _sync_badges(user_id: int, stats: dict) -> dict[str, dict]:
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        stored = {r["badge_id"]: dict(r) for r in conn.execute("SELECT * FROM badges WHERE user_id = ?", (user_id,))}
        for badge in BADGES:
            if badge.id not in stored and badge.earned(stats):
                conn.execute(
                    "INSERT INTO badges (user_id, badge_id, earned_at, seen) VALUES (?, ?, ?, 0)",
                    (user_id, badge.id, now),
                )
                stored[badge.id] = {"badge_id": badge.id, "earned_at": now, "seen": 0}
    return stored


def get_progress(user_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    stats = gather_stats(user_id)
    stored = _sync_badges(user_id, stats)
    xp = stats["xp"]
    level = level_for(xp)
    start, nxt = level_start(level), level_start(level + 1)
    goal = daily_goal(user_id)
    week = [
        {"date": d, "xp": stats["by_day"].get(d, 0)}
        for d in ((today - timedelta(days=i)).isoformat() for i in range(6, -1, -1))
    ]
    badges = [
        {
            "id": b.id, "name": b.name, "description": b.description, "icon": b.icon,
            "earned_at": stored.get(b.id, {}).get("earned_at"),
            "new": b.id in stored and not stored[b.id]["seen"],
        }
        for b in BADGES
    ]
    return {
        "xp": xp,
        "level": level,
        "level_xp": xp - start,
        "level_size": nxt - start,
        "today_xp": stats["by_day"].get(today.isoformat(), 0),
        "daily_goal": goal,
        "week": week,
        "current_streak": stats["current_streak"],
        "longest_streak": stats["longest_streak"],
        "badges": badges,
        "earned_count": sum(1 for b in badges if b["earned_at"]),
    }


def mark_badges_seen(user_id: int):
    with get_db() as conn:
        conn.execute("UPDATE badges SET seen = 1 WHERE user_id = ?", (user_id,))
