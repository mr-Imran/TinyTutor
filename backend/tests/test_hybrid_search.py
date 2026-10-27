import asyncio

from database import get_db
from services import embeddings
from services.search import hybrid_global_search, hybrid_search
from tests.conftest import add_chunks


def _index():
    return asyncio.run(embeddings.index_chunks(1))


def test_meaning_match_without_shared_words(db):
    add_chunks([
        ("Mechanics", "An automobile engine needs regular oil changes."),
        ("Biology", "Photosynthesis happens in chloroplasts."),
    ])
    assert _index() == 2

    results = asyncio.run(hybrid_search(1, "how do I look after my car", limit=2))
    assert results[0]["topic"] == "Mechanics"
    assert results[0]["semantic_score"] > 0.5
    assert results[0]["match_score"] == 0  # no keyword overlap at all


def test_keyword_and_semantic_hits_are_fused(db):
    add_chunks([
        ("Biology", "Chlorophyll absorbs light in the leaf."),
        ("Biology", "Mitochondria release energy."),
        ("Mechanics", "Vehicle brakes use friction."),
    ])
    _index()
    results = asyncio.run(hybrid_search(1, "chlorophyll plants", limit=3))
    assert results[0]["content"].startswith("Chlorophyll")
    assert results[0]["semantic_score"] is not None and results[0]["match_score"] >= 1


def test_global_search_shows_preview_for_meaning_only_hits(db):
    add_chunks([("Medicine", "Cardiac output depends on heart rate and stroke volume.")])
    _index()
    hits = asyncio.run(hybrid_global_search(1, "pulse"))
    assert hits and hits[0]["snippet"].startswith("Cardiac output")
    assert hits[0]["semantic_score"] > 0


def test_index_is_incremental_and_edits_invalidate(db, fake_embeddings):
    add_chunks([("Biology", "Plants need light."), ("Biology", "Leaves are green.")])
    assert _index() == 2
    assert _index() == 0
    with get_db() as conn:
        conn.execute("UPDATE knowledge_chunks SET content = 'Plants need water.' WHERE id = 1")
    assert _index() == 1
    assert embeddings.index_status(1) == {
        "provider": "ollama", "model": "nomic-embed-text", "indexed": 2, "total": 2,
    }


def test_embedding_failure_falls_back_to_keywords(db, monkeypatch):
    add_chunks([("Biology", "Photosynthesis needs light.")])
    _index()

    async def broken(texts, cfg=None):
        raise embeddings.EmbeddingError("ollama not running")

    monkeypatch.setattr(embeddings, "embed_texts", broken)
    results = asyncio.run(hybrid_search(1, "photosynthesis"))
    assert results[0]["semantic_score"] is None and results[0]["match_score"] >= 1


def test_embeddings_off_and_auto_provider(client):
    assert client.get("/api/settings/embeddings").json()["provider"] == "ollama"
    client.put("/api/settings/llm", json={"provider": "gemini", "model": "gemini-2.5-flash"})
    assert client.get("/api/settings/embeddings").json()["provider"] == "gemini"
    off = client.put("/api/settings/embeddings", json={"provider": "off"}).json()
    assert off["provider"] is None and off["indexed"] == 0
    assert client.put("/api/settings/embeddings", json={"provider": "nope"}).status_code == 400


def test_upload_indexes_in_background_and_reindex_endpoint(client):
    client.post("/api/documents/upload", files={"file": ("cars.txt", b"An automobile has an engine.")})
    status = client.get("/api/settings/embeddings").json()
    assert status["indexed"] == status["total"] == 1
    r = client.post("/api/settings/embeddings/reindex").json()
    assert r["embedded"] == 0 and r["error"] is None
