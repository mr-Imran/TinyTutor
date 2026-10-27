from database import get_db
from services.search import global_search, search_chunks, search_chunks_scored
from tests.conftest import add_chunks


def test_bm25_ranks_and_scores(db):
    add_chunks([
        ("Biology", "Photosynthesis happens in chloroplasts. Photosynthesis needs light."),
        ("Biology", "Respiration releases energy."),
        ("Physics", "Light travels fast."),
    ])
    results = search_chunks_scored(1, "photosynthesis light")
    assert results[0]["content"].startswith("Photosynthesis")
    assert results[0]["match_score"] >= 3
    assert results[0]["page_number"] == 1 and results[0]["file_type"] == "pdf"


def test_topic_filter_and_operator_safety(db):
    add_chunks([("Biology", "Light helps plants."), ("Physics", "Light is a wave.")])
    assert [r["topic"] for r in search_chunks_scored(1, "light", topic="physics")] == ["Physics"]
    # FTS syntax in user input must not raise.
    assert search_chunks_scored(1, 'light AND "NEAR(" * :') != []


def test_fallback_returns_topic_chunks_when_no_match(db):
    add_chunks([("Biology", "Cells divide.")])
    assert len(search_chunks(1, "quantum", topic="Biology")) == 1


def test_index_follows_updates_and_deletes(db):
    add_chunks([("Biology", "Enzymes speed reactions.")])
    with get_db() as conn:
        conn.execute("UPDATE knowledge_chunks SET content = 'Hormones carry signals.'")
    assert global_search(1, "enzymes") == []
    assert len(global_search(1, "hormones")) == 1
    with get_db() as conn:
        conn.execute("DELETE FROM knowledge_chunks")
    assert global_search(1, "hormones") == []
