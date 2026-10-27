from datetime import datetime, timedelta

from database import get_db
from services.mastery import compute_mastery, mastery_trend, record_event

NOW = datetime(2026, 1, 31)


def test_prior_keeps_single_answer_away_from_extremes():
    assert compute_mastery([], NOW) == 50.0
    assert compute_mastery([(True, 1.0, NOW)], NOW) == 75.0
    assert compute_mastery([(False, 1.0, NOW)], NOW) == 25.0


def test_recent_answers_outweigh_old_ones():
    old_wrong_new_right = [(False, 1.0, NOW - timedelta(days=60))] * 3 + [(True, 1.0, NOW)] * 3
    old_right_new_wrong = [(True, 1.0, NOW - timedelta(days=60))] * 3 + [(False, 1.0, NOW)] * 3
    assert compute_mastery(old_wrong_new_right, NOW) > 70
    assert compute_mastery(old_right_new_wrong, NOW) < 30


def test_hard_questions_count_more():
    easy = compute_mastery([(True, 0.8, NOW), (False, 1.0, NOW)], NOW)
    hard = compute_mastery([(True, 1.25, NOW), (False, 1.0, NOW)], NOW)
    assert hard > easy


def test_record_event_updates_topic_scores_and_trend(db):
    record_event(1, "Biology", True, "hard")
    record_event(1, "Biology", False, "easy")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM topic_scores WHERE topic = 'Biology'").fetchone()
    assert (row["correct_answers"], row["wrong_answers"]) == (1, 1)
    assert 50 < row["mastery_percentage"] < 60

    trend = mastery_trend(1, weeks=4)
    assert len(trend) == 4
    assert trend[-1]["overall"] == row["mastery_percentage"]
    assert trend[0]["overall"] is None
