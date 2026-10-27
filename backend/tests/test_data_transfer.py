import io
import zipfile

from database import get_db
from tests.conftest import add_chunks


def _add_highlights(doc_id: int, texts: list[tuple[str, str | None]]):
    with get_db() as conn:
        for text, note in texts:
            conn.execute(
                """INSERT INTO document_annotations (user_id, document_id, page_number, marker_type, selected_text, note, created_at)
                   VALUES (1, ?, 1, 'highlight', ?, ?, datetime('now'))""",
                (doc_id, text, note),
            )


def test_highlights_become_flashcards_once(client):
    doc = add_chunks([("Biology", "Cells.")])
    _add_highlights(doc, [("ATP stores energy in phosphate bonds.", None), ("Ribosomes make proteins.", "why?")])
    r = client.post("/api/flashcards/from-highlights", json={"document_id": doc}).json()
    assert [c["front"] for c in r["created"]] == ["Highlight question 1?", "Highlight question 2?"]
    assert r["used_ai"] is True and all(c["annotation_id"] for c in r["created"])
    again = client.post("/api/flashcards/from-highlights", json={"document_id": doc}).json()
    assert again["created"] == []


def test_highlight_cards_fall_back_without_ai(client, monkeypatch):
    from services import llm

    async def offline(*a, **k):
        raise llm.LLMError("offline")

    monkeypatch.setattr(llm, "complete", offline)
    doc = add_chunks([("Biology", "Cells.")])
    _add_highlights(doc, [("Osmosis moves water across a membrane toward higher solute concentration.", "osmosis direction")])
    r = client.post("/api/flashcards/from-highlights", json={"document_id": doc}).json()
    assert r["used_ai"] is False
    assert r["created"][0]["front"] == "Recall: osmosis direction"
    assert client.post("/api/flashcards/from-highlights", json={"document_id": 999}).status_code == 404


def test_backup_and_restore_roundtrip(client, db):
    up = client.post("/api/documents/upload", files={"file": ("keep.txt", b"Glaciers carve valleys over time.")}).json()
    backup = client.get("/api/data/backup")
    assert backup.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(backup.content)).namelist()
    assert "tutor.db" in names and any(n.startswith("uploads/") for n in names)

    client.delete(f"/api/documents/{up['document_id']}")
    assert client.get("/api/search", params={"q": "glaciers"}).json()["results"] == []

    r = client.post("/api/data/restore", files={"file": ("backup.zip", backup.content)})
    assert r.status_code == 200, r.text
    assert r.json()["documents"] == 1 and r.json()["files"] == 1
    assert (db / r.json()["safety_copy"]).exists()
    assert client.get("/api/search", params={"q": "glaciers"}).json()["results"]
    assert len(list((db / "uploads").iterdir())) == 1


def test_restore_rejects_bad_files_and_path_tricks(client, db):
    assert client.post("/api/data/restore", files={"file": ("x.zip", b"not a zip")}).status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hi")
    assert client.post("/api/data/restore", files={"file": ("x.zip", buf.getvalue())}).status_code == 400

    good = client.get("/api/data/backup").content
    evil = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(evil, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("uploads/../../escape.txt", "should land inside uploads")
    assert client.post("/api/data/restore", files={"file": ("x.zip", evil.getvalue())}).status_code == 200
    assert not (db.parent / "escape.txt").exists()
    assert (db / "uploads" / "escape.txt").exists()


def test_flashcards_csv_and_anki_roundtrip(client):
    client.post("/api/flashcards", json={"topic": "Chemistry", "front": "H2O is?", "back": "Water"})
    client.post("/api/flashcards", json={"topic": "Physics", "front": "F = ?", "back": "m × a"})

    csv_text = client.get("/api/data/flashcards.csv").text
    assert csv_text.splitlines()[0] == "topic,front,back,interval_days,repetitions,due_at"
    apkg = client.get("/api/data/flashcards.apkg").content

    for card in client.get("/api/flashcards").json():
        client.delete(f"/api/flashcards/{card['id']}")

    r = client.post("/api/data/flashcards/import", files={"file": ("deck.apkg", apkg)}).json()
    assert r["imported"] == 2 and r["topics"] == ["Chemistry", "Physics"]
    r = client.post("/api/data/flashcards/import", files={"file": ("deck.csv", csv_text.encode())}).json()
    assert r["imported"] == 0 and r["skipped"] == 2  # duplicates


def test_csv_import_without_header_and_anki_text(client):
    r = client.post(
        "/api/data/flashcards/import",
        files={"file": ("cards.txt", "#separator:tab\nCapital of France\t<b>Paris</b>\nLargest planet\tJupiter\n".encode())},
        data={"topic": "Geography"},
    ).json()
    assert r["imported"] == 2 and r["topics"] == ["Geography"]
    backs = {c["back"] for c in client.get("/api/flashcards").json()}
    assert "Paris" in backs
    assert client.post("/api/data/flashcards/import", files={"file": ("x.pdf", b"%PDF")}).status_code == 400
    assert client.get("/api/data/flashcards.apkg", params={"topic": "None"}).status_code == 400


def test_quiz_history_csv(client):
    client.post("/api/quiz/submit", json={
        "topic": "Math", "question_type": "mcq", "difficulty": "easy", "question": "1+1?",
        "options": ["1", "2"], "correct_answer": "2", "user_answer": "2",
    })
    lines = client.get("/api/data/quiz-history.csv").text.strip().splitlines()
    assert lines[0].startswith("date,topic") and lines[1].endswith(",2,2,yes")
