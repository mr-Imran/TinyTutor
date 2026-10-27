import io
import json
import zipfile

import database
from services import card_types, notes
from services.data_transfer import flashcards_apkg, flashcards_csv
from tests.conftest import add_chunks


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- cloze

def test_cloze_rendering():
    text = "{{c1::Mitochondria}} make {{c2::ATP::energy molecule}}."
    assert card_types.cloze_indices(text) == [1, 2]
    assert card_types.render_cloze(text, 1, reveal=False) == "[...] make ATP."
    assert card_types.render_cloze(text, 2, reveal=False) == "Mitochondria make [energy molecule]."
    assert card_types.render_cloze(text, 2, reveal=True) == "Mitochondria make [ATP]."


def test_create_cloze_makes_one_card_per_blank_and_dedupes(client):
    body = {"topic": "Cells", "text": "{{c1::Mitochondria}} make {{c2::ATP}}.", "extra": "Cell biology"}
    cards = client.post("/api/flashcards/cloze", json=body).json()
    assert [c["cloze_index"] for c in cards] == [1, 2]
    assert {c["note_id"] for c in cards} == {cards[0]["note_id"]} and cards[0]["card_type"] == "cloze"
    assert client.post("/api/flashcards/cloze", json=body).json() == []
    assert client.post("/api/flashcards/cloze", json={"topic": "x", "text": "no blanks here"}).status_code == 400
    # A basic card with the same text on the same topic is still allowed.
    assert client.post("/api/flashcards", json={"topic": "Cells", "front": body["text"], "back": "b"}).json()


def test_cloze_suggest(client):
    data = client.post("/api/flashcards/cloze/suggest", json={"text": "The mitochondria makes energy."}).json()
    assert data == {"text": "The {{c1::mitochondria}} makes energy.", "used_ai": True}


def test_cloze_suggest_rejects_rewrites(client, fake_llm, monkeypatch):
    async def rewrite(messages, system="", json_mode=False, cfg=None, temperature=None):
        return json.dumps({"text": "Totally {{c1::different}} text."})

    monkeypatch.setattr("services.llm.complete", rewrite)
    data = client.post("/api/flashcards/cloze/suggest", json={"text": "The mitochondria makes energy."}).json()
    assert data["used_ai"] is False and data["text"] == "The mitochondria makes energy."


# ---------------------------------------------------------------- occlusion

def test_occlusion_cards_review_and_cleanup(client, db):
    masks = [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "label": "Nucleus"},
             {"x": 0.5, "y": 0.5, "w": 0.9, "h": 0.9, "label": "Membrane"},  # clipped to the image
             {"x": 0.3, "y": 0.3, "w": 0, "h": 0.1}]  # too small, dropped
    cards = client.post(
        "/api/flashcards/occlusion",
        files={"file": ("cell.png", _png(), "image/png")},
        data={"topic": "Cells", "masks": json.dumps(masks), "header": "Label the cell"},
    ).json()
    assert len(cards) == 2 and cards[1]["masks"][1]["w"] == 0.5
    assert cards[0]["back"] == "Nucleus" and cards[0]["front"] == "Label the cell"
    image = cards[0]["image_name"]
    assert client.get(f"/api/flashcards/images/{image}").status_code == 200
    assert client.get("/api/flashcards/images/..%2Ftutor.db").status_code == 404

    assert client.post(f"/api/flashcards/{cards[0]['id']}/review", json={"grade": 4}).json()["repetitions"] == 1

    client.delete(f"/api/flashcards/{cards[0]['id']}")
    assert (db / "uploads" / image).exists()  # still used by the sibling card
    client.delete(f"/api/flashcards/{cards[1]['id']}")
    assert not (db / "uploads" / image).exists()


