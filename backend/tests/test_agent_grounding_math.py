import asyncio
import json

import pytest

from services import grounding, llm, math_check
from services.text_style import humanize_text
from tests.conftest import add_chunks


def _events(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


# ---------------------------------------------------------------- agent

def test_agent_searches_cites_and_creates_cards(client, fake_llm):
    add_chunks([("Photosynthesis", "Photosynthesis turns light, water and carbon dioxide into sugar.")])
    fake_llm.tool_script = [
        ("", [("search_notes", {"query": "photosynthesis"})]),
        ("", [("create_flashcards", {"topic": "Photosynthesis", "count": 2})]),
        ("Plants make sugar from light [1]. I made 2 flashcards for you.", []),
    ]
    resp = client.post("/api/chat/agent", json={"message": "Explain photosynthesis and make cards"})
    assert resp.status_code == 200
    events = _events(resp)
    kinds = [e["type"] for e in events]
    assert kinds.count("tool") == 2
    card = next(e["card"] for e in events if e["type"] == "card")
    assert card["type"] == "flashcards" and card["count"] == 2
    final = next(e for e in events if e["type"] == "text")
    assert "[1]" in final["text"]
    done = events[-1]
    assert done["type"] == "done" and done["sources"][0]["n"] == 1

    # The tool result the model saw carries the citation number of the note.
    tool_msg = next(m for m in fake_llm.calls[-1]["messages"] if m["role"] == "tool")
    assert "[1] Topic: Photosynthesis" in json.loads(tool_msg["content"])["notes"]

    session_id = int(resp.headers["X-Session-Id"])
    messages = client.get(f"/api/chat/sessions/{session_id}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["cards"][0]["type"] == "flashcards"
    assert client.get("/api/flashcards/stats").json()["total"] == 2


def test_agent_quiz_answers_go_to_ui_not_model(client, fake_llm):
    add_chunks([("Photosynthesis", "Plants make sugar.")])
    fake_llm.tool_script = [("", [("create_quiz", {"topic": "Photosynthesis", "count": 2})]), ("Here is a quiz.", [])]
    events = _events(client.post("/api/chat/agent", json={"message": "quiz me"}))
    quiz = next(e["card"] for e in events if e["type"] == "card")
    assert len(quiz["questions"]) == 2 and quiz["questions"][0]["correct_answer"]
    tool_msg = next(m for m in fake_llm.calls[-1]["messages"] if m["role"] == "tool")
    assert "correct_answer" not in tool_msg["content"]


def test_agent_stops_after_max_steps(client, fake_llm):
    from services import agent

    fake_llm.tool_script = [("", [("get_mastery", {})])]
    events = _events(client.post("/api/chat/agent", json={"message": "loop forever"}))
    assert sum(e["type"] == "tool" for e in events) == agent.MAX_STEPS
    assert fake_llm.calls[-1]["allow_calls"] is False
    assert next(e for e in events if e["type"] == "text")["text"] == "Out of steps."


def test_agent_falls_back_without_tool_support(client, fake_llm):
    add_chunks([("Photosynthesis", "Photosynthesis makes sugar from light.")])
    fake_llm.tools_supported = False
    events = _events(client.post("/api/chat/agent", json={"message": "What is photosynthesis?"}))
    assert events[0]["type"] == "notice"
    assert "".join(e["text"] for e in events if e["type"] == "delta").startswith("Photosynthesis")


def test_agent_unknown_tool_and_bad_args_are_reported_to_model(client, fake_llm):
    fake_llm.tool_script = [("", [("delete_everything", {}), ("create_flashcards", {})]), ("Sorry.", [])]
    _events(client.post("/api/chat/agent", json={"message": "hi"}))
    results = [json.loads(m["content"]) for m in fake_llm.calls[-1]["messages"] if m["role"] == "tool"]
    assert "Unknown tool" in results[0]["error"] and results[1]["error"] == "topic is required"


def test_agent_failure_is_not_saved(client, fake_llm, monkeypatch):
    async def broken(*a, **k):
        raise llm.LLMError("down")

    monkeypatch.setattr(llm, "complete_with_tools", broken)
    resp = client.post("/api/chat/agent", json={"message": "hello"})
    assert _events(resp)[-1]["type"] == "error"
    assert client.get(f"/api/chat/sessions/{resp.headers['X-Session-Id']}").json()["messages"] == []


# ---------------------------------------------------------------- provider transcripts

def test_anthropic_transcript_groups_tool_results_and_echoes_raw():
    raw = [{"type": "tool_use", "id": "a", "name": "search_notes", "input": {}},
           {"type": "tool_use", "id": "b", "name": "get_mastery", "input": {}}]
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [], "raw": raw, "raw_provider": "anthropic"},
        {"role": "tool", "tool_call_id": "a", "name": "search_notes", "content": "{}"},
        {"role": "tool", "tool_call_id": "b", "name": "get_mastery", "content": "{}"},
    ]
    out = llm._anthropic_tool_messages(messages)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"] is raw
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["a", "b"]


