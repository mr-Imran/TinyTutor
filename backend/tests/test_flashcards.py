from database import get_db
from services.flashcards import sm2
from tests.conftest import add_chunks


def test_sm2_progression_and_lapse():
    ease, interval, reps = sm2(2.5, 0, 0, 4)
    assert (interval, reps) == (1, 1)
    ease, interval, reps = sm2(ease, interval, reps, 4)
    assert (interval, reps) == (6, 2)
    ease, interval, reps = sm2(ease, interval, reps, 5)
    assert interval == round(6 * 2.5) and reps == 3
    ease, interval, reps = sm2(ease, interval, reps, 1)
    assert (interval, reps) == (0, 0)
    assert ease >= 1.3


def test_ease_never_below_minimum():
    ease = 2.5
    for _ in range(20):
        ease, _, _ = sm2(ease, 1, 1, 0)
    assert ease == 1.3


def test_generate_review_flow(client, db):
    add_chunks([("Biology", "ATP is the energy currency. Photosynthesis happens in chloroplasts.")])
    created = client.post("/api/flashcards/generate", json={"topic": "Biology", "count": 5}).json()["created"]
    assert len(created) == 2  # duplicate front skipped

    due = client.get("/api/flashcards/due").json()
    assert len(due) == 2

    card = client.post(f"/api/flashcards/{due[0]['id']}/review", json={"grade": 4}).json()
    assert card["interval_days"] == 1 and card["repetitions"] == 1
    assert len(client.get("/api/flashcards/due").json()) == 1

    stats = client.get("/api/flashcards/stats").json()
    assert stats["total"] == 2 and stats["due"] == 1
    with get_db() as conn:
        events = conn.execute("SELECT source, is_correct FROM mastery_events").fetchall()
    assert [(e["source"], e["is_correct"]) for e in events] == [("flashcard", 1)]


def test_generate_without_material_is_400(client):
    r = client.post("/api/flashcards/generate", json={"topic": "Nothing"})
    assert r.status_code == 400