def test_exports_handle_new_card_types(client):
    client.post("/api/flashcards/cloze", json={"topic": "Cells", "text": "{{c1::DNA}} holds {{c2::genes}}."})
    client.post(
        "/api/flashcards/occlusion",
        files={"file": ("cell.png", _png(), "image/png")},
        data={"topic": "Cells", "masks": json.dumps([{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "label": "Nucleus"}])},
    )
    csv_text = flashcards_csv(1)
    assert "[...] holds genes." in csv_text and "Nucleus" not in csv_text

    with zipfile.ZipFile(io.BytesIO(flashcards_apkg(1))) as zf:
        media = json.loads(zf.read("media"))
    # The occlusion card ships as a question and an answer picture with the box burned in.
    assert len(media) == 2 and all(n.startswith("tinytutor_") for n in media.values())


def test_apkg_import_restores_cloze(client):
    client.post("/api/flashcards/cloze", json={"topic": "Cells", "text": "{{c1::DNA}} holds {{c2::genes}}."})
    package = flashcards_apkg(1)
    with database.get_db() as conn:
        conn.execute("DELETE FROM flashcards")
    result = client.post("/api/data/flashcards/import", files={"file": ("deck.apkg", package)},
                         data={"topic": "Imported"}).json()
    assert result["imported"] == 1
    cards = client.get("/api/flashcards").json()
    assert [c["card_type"] for c in cards] == ["cloze", "cloze"] and cards[0]["topic"] == "Cells"


# ---------------------------------------------------------------- knowledge graph

