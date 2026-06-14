import re
from typing import List

from database import get_db


def _tokenize(query: str) -> list[str]:
    words = re.findall(r"\w+", query.lower())
    return [w for w in words if len(w) > 2]


def search_chunks(user_id: int, query: str, topic: str | None = None, limit: int = 5) -> List[dict]:
    """Simple keyword scoring — no vector DB."""
    tokens = _tokenize(query)
    if not tokens:
        tokens = _tokenize(topic or "")

    with get_db() as conn:
        if topic:
            rows = conn.execute(
                """SELECT id, title, topic, content, source FROM knowledge_chunks
                   WHERE user_id = ? AND LOWER(topic) LIKE ?""",
                (user_id, f"%{topic.lower()}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, topic, content, source FROM knowledge_chunks WHERE user_id = ?",
                (user_id,),
            ).fetchall()

    scored = []
    for row in rows:
        text = f"{row['title']} {row['topic']} {row['content']}".lower()
        score = sum(text.count(t) for t in tokens) if tokens else 1
        if score > 0 or not tokens:
            scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def search_chunks_scored(
    user_id: int, query: str, topic: str | None = None, limit: int = 5
) -> list[dict]:
    """Same as search_chunks but each result includes a match score."""
    tokens = _tokenize(query)
    if not tokens:
        tokens = _tokenize(topic or "")

    with get_db() as conn:
        if topic:
            rows = conn.execute(
                """SELECT id, title, topic, content, source FROM knowledge_chunks
                   WHERE user_id = ? AND LOWER(topic) LIKE ?""",
                (user_id, f"%{topic.lower()}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, topic, content, source FROM knowledge_chunks WHERE user_id = ?",
                (user_id,),
            ).fetchall()

    scored = []
    for row in rows:
        text = f"{row['title']} {row['topic']} {row['content']}".lower()
        score = sum(text.count(t) for t in tokens) if tokens else 0
        if score > 0:
            item = dict(row)
            item["match_score"] = score
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


# Minimum keyword hit score on best chunk to count as "found in your materials"
CONTEXT_MATCH_THRESHOLD = 2


def get_topics(user_id: int) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT topic FROM knowledge_chunks WHERE user_id = ? AND topic IS NOT NULL",
            (user_id,),
        ).fetchall()
    return sorted({r["topic"] for r in rows if r["topic"]})
