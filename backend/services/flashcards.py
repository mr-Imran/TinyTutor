"""Flashcards with SM-2 spaced repetition."""
import json
from datetime import datetime, timedelta

from database import get_db, row_to_dict
from services import llm
from services.ai import _extract_json, build_context
from services.mastery import record_event
from services.quiz import touch_study_streak
from services.search import search_chunks

MIN_EASE = 1.3
RELEARN_MINUTES = 10

GENERATE_SYSTEM = (
    "You write study flashcards. Return ONLY valid JSON, no markdown: "
    '{"cards":[{"front":"short question or term","back":"concise answer, 1-2 sentences"}]}. '
    "Each card tests one fact or idea from the notes. No duplicates."
)


def sm2(ease: float, interval_days: int, repetitions: int, grade: int) -> tuple[float, int, int]:
    """SM-2 update. grade is 0-5; below 3 means the card was forgotten.

    Returns (ease, interval_days, repetitions). An interval of 0 means "review again soon".
    """
    grade = max(0, min(5, grade))
    if grade < 3:
        repetitions, interval_days = 0, 0
    else:
        repetitions += 1
        if repetitions == 1:
            interval_days = 1
        elif repetitions == 2:
            interval_days = 6
        else:
            interval_days = max(1, round(interval_days * ease))
    ease = max(MIN_EASE, ease + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    return round(ease, 3), interval_days, repetitions


def _now() -> datetime:
    return datetime.utcnow()


def card_out(card: dict | None) -> dict | None:
    """Row -> API shape: occlusion boxes are parsed, the raw JSON column dropped."""
    if card is None:
        return None
    card["masks"] = json.loads(card.pop("masks_json", None) or "null")
    return card


def create_cards(user_id: int, topic: str, cards: list[dict], document_id: int | None = None) -> list[dict]:
    now = _now().isoformat()
    with get_db() as conn:
        existing = {
            r["front"].strip().lower()
            for r in conn.execute(
                "SELECT front FROM flashcards WHERE user_id = ? AND topic = ? AND card_type = 'basic'", (user_id, topic)
            )
        }
        ids = []
        for c in cards:
            front, back = str(c.get("front", "")).strip(), str(c.get("back", "")).strip()
            if not front or not back or front.lower() in existing:
                continue
            existing.add(front.lower())
            cur = conn.execute(
                """INSERT INTO flashcards (user_id, document_id, annotation_id, topic, front, back, due_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, document_id, c.get("annotation_id"), topic, front, back, now, now),
            )
            ids.append(cur.lastrowid)
        if not ids:
            return []
        rows = conn.execute(
            f"SELECT * FROM flashcards WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id", ids
        ).fetchall()
    return [card_out(row_to_dict(r)) for r in rows]


def _document_chunks(user_id: int, document_id: int, limit: int) -> tuple[str, list[dict]]:
    with get_db() as conn:
        doc = conn.execute(
            "SELECT topic FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)
        ).fetchone()
        if not doc:
            raise ValueError("Document not found")
        rows = conn.execute(
            "SELECT * FROM knowledge_chunks WHERE document_id = ? ORDER BY id", (document_id,)
        ).fetchall()
    rows = [dict(r) for r in rows]
    if len(rows) > limit:
        step = len(rows) / limit
        rows = [rows[int(i * step)] for i in range(limit)]
    return doc["topic"] or "General", rows


async def generate_cards(
    user_id: int, topic: str | None = None, document_id: int | None = None, count: int = 10
) -> list[dict]:
    if document_id is not None:
        topic, chunks = _document_chunks(user_id, document_id, limit=6)
    elif topic:
        chunks = search_chunks(user_id, topic, topic=topic, limit=6)
    else:
        raise ValueError("Give a topic or a document")
    if not chunks:
        raise ValueError("No study material found for that topic yet")

    prompt = f"Notes:\n{build_context(chunks)}\n\nWrite {count} flashcards about {topic}."
    try:
        raw = await llm.complete([{"role": "user", "content": prompt}], system=GENERATE_SYSTEM, json_mode=True)
        data = json.loads(_extract_json(raw))
    except llm.LLMError as e:
        raise ValueError(f"AI unavailable: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError("The AI returned an unreadable answer, please try again") from e
    cards = data.get("cards") if isinstance(data, dict) else data
    if not isinstance(cards, list):
        raise ValueError("The AI returned no cards, please try again")
    return create_cards(user_id, topic, [c for c in cards if isinstance(c, dict)][:count], document_id)


HIGHLIGHT_SYSTEM = (
    "You turn a student's highlighted passages into flashcards. Return ONLY valid JSON, no markdown: "
    '{"cards":[{"n":1,"front":"question that the highlight answers","back":"answer in 1-2 sentences"}]}. '
    "Write exactly one card per numbered highlight and keep its number in n. "
    "If the student wrote a note, use it to decide what the question should focus on."
)


def _fallback_card(text: str, note: str | None) -> dict:
    """Used when the AI is unavailable: the note (or the opening words) prompts the passage."""
    words = text.split()
    prompt = note.strip() if note and note.strip() else " ".join(words[:8]) + ("…" if len(words) > 8 else "")
    return {"front": f"Recall: {prompt}", "back": text}


async def cards_from_highlights(
    user_id: int, document_id: int, marker_ids: list[int] | None = None
) -> dict:
    """One flashcard per highlight/note that does not have a card yet."""
    with get_db() as conn:
        doc = conn.execute(
            "SELECT topic FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)
        ).fetchone()
        if not doc:
            raise ValueError("Document not found")
        rows = conn.execute(
            """SELECT a.id, a.selected_text, a.note FROM document_annotations a
               WHERE a.user_id = ? AND a.document_id = ?
                 AND NOT EXISTS (SELECT 1 FROM flashcards f WHERE f.annotation_id = a.id)
               ORDER BY a.id""",
            (user_id, document_id),
        ).fetchall()
    highlights = [dict(r) for r in rows if not marker_ids or r["id"] in marker_ids]
    if not highlights:
        return {"created": [], "skipped": 0, "used_ai": False}

    numbered = "\n\n".join(
        f"[{i}] {h['selected_text'].strip()}" + (f"\nStudent note: {h['note'].strip()}" if h["note"] else "")
        for i, h in enumerate(highlights, 1)
    )
    by_n: dict[int, dict] = {}
    used_ai = True
    try:
        raw = await llm.complete([{"role": "user", "content": f"Highlights:\n\n{numbered}"}],
                                 system=HIGHLIGHT_SYSTEM, json_mode=True)
        data = json.loads(_extract_json(raw))
        for c in (data.get("cards") if isinstance(data, dict) else data) or []:
            if isinstance(c, dict) and str(c.get("n", "")).isdigit():
                by_n[int(c["n"])] = c
    except (llm.LLMError, json.JSONDecodeError, TypeError, AttributeError):
        used_ai = False

    cards = []
    for i, h in enumerate(highlights, 1):
        card = by_n.get(i) or _fallback_card(h["selected_text"], h["note"])
        cards.append({"front": card.get("front"), "back": card.get("back"), "annotation_id": h["id"]})
    created = create_cards(user_id, doc["topic"] or "General", cards, document_id)
    return {"created": created, "skipped": len(cards) - len(created), "used_ai": used_ai and bool(by_n)}


def due_cards(user_id: int, limit: int = 20, topic: str | None = None) -> list[dict]:
    sql = "SELECT * FROM flashcards WHERE user_id = ? AND due_at <= ?"
    params: list = [user_id, _now().isoformat()]
    if topic:
        sql += " AND topic = ?"
        params.append(topic)
    sql += " ORDER BY due_at LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        return [card_out(row_to_dict(r)) for r in conn.execute(sql, params).fetchall()]


def list_cards(user_id: int, topic: str | None = None) -> list[dict]:
    sql = "SELECT * FROM flashcards WHERE user_id = ?"
    params: list = [user_id]
    if topic:
        sql += " AND topic = ?"
        params.append(topic)
    with get_db() as conn:
        return [card_out(row_to_dict(r)) for r in conn.execute(sql + " ORDER BY topic, id", params).fetchall()]


def review_card(user_id: int, card_id: int, grade: int) -> dict | None:
    with get_db() as conn:
        card = conn.execute(
            "SELECT * FROM flashcards WHERE id = ? AND user_id = ?", (card_id, user_id)
        ).fetchone()
        if not card:
            return None
        ease, interval, reps = sm2(card["ease"], card["interval_days"], card["repetitions"], grade)
        now = _now()
        due = now + (timedelta(days=interval) if interval else timedelta(minutes=RELEARN_MINUTES))
        conn.execute(
            """UPDATE flashcards SET ease = ?, interval_days = ?, repetitions = ?,
                                     due_at = ?, last_reviewed_at = ? WHERE id = ?""",
            (ease, interval, reps, due.isoformat(), now.isoformat(), card_id),
        )
    # Flashcard recall counts toward mastery, a little less than a quiz answer.
    record_event(user_id, card["topic"], grade >= 3, "easy", source="flashcard")
    touch_study_streak(user_id)
    with get_db() as conn:
        return card_out(row_to_dict(conn.execute("SELECT * FROM flashcards WHERE id = ?", (card_id,)).fetchone()))


def flashcard_stats(user_id: int) -> dict:
    now = _now().isoformat()
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM flashcards WHERE user_id = ?", (user_id,)).fetchone()["c"]
        due = conn.execute(
            "SELECT COUNT(*) c FROM flashcards WHERE user_id = ? AND due_at <= ?", (user_id, now)
        ).fetchone()["c"]
        learned = conn.execute(
            "SELECT COUNT(*) c FROM flashcards WHERE user_id = ? AND repetitions >= 2", (user_id,)
        ).fetchone()["c"]
        by_topic = conn.execute(
            """SELECT topic, COUNT(*) total, SUM(CASE WHEN due_at <= ? THEN 1 ELSE 0 END) due
               FROM flashcards WHERE user_id = ? GROUP BY topic ORDER BY topic""",
            (now, user_id),
        ).fetchall()
    return {"total": total, "due": due, "learned": learned, "topics": [row_to_dict(r) for r in by_topic]}


def update_card(user_id: int, card_id: int, front: str | None, back: str | None):
    with get_db() as conn:
        conn.execute(
            "UPDATE flashcards SET front = COALESCE(?, front), back = COALESCE(?, back) WHERE id = ? AND user_id = ?",
            (front, back, card_id, user_id),
        )


def delete_card(user_id: int, card_id: int):
    from services.card_types import remove_unused_image

    with get_db() as conn:
        row = conn.execute(
            "SELECT image_name FROM flashcards WHERE id = ? AND user_id = ?", (card_id, user_id)
        ).fetchone()
        conn.execute("DELETE FROM flashcards WHERE id = ? AND user_id = ?", (card_id, user_id))
    if row:
        remove_unused_image(row["image_name"])