def test_openai_and_gemini_transcripts():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "get_mastery", "args": {"x": 1}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "get_mastery", "content": '{"topics": []}'},
    ]
    oa = llm._openai_style_messages(messages, "sys", ollama=False)
    assert oa[2]["tool_calls"][0]["function"]["arguments"] == '{"x": 1}'
    assert oa[3] == {"role": "tool", "content": '{"topics": []}', "tool_call_id": "c1"}
    ol = llm._openai_style_messages(messages, "", ollama=True)
    assert ol[1]["tool_calls"][0]["function"]["arguments"] == {"x": 1} and ol[2]["tool_name"] == "get_mastery"
    gem = llm._gemini_tool_contents(messages)
    assert gem[1]["parts"][0]["functionCall"]["name"] == "get_mastery"
    assert gem[2]["parts"][0]["functionResponse"]["response"] == {"result": {"topics": []}}


# ---------------------------------------------------------------- grounding

def test_coverage_detects_unrelated_notes():
    chunks = [{"title": "Bio", "topic": "Photosynthesis", "content": "Plants use chlorophyll to capture light."}]
    assert grounding.coverage("How does chlorophyll capture light?", chunks)["covered"]
    assert not grounding.coverage("Who won the 1998 football world cup?", chunks)["covered"]


def test_tutor_says_when_notes_do_not_cover_question(client, fake_llm):
    add_chunks([("Photosynthesis", "Plants use chlorophyll to capture light.")])
    resp = client.post("/api/chat", json={"message": "Who won the football world cup in 1998?"})
    assert resp.json()["sources"] == []
    assert "notes do not cover this question" in fake_llm.calls[-1]["system"]

    client.put("/api/settings/grounding", json={"enabled": False})
    resp = client.post("/api/chat", json={"message": "Who won the football world cup in 1998?"})
    assert resp.json()["sources"]


def test_check_answer_labels_sentences(db):
    chunks = [{"n": 1, "content": "Photosynthesis in plants makes glucose sugar from light, water and carbon dioxide."}]
    answer = ("Photosynthesis makes glucose sugar from light and water [1]. "
              "The Eiffel Tower was finished in Paris during eighteen eighty nine.")
    result = asyncio.run(grounding.check_answer(answer, chunks))
    assert [s["supported"] for s in result["sentences"]] == [True, False]
    assert result["label"] == "partly"
    assert asyncio.run(grounding.check_answer("Anything at all here, long enough.", []))["label"] == "not_in_notes"


def test_check_endpoint_saves_grounding(client, fake_llm):
    add_chunks([("Photosynthesis", "Photosynthesis makes sugar from light in the leaves of plants.")])
    fake_llm.stream_text = "Photosynthesis makes sugar from light [1]."
    resp = client.post("/api/chat/stream", json={"message": "What does photosynthesis make?"})
    sid = resp.headers["X-Session-Id"]
    check = client.post(f"/api/chat/sessions/{sid}/check").json()
    assert check["label"] == "fully"
    saved = client.get(f"/api/chat/sessions/{sid}").json()["messages"][-1]
    assert saved["grounding"]["label"] == "fully"


# ---------------------------------------------------------------- math

@pytest.mark.parametrize("a,b,expected", [
    ("2x+2", "2(x+1)", True),
    ("x = 5", "5", True),
    (r"\frac{1}{2}", "0.5", True),
    ("$x^2$", "x*x", True),
    ("2x+3", "2x+4", False),
    ("Chlorophyll", "chlorophyll", None),
])
def test_equivalent(a, b, expected):
    assert math_check.equivalent(a, b) is expected


def test_verify_steps_flags_bad_step():
    steps = math_check.verify_steps([{"expression": "2x+3=7"}, {"expression": "2x=4"}, {"expression": "x=3"}])
    assert [s["status"] for s in steps] == ["unchecked", "verified", "mismatch"]


def test_short_answer_math_graded_by_algebra(client, fake_llm):
    resp = client.post("/api/quiz/submit", json={
        "topic": "Algebra", "question_type": "short_answer", "difficulty": "easy",
        "question": "Expand 2(x+1)", "correct_answer": "2x+2", "user_answer": "2(1+x)",
    }).json()
    assert resp["is_correct"] and resp["checked_by"] == "algebra"
    assert not any("is_correct" in c.get("system", "") for c in fake_llm.calls)


def test_solve_endpoint_marks_steps(client):
    data = client.post("/api/math/solve", json={"problem": "2x + 3 = 7"}).json()
    assert [s["status"] for s in data["steps"]] == ["unchecked", "verified", "mismatch"]
    assert data["mismatches"] == 1


def test_humanize_keeps_math_and_code():
    text = "**Bold** idea: $a*b*c$ and\n```python\nx = 2 * 3 * 4\n```\n- item"
    out = humanize_text(text)
    assert "$a*b*c$" in out and "x = 2 * 3 * 4" in out and "**" not in out and "- item" not in out
