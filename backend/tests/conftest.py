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
        self.tool_script: list[tuple[str, list]] = [("A plain answer.", [])]
        self.tools_supported = True

    def reply_for(self, system: str, messages: list[dict]) -> str:
        prompt = messages[-1]["content"]
        if "marking rubrics" in system:
            return json.dumps({"criteria": [
                {"name": "Definition", "description": "Defines photosynthesis", "points": 2},
                {"name": "Inputs", "description": "Names light, water and CO2", "points": 3},
            ]})
        if "fair, encouraging examiner" in system:
            return json.dumps({
                "criteria": [
                    {"name": "Definition", "score": 2, "max": 2, "feedback": "Clear.", "evidence": [1]},
                    {"name": "Inputs", "score": 9, "max": 3, "feedback": "Over-scored on purpose.", "evidence": []},
                ],
                "overall_feedback": "Good answer.", "model_answer": "Plants turn light into sugar.",
            })
        if "Feynman" in system:
            return json.dumps({"score": 82, "accuracy": 90, "clarity": 75, "completeness": 80,
                               "gaps": ["Mention chlorophyll"], "jargon": [{"term": "ATP", "suggestion": "energy packet"}],
                               "misconceptions": [], "follow_up_question": "Why are leaves green?",
                               "verdict": "Nice and clear."})
        if "misconception behind" in system:
            return json.dumps({"is_pattern": True, "same_as": None, "title": "Confuses mitosis with meiosis",
                               "description": "Thinks mitosis makes gametes.", "correction": "Meiosis makes gametes."})
        if "target one specific misconception" in system:
            return json.dumps({"questions": [
                {"question": f"Drill {i}?", "options": ["Mitosis", "Meiosis"], "correct_answer": "Meiosis",
                 "explanation": "Gametes come from meiosis."} for i in range(1, 4)
            ]})
        if "order study concepts" in system:
            return json.dumps({"prerequisites": [{"before": "Stomata", "after": "Photosynthesis"},
                                                 {"before": "Nonexistent", "after": "Photosynthesis"}]})
        if "fill-in-the-blank flashcard" in system:
            return json.dumps({"text": prompt.replace("mitochondria", "{{c1::mitochondria}}")})
        if "solve math problems" in system:
            return json.dumps({"steps": [
                {"explanation": "Start", "expression": "2x + 3 = 7"},
                {"explanation": "Subtract 3", "expression": "2x = 4"},
                {"explanation": "Divide by 2", "expression": "x = 3"},
            ], "final_answer": "x = 3"})
        if "check whether statements" in system:
            return json.dumps({"results": [{"n": 1, "supported": True}]})
        if "highlighted passages" in system:
            count = messages[-1]["content"].count("\n\n[") + 1
            return json.dumps({"cards": [
                {"n": i, "front": f"Highlight question {i}?", "back": f"Highlight answer {i}."}
                for i in range(1, count + 1)
            ]})
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

    async def complete(self, messages, system="", json_mode=False, cfg=None, temperature=None):
        self.calls.append({"messages": messages, "system": system, "json_mode": json_mode})
        return self.reply_for(system, messages)

    async def complete_with_tools(self, messages, system, tools, cfg=None, allow_calls=True):
        """Plays self.tool_script: each entry is (text, [(tool_name, args), ...])."""
        self.calls.append({"messages": list(messages), "system": system, "tools": [t["name"] for t in tools],
                           "allow_calls": allow_calls})
        step = sum(1 for m in messages if m["role"] == "assistant" and m.get("tool_calls") is not None)
        text, calls = self.tool_script[min(step, len(self.tool_script) - 1)] if allow_calls else ("Out of steps.", [])
        calls = [{"id": f"t{step}_{i}", "name": n, "args": a} for i, (n, a) in enumerate(calls)]
        return {"text": text, "tool_calls": calls,
                "assistant": {"role": "assistant", "content": text, "tool_calls": calls, "raw": None}}

    async def stream(self, messages, system="", cfg=None):
        self.calls.append({"messages": messages, "system": system, "stream": True})
        for word in self.stream_text.split(" "):
            yield word + " "


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "complete", fake.complete)
    monkeypatch.setattr(llm, "stream", fake.stream)
    monkeypatch.setattr(llm, "complete_with_tools", fake.complete_with_tools)

    async def supports_tools(cfg=None):
        return fake.tools_supported

    monkeypatch.setattr(llm, "supports_tools", supports_tools)

    async def describe_image(image, mime, prompt=llm.VISION_PROMPT, cfg=None):
        fake.calls.append({"vision": mime})
        return "Handwritten note: the mitochondria is the powerhouse of the cell."

    monkeypatch.setattr(llm, "describe_image", describe_image)
    return fake


# Words in the same group get the same embedding direction, so "car" matches "automobile"
# by meaning even though the words differ.
SYNONYMS = [
    {"car", "cars", "automobile", "vehicle", "engine"},
    {"plant", "plants", "photosynthesis", "chlorophyll", "leaf"},
    {"heart", "cardiac", "blood", "pulse"},
]


def fake_vector(text: str, dim: int = 16) -> list[float]:
    import re
    import zlib

    vec = [0.0] * dim
    for word in re.findall(r"\w+", text.lower()):
        group = next((i for i, g in enumerate(SYNONYMS) if word in g), None)
        if group is not None:
            vec[group] += 1.0
        else:
            vec[3 + zlib.crc32(word.encode()) % (dim - 3)] += 0.2  # stable across runs, unlike hash()
    return vec


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    from services import embeddings

    calls = []

    async def embed(texts, cfg=None):
        calls.append(len(texts))
        return [fake_vector(t) for t in texts]

    monkeypatch.setattr(embeddings, "embed_texts", embed)
    return calls


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    uploads = data_dir / "uploads"
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "DB_PATH", data_dir / "tutor.db")
    import routers.documents
    import routers.exam_tools
    import services.card_types
    import services.data_transfer
    import services.document_processor
    import services.transcription

    for mod in (services.document_processor, services.data_transfer, routers.documents, routers.exam_tools,
                services.card_types, services.transcription):
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
