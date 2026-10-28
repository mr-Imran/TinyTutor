import database
from services import misconceptions
from services.quiz import record_quiz_attempt
from tests.conftest import add_chunks


# ---------------------------------------------------------------- rubric grading

def test_essay_grading_makes_rubric_and_clamps_scores(client):
    add_chunks([("Photosynthesis", "Photosynthesis turns light, water and CO2 into sugar.")])
    data = client.post("/api/grading/essay", json={
        "question": "Explain photosynthesis.", "answer": "Plants use light to make sugar.", "topic": "Photosynthesis",
    }).json()
    assert [c["name"] for c in data["rubric"]] == ["Definition", "Inputs"]
    inputs = data["criteria"][1]
    assert inputs["score"] == 3 and inputs["max"] == 3  # the AI's 9/3 is clamped
    assert data["score"] == 5 and data["max_score"] == 5 and data["percentage"] == 100.0
    assert data["sources"][0]["n"] == 1

    history = client.get("/api/grading/history?kind=essay").json()
    assert history[0]["id"] == data["id"] and history[0]["score"] == 5
    with database.get_db() as conn:
        event = conn.execute("SELECT * FROM mastery_events ORDER BY id DESC LIMIT 1").fetchone()
    assert event["source"] == "essay" and event["is_correct"] == 1


def test_essay_grading_uses_given_rubric(client, fake_llm):
    rubric = [{"name": "Inputs", "description": "Light, water, CO2", "points": 4}]
    data = client.post("/api/grading/essay", json={
        "question": "What goes into photosynthesis?", "answer": "Light.", "rubric": rubric,
    }).json()
    assert data["rubric"] == rubric
    assert not any("marking rubrics" in c.get("system", "") for c in fake_llm.calls)
    assert data["criteria"][0]["max"] == 4


def test_photo_answer_is_transcribed_then_graded(client):
    resp = client.post(
        "/api/grading/essay/photo",
        files={"file": ("answer.png", b"\x89PNG fake", "image/png")},
        data={"question": "What is the powerhouse of the cell?"},
    )
    data = resp.json()
    assert "mitochondria" in data["transcription"]
    assert data["max_score"] == 5


def test_photo_answer_rejects_non_images(client):
    resp = client.post("/api/grading/essay/photo", files={"file": ("a.pdf", b"%PDF", "application/pdf")},
                       data={"question": "Q?"})
    assert resp.status_code == 400


def test_teach_back(client):
    data = client.post("/api/grading/teach-back", json={
        "concept": "Photosynthesis", "explanation": "Plants eat sunlight to make food.",
    }).json()
    assert data["score"] == 82 and data["jargon"][0]["term"] == "ATP"
    assert data["follow_up_question"] == "Why are leaves green?"
    assert client.get("/api/grading/history?kind=teach_back").json()[0]["result"]["score"] == 82


# ---------------------------------------------------------------- misconceptions

def _wrong(question, answer="Mitosis", correct="Meiosis", topic="Cells"):
    return record_quiz_attempt(1, topic, "mcq", "medium", question, ["Mitosis", "Meiosis"], correct, answer, False)


def test_too_few_mistakes_gives_message(client):
    _wrong("Which division makes gametes?")
    data = client.post("/api/misconceptions/analyze").json()
    assert data["created"] == [] and "at least" in data["message"]


def test_analyze_groups_mistakes_and_drill_resolves(client):
    for q in ("Which division makes gametes?", "Which division makes sperm cells?", "Which division makes egg cells?"):
        _wrong(q)
    _wrong("What colour is chlorophyll?", answer="Red", correct="Green", topic="Plants")

    data = client.post("/api/misconceptions/analyze").json()
    assert len(data["created"]) == 1
    item = data["misconceptions"][0]
    assert item["title"] == "Confuses mitosis with meiosis" and item["evidence"] == 3
    # The lone plant mistake stays pending so it can join a later pattern.
    assert data["pending"] == 1

    # Analysing again does not re-create the same misconception.
    assert client.post("/api/misconceptions/analyze").json()["created"] == []

    mid = item["id"]
    drill = client.post(f"/api/misconceptions/{mid}/drill").json()["drill"]
    assert len(drill["questions"]) == 3 and "correct_answer" not in drill["questions"][0]

    wrong = client.post(f"/api/misconceptions/{mid}/answer", json={"index": 0, "answer": "Mitosis"}).json()
    assert not wrong["is_correct"] and wrong["streak"] == 0
    assert client.post(f"/api/misconceptions/{mid}/answer", json={"index": 0, "answer": "x"}).status_code == 400

    client.post(f"/api/misconceptions/{mid}/drill")
    for i in range(3):
        result = client.post(f"/api/misconceptions/{mid}/answer", json={"index": i, "answer": "Meiosis"}).json()
    assert result["status"] == "resolved"
    # The wrong drill answer was filed under this misconception, not left pending.
    assert misconceptions.pending_count(1) == 1


def test_open_misconception_appears_in_daily_plan(client):
    for q in ("Which division makes gametes?", "Which division makes sperm cells?", "Which division makes egg cells?"):
        _wrong(q)
    add_chunks([("Cells", "Meiosis makes gametes.")])
    client.post("/api/misconceptions/analyze")
    tasks = client.post("/api/plan/today/regenerate").json()["tasks"]
    assert any(t["kind"] == "misconception" for t in tasks)


def test_agent_can_read_misconceptions(client, fake_llm):
    import json

    for q in ("Which division makes gametes?", "Which division makes sperm cells?", "Which division makes egg cells?"):
        _wrong(q)
    client.post("/api/misconceptions/analyze")
    fake_llm.tool_script = [("", [("get_misconceptions", {})]), ("You mix up mitosis and meiosis.", [])]
    client.post("/api/chat/agent", json={"message": "what do I get wrong?"})
    tool_msg = next(m for m in fake_llm.calls[-1]["messages"] if m["role"] == "tool")
    assert json.loads(tool_msg["content"])["misconceptions"][0]["title"] == "Confuses mitosis with meiosis"
