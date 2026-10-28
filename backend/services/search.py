import re
from typing import List

from database import get_db

# Minimum keyword hit score on best chunk to count as "found in your materials"
CONTEXT_MATCH_THRESHOLD = 2

_CHUNK_COLUMNS = """c.id, c.document_id, c.title, c.topic, c.content, c.source, c.page_number,
                    c.start_seconds, d.file_type, d.source_url"""

# Reciprocal rank fusion constant; 60 is the usual choice from the RRF paper.
RRF_K = 60
# Below this cosine similarity a meaning-only match is treated as noise.
MIN_SEMANTIC_SCORE = 0.35


def _tokenize(query: str) -> list[str]:
    words = re.findall(r"\w+", query.lower())
    return [w for w in words if len(w) > 2]


def _fts_query(tokens: list[str]) -> str:
    # Quote every token so FTS operators in user input (AND, NEAR, *, :) are literal.
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens))


def _hit_score(row: dict, tokens: list[str]) -> int:
    text = f"{row['title']} {row['topic']} {row['content']}".lower()
    return sum(text.count(t) for t in tokens)


def search_chunks_scored(
    user_id: int, query: str, topic: str | None = None, limit: int = 5
) -> list[dict]:
    """Full-text search (FTS5 + BM25). Each result includes a keyword `match_score`."""
    tokens = _tokenize(query) or _tokenize(topic or "")
    if not tokens:
        return []

    sql = f"""SELECT {_CHUNK_COLUMNS}
              FROM chunks_fts f
              JOIN knowledge_chunks c ON c.id = f.rowid
              LEFT JOIN documents d ON d.id = c.document_id
              WHERE chunks_fts MATCH ? AND c.user_id = ?"""
    params: list = [_fts_query(tokens), user_id]
    if topic:
        sql += " AND LOWER(c.topic) LIKE ?"
        params.append(f"%{topic.lower()}%")
    sql += " ORDER BY bm25(chunks_fts, 2.0, 1.5, 1.0) LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["match_score"] = _hit_score(item, tokens)
        results.append(item)
    return results


def search_chunks(user_id: int, query: str, topic: str | None = None, limit: int = 5) -> List[dict]:
    """Best matching chunks; falls back to the topic's (or any) chunks when nothing matches."""
    results = search_chunks_scored(user_id, query, topic=topic, limit=limit)
    if results:
        return results

    sql = f"""SELECT {_CHUNK_COLUMNS} FROM knowledge_chunks c
              LEFT JOIN documents d ON d.id = c.document_id
              WHERE c.user_id = ?"""
    params: list = [user_id]
    if topic:
        sql += " AND LOWER(c.topic) LIKE ?"
        params.append(f"%{topic.lower()}%")
    sql += " ORDER BY c.id LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def global_search(user_id: int, query: str, limit: int = 20) -> list[dict]:
    """Search across all materials, returning highlighted snippets."""
    tokens = _tokenize(query)
    if not tokens:
        return []
    with get_db() as conn:
        rows = conn.execute(
            """SELECT c.id, c.document_id, c.title, c.topic, c.source, c.page_number, c.start_seconds,
                      d.file_type, d.source_url, snippet(chunks_fts, 2, '[[', ']]', '…', 24) AS snippet
               FROM chunks_fts f
               JOIN knowledge_chunks c ON c.id = f.rowid
               LEFT JOIN documents d ON d.id = c.document_id
               WHERE chunks_fts MATCH ? AND c.user_id = ?
               ORDER BY bm25(chunks_fts, 2.0, 1.5, 1.0)
               LIMIT ?""",
            (_fts_query(tokens), user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def _chunks_by_id(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT {_CHUNK_COLUMNS} FROM knowledge_chunks c
                LEFT JOIN documents d ON d.id = c.document_id
                WHERE c.id IN ({placeholders})""",
            ids,
        ).fetchall()
    return {r["id"]: dict(r) for r in rows}


async def _semantic(user_id: int, query: str, topic: str | None, limit: int) -> list[tuple[int, float]]:
    from services.embeddings import EmbeddingError, semantic_search

    try:
        hits = await semantic_search(user_id, query, topic=topic, limit=limit)
    except EmbeddingError:
        return []
    return [(cid, score) for cid, score in hits if score >= MIN_SEMANTIC_SCORE]


def _fuse(keyword_ids: list[int], semantic: list[tuple[int, float]]) -> list[int]:
    scores: dict[int, float] = {}
    for rank, cid in enumerate(keyword_ids):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
    for rank, (cid, _) in enumerate(semantic):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
    return sorted(scores, key=lambda c: -scores[c])


async def hybrid_search(user_id: int, query: str, topic: str | None = None, limit: int = 5) -> list[dict]:
    """Keyword (BM25) and meaning (embeddings) results merged by reciprocal rank fusion.

    Each result keeps its keyword `match_score` and gains `semantic_score` (cosine, or None).
    Falls back to search_chunks when neither finds anything.
    """
    keyword = search_chunks_scored(user_id, query, topic=topic, limit=limit * 3)
    semantic = await _semantic(user_id, query, topic, limit * 3)
    if not keyword and not semantic:
        return search_chunks(user_id, query, topic=topic, limit=limit)

    by_id = {r["id"]: r for r in keyword}
    by_id.update(_chunks_by_id([c for c, _ in semantic if c not in by_id]))
    sem_scores = dict(semantic)
    tokens = _tokenize(query) or _tokenize(topic or "")
    results = []
    for cid in _fuse([r["id"] for r in keyword], semantic)[:limit]:
        row = by_id.get(cid)
        if not row:
            continue
        row.setdefault("match_score", _hit_score(row, tokens) if tokens else 0)
        row["semantic_score"] = round(sem_scores[cid], 3) if cid in sem_scores else None
        results.append(row)
    return results


async def hybrid_global_search(user_id: int, query: str, limit: int = 20) -> list[dict]:
    """Global search: keyword hits keep their highlighted snippet; meaning-only hits show a preview."""
    keyword = global_search(user_id, query, limit=limit)
    semantic = await _semantic(user_id, query, None, limit)
    by_id = {r["id"]: {**r, "semantic_score": None} for r in keyword}
    for cid, row in _chunks_by_id([c for c, _ in semantic if c not in by_id]).items():
        content = row.pop("content")
        by_id[cid] = {**row, "snippet": content[:240] + ("…" if len(content) > 240 else "")}
    for cid, score in semantic:
        if cid in by_id:
            by_id[cid]["semantic_score"] = round(score, 3)
    return [by_id[c] for c in _fuse([r["id"] for r in keyword], semantic)[:limit] if c in by_id]


def get_topics(user_id: int) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT topic FROM knowledge_chunks WHERE user_id = ? AND topic IS NOT NULL",
            (user_id,),
        ).fetchall()
    return sorted({r["topic"] for r in rows if r["topic"]})
