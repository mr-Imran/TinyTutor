import re
from typing import List

from database import get_db

# Minimum keyword hit score on best chunk to count as "found in your materials"
CONTEXT_MATCH_THRESHOLD = 2

_CHUNK_COLUMNS = """c.id, c.document_id, c.title, c.topic, c.content, c.source, c.page_number,
                    d.file_type"""


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
            """SELECT c.id, c.document_id, c.title, c.topic, c.source, c.page_number, d.file_type,
                      snippet(chunks_fts, 2, '[[', ']]', '…', 24) AS snippet
               FROM chunks_fts f
               JOIN knowledge_chunks c ON c.id = f.rowid
               LEFT JOIN documents d ON d.id = c.document_id
               WHERE chunks_fts MATCH ? AND c.user_id = ?
               ORDER BY bm25(chunks_fts, 2.0, 1.5, 1.0)
               LIMIT ?""",
            (_fts_query(tokens), user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_topics(user_id: int) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT topic FROM knowledge_chunks WHERE user_id = ? AND topic IS NOT NULL",
            (user_id,),
        ).fetchall()
    return sorted({r["topic"] for r in rows if r["topic"]})