def _doc_with_concepts(title, topic, concepts):
    with database.get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (user_id, filename, file_type, title, topic, concepts_json, created_at)
               VALUES (1, ?, 'pdf', ?, ?, ?, datetime('now'))""",
            (f"{title}.pdf", title, topic, json.dumps(concepts)),
        )
        return cur.lastrowid


def test_graph_merges_documents_and_labels_prerequisites(client, fake_llm):
    _doc_with_concepts("Bio 1", "Plants", [
        {"term": "Photosynthesis", "definition": "Light to sugar.", "related": ["Stomata"]},
        {"term": "Stomata", "definition": "Tiny pores for gas exchange.", "related": []},
    ])
    _doc_with_concepts("Bio 2", "Plants", [{"term": "photosynthesis", "definition": "Short.", "related": []}])
    graph = client.post("/api/knowledge/rebuild").json()
    keys = {n["key"]: n for n in graph["nodes"]}
    assert set(keys) == {"photosynthesis", "stomata"}
    assert len(keys["photosynthesis"]["documents"]) == 2
    assert keys["photosynthesis"]["definition"] == "Light to sugar."
    kinds = {(e["source"], e["target"], e["kind"]) for e in graph["edges"]}
    assert ("stomata", "photosynthesis", "prereq") in kinds
    assert ("photosynthesis", "stomata", "related") in kinds

    # Unchanged concepts: no second AI call on rebuild.
    calls = len(fake_llm.calls)
    client.post("/api/knowledge/rebuild")
    assert len(fake_llm.calls) == calls


def test_learning_path_and_link_edits(client):
    _doc_with_concepts("Bio", "Plants", [
        {"term": "Photosynthesis", "definition": "Light to sugar.", "related": []},
        {"term": "Stomata", "definition": "Tiny pores for gas exchange.", "related": []},
    ])
    graph = client.post("/api/knowledge/rebuild").json()
    path = client.get("/api/knowledge/path?key=photosynthesis").json()
    assert [s["key"] for s in path["steps"]] == ["stomata", "photosynthesis"]

    prereq = next(e for e in graph["edges"] if e["kind"] == "prereq")
    graph = client.post(f"/api/knowledge/links/{prereq['id']}/flip").json()
    flipped = next(e for e in graph["edges"] if e["kind"] == "prereq")
    assert (flipped["source"], flipped["target"], flipped["origin"]) == ("photosynthesis", "stomata", "user")

    graph = client.delete(f"/api/knowledge/links/{flipped['id']}").json()
    assert not [e for e in graph["edges"] if e["kind"] == "prereq"]
    # A forced AI relabel does not bring back the link the student removed.
    graph = client.post("/api/knowledge/rebuild?force_ai=true").json()
    assert [(e["source"], e["origin"]) for e in graph["edges"] if e["kind"] == "prereq"] == []
    assert client.get("/api/knowledge/path?key=nope").status_code == 404


def test_mastered_prerequisites_are_skipped(client):
    from services.mastery import record_event

    _doc_with_concepts("Bio", "Plants", [
        {"term": "Photosynthesis", "definition": "Light to sugar.", "related": []},
        {"term": "Stomata", "definition": "Tiny pores for gas exchange.", "related": []},
    ])
    for _ in range(12):
        record_event(1, "Plants", True, "hard")
    client.post("/api/knowledge/rebuild")
    path = client.get("/api/knowledge/path?key=photosynthesis").json()
    assert [s["key"] for s in path["steps"]] == ["photosynthesis"] and path["skipped"] == ["Stomata"]


# ---------------------------------------------------------------- notes

def test_note_crud_links_and_search(client):
    a = client.post("/api/notes", json={"title": "Cells", "body": "# Cells\nThe [[Mitochondria]] makes energy."}).json()
    b = client.post("/api/notes", json={"title": "Mitochondria", "topic": "Biology",
                                        "body": "Mitochondria produce ATP through respiration."}).json()
    assert a["links"] == [{"title": "Mitochondria", "id": None}]  # created before its target existed
    assert client.get(f"/api/notes/{a['id']}").json()["links"][0]["id"] == b["id"]
    assert client.get(f"/api/notes/{b['id']}").json()["backlinks"] == [{"id": a["id"], "title": "Cells"}]

    hits = client.get("/api/search?q=respiration").json()["results"]
    assert hits and hits[0]["file_type"] == "note" and hits[0]["document_id"] == b["id"]
    assert client.get("/api/notes/by-title?title=mitochondria").json()["id"] == b["id"]
    assert [n["title"] for n in client.get("/api/notes").json()] == ["Mitochondria", "Cells"]


def test_note_update_only_replaces_changed_chunks(client, fake_embeddings):
    long_a = "Alpha paragraph about plants. " * 30
    long_b = "Beta paragraph about engines. " * 30
    note = client.post("/api/notes", json={"title": "Mixed", "body": f"# A\n{long_a}\n\n# B\n{long_b}"}).json()
    with database.get_db() as conn:
        before = {r["content"]: r["id"] for r in conn.execute(
            "SELECT id, content FROM knowledge_chunks WHERE document_id = ?", (note["id"],))}
    updated = client.put(f"/api/notes/{note['id']}", json={
        "title": "Mixed", "body": f"# A\n{long_a}\n\n# B\nShort new text about cars."}).json()
    assert updated["sync"]["kept"] >= 1 and updated["sync"]["added"] == 1
    with database.get_db() as conn:
        after = {r["content"]: r["id"] for r in conn.execute(
            "SELECT id, content FROM knowledge_chunks WHERE document_id = ?", (note["id"],))}
    kept = [c for c in after if c in before]
    assert kept and all(after[c] == before[c] for c in kept)


def test_note_assist_and_flashcards(client):
    note = client.post("/api/notes", json={"title": "ATP", "topic": "Energy", "body": "ATP stores energy."}).json()
    assert client.post("/api/notes/assist", json={"action": "simplify", "text": "ATP stores energy."}).json()["text"]
    made = client.post("/api/notes/assist", json={"action": "flashcards", "text": "ATP stores energy.",
                                                  "note_id": note["id"]}).json()
    assert made["created"] == 2
    assert client.post("/api/notes/assist", json={"action": "dance", "text": "x"}).status_code == 400


def test_notes_do_not_earn_upload_xp(client):
    client.post("/api/notes", json={"title": "Empty", "body": ""})
    assert client.get("/api/progress").json()["xp"] == 0


def test_links_in():
    assert notes.links_in("See [[A]] and [[B|the b note]] and [[A]] again") == ["A", "B"]
