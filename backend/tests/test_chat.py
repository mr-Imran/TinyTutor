import base64
import json

from tests.conftest import add_chunks


def test_stream_creates_session_with_citations_and_history(client, fake_llm):
    add_chunks([("Biology", "Photosynthesis turns light into sugar.")])
    r = client.post("/api/chat/stream", json={"message": "What is photosynthesis?"})
    assert r.status_code == 200
    assert r.text.strip() == "Photosynthesis makes sugar from light [1]."
    session_id = int(r.headers["X-Session-Id"])
    sources = json.loads(base64.b64decode(r.headers["X-Sources"]))
    assert sources[0]["n"] == 1 and sources[0]["page_number"] == 1
    assert "square brackets" in fake_llm.calls[-1]["system"]

    r = client.post("/api/chat/stream", json={"message": "And where?", "session_id": session_id})
    assert r.status_code == 200
    history = fake_llm.calls[-1]["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]

    detail = client.get(f"/api/chat/sessions/{session_id}").json()
    assert detail["title"] == "What is photosynthesis?"
    assert len(detail["messages"]) == 4
    assert detail["messages"][1]["sources"][0]["source"] == "Biology.pdf"


def test_sessions_are_separated_by_kind_and_deletable(client):
    client.post("/api/chat", json={"message": "tutor question"})
    client.post("/api/study/mentor/chat", json={"message": "mentor question"})
    tutor = client.get("/api/chat/sessions", params={"kind": "tutor"}).json()
    mentor = client.get("/api/chat/sessions", params={"kind": "mentor"}).json()
    assert [s["title"] for s in tutor] == ["tutor question"]
    assert [s["title"] for s in mentor] == ["mentor question"]

    client.patch(f"/api/chat/sessions/{tutor[0]['id']}", json={"title": "Renamed"})
    assert client.get(f"/api/chat/sessions/{tutor[0]['id']}").json()["title"] == "Renamed"
    client.delete(f"/api/chat/sessions/{tutor[0]['id']}")
    assert client.get(f"/api/chat/sessions/{tutor[0]['id']}").status_code == 404


def test_unknown_session_and_empty_message(client):
    assert client.post("/api/chat/stream", json={"message": "hi", "session_id": 999}).status_code == 404
    assert client.post("/api/chat/stream", json={"message": "  "}).status_code == 400
