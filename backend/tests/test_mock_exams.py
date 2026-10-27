from services.mock_exams import build_report, plan_questions
from tests.conftest import add_chunks


def test_plan_round_robins_topics_and_types():
    plan = plan_questions(["A", "B"], 4, ["mcq", "short_answer", "bogus"])
    assert plan == [("A", "mcq"), ("B", "short_answer"), ("A", "mcq"), ("B", "short_answer")]


def test_report_sorts_weakest_first():
    graded = [
        {"topic": "A", "is_correct": True},
        {"topic": "A", "is_correct": True},
        {"topic": "B", "is_correct": False},
    ]
    report = build_report(graded)
    assert report["percentage"] == 66.7
    assert report["weakest_topic"] == "B"


def test_exam_hides_answers_until_submitted(client, fake_llm):
    add_chunks([("Biology", "Plants make sugar using chlorophyll.")])
    exam = client.post("/api/mock-exams", json={"topics": ["Biology"], "count": 3, "duration_minutes": 10}).json()
    assert exam["status"] == "in_progress" and exam["total"] == 3
    assert [q["question_type"] for q in exam["questions"]] == ["mcq", "true_false", "short_answer"]
    assert all("correct_answer" not in q for q in exam["questions"])

    q = exam["questions"]
    fake_llm.grade_correct = False
    answers = {str(q[0]["id"]): "Sugar", str(q[1]["id"]): "False", str(q[2]["id"]): "Something else"}
    done = client.post(f"/api/mock-exams/{exam['id']}/submit", json={"answers": answers}).json()
    assert done["status"] == "submitted" and done["late"] == 0
    assert done["score"] == 1
    assert [x["is_correct"] for x in done["questions"]] == [1, 0, 0]
    assert done["questions"][0]["correct_answer"] == "Sugar"
    assert done["report"]["topics"][0]["topic"] == "Biology"

    # Resubmitting does not regrade or record attempts twice.
    again = client.post(f"/api/mock-exams/{exam['id']}/submit", json={"answers": {}}).json()
    assert again["score"] == 1
    assert len(client.get("/api/quiz/history").json()) == 3

    listing = client.get("/api/mock-exams").json()
    assert listing[0]["id"] == exam["id"] and listing[0]["topics"] == ["Biology"]


def test_unanswered_questions_are_wrong(client):
    add_chunks([("Biology", "Cells.")])
    exam = client.post("/api/mock-exams", json={"topics": ["Biology"], "count": 2, "mix": ["mcq"]}).json()
    done = client.post(f"/api/mock-exams/{exam['id']}/submit", json={"answers": {}}).json()
    assert done["score"] == 0
    assert "Not answered" in done["questions"][0]["feedback"]
