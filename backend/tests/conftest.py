import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from services import llm  # noqa: E402


class FakeLLM:
    """Stands in for every provider. Picks a canned reply from the system prompt."""

    def __init__(self):
        self.calls: list[dict] = []
        self.stream_text = "Photosynthesis makes sugar from light [1]."
        self.grade_correct = True

    def reply_for(self, system: str, messages: list[dict]) -> str:
        if "flashcards" in system:
            return json.dumps({"cards": [
                {"front": "What is ATP?", "back": "The cell's energy currency."},
                {"front": "Where does photosynthesis happen?", "back": "In chloroplasts."},
                {"front": "What is ATP?", "back": "Duplicate that should be skipped."},
            ]})
        if "summarise" in system:
            return json.dumps({
                "summary": "Plants turn light into chemical energy.",
                "concepts": [
                    {"term": "Photosynthesis", "definition": "Light to sugar.", "related": ["Chlorophyll", "Unknown"]},
                    {"term": "Chlorophyll", "definition": "Green pigment.", "related": ["Photosynthesis"]},
                ],
            })
        if "is_correct" in system:
            return json.dumps({"is_correct": self.grade_correct, "feedback": "Looks right."})
        if '"correct_answer"' in system:
            prompt = messages[-1]["content"]
            if "true/false" in prompt:
                return json.dumps({"question": "Plants need light?", "options": ["True", "False"],
                                   "correct_answer": "True", "explanation": "They do."})
            if "short answer" in prompt:
                return json.dumps({"question": "Name the green pigment.", "options": None,
                                   "correct_answer": "Chlorophyll", "explanation": "It absorbs light."})
            return json.dumps({"question": "What do plants make?", "options": ["Sugar", "Salt", "Iron", "Oil"],
                               "correct_answer": "Sugar", "explanation": "Glucose."})
        return "A plain answer."

    async def complete(self, messages, system="", json_mode=False, cfg=None):
        self.calls.append({"messages": messages, "system": system, "json_mode": json_mode})
        return self.reply_for(system, messages)

    async def stream(self, messages, system="", cfg=None):
        self.calls.append({"messages": messages, "system": system, "stream": True})
        for word in self.stream_text.split(" "):
            yield word + " "


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "complete", fake.complete)
    monkeypatch.setattr(llm, "stream", fake.stream)
    return fake


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    uploads = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "tutor.db")
    import routers.documents
    import routers.exam_tools
    import services.document_processor

    for mod in (services.document_processor, routers.documents, routers.exam_tools):
        monkeypatch.setattr(mod, "UPLOAD_DIR", uploads)
    for var in ("LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    database.init_db()
    return data_dir


@pytest.fixture
def client(db, fake_llm, monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "start_scheduler", lambda: None)
    with TestClient(main.app) as c:
        yield c


def add_chunks(rows: list[tuple[str, str]], document_title: str = "Biology", file_type: str = "pdf") -> int:
    """Insert a document with (topic, content) chunks; returns the document id."""
    with database.get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (user_id, filename, file_type, title, topic, chunk_count, created_at)
               VALUES (1, ?, ?, ?, ?, ?, datetime('now'))""",
            (f"{document_title}.{file_type}", file_type, document_title, rows[0][0], len(rows)),
        )
        doc_id = cur.lastrowid
        for i, (topic, content) in enumerate(rows, 1):
            conn.execute(
                """INSERT INTO knowledge_chunks (document_id, user_id, title, topic, content, source, page_number, created_at)
                   VALUES (?, 1, ?, ?, ?, ?, ?, datetime('now'))""",
                (doc_id, f"{document_title} — Part {i}", topic, content, f"{document_title}.{file_type}", i),
            )
    return doc_id
