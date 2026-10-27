"""Notes the student writes in the app (Markdown with [[wiki links]]).

A note is a document with file_type 'note' whose Markdown lives in documents.body. Saving re-chunks
the note but only replaces chunks whose text changed, so unchanged paragraphs keep their embeddings.
Notes are searchable and citable exactly like uploads, and backed up with the database.
"""
import json
import re
from datetime import datetime

from database import get_db, row_to_dict
from services import llm
from services.ai import _extract_json
from services.document_processor import Segment, chunk_segments
from services.flashcards import GENERATE_SYSTEM, create_cards
from services.text_style import HUMAN_STYLE_RULE

LINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+))?\]\]")
MAX_BODY = 200_000

ASSIST_PROMPTS = {
    "continue": "Continue the student's note with one or two short paragraphs in the same style. "
                "Output only the new text.",
    "simplify": "Rewrite the selected text so a 12-year-old understands it, keeping every fact. "
                "Output only the rewrite.",
    "explain": "Explain the selected text simply, with one everyday example. Output only the explanation.",
    "summarize": "Summarise the selected text in two or three sentences. Output only the summary.",
}


class NoteError(ValueError):
    pass


def links_in(body: str) -> list[str]:
    return list(dict.fromkeys(m.group(1).strip() for m in LINK_RE.finditer(body or "")))


def _plain(body: str) -> str:
    """Markdown -> text for search: [[Note|label]] becomes label, headings keep their words."""
    text = LINK_RE.sub(lambda m: m.group(2) or m.group(1), body)
    return re.sub(r"^#{1,6}\s*", "", text, flags=re.M)


def _sections(body: str) -> list[Segment]:
    """One segment per heading section, so chunks do not straddle unrelated parts of a note."""
    parts = re.split(r"(?m)^(?=#{1,6}\s)", body)
    return [Segment(_plain(p)) for p in parts if p.strip()]


def _sync_chunks(user_id: int, doc_id: int, title: str, topic: str, body: str) -> dict:
    new = chunk_segments(_sections(body), title, topic, f"{title} (note)")
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        old = {r["content"]: r["id"] for r in conn.execute(
            "SELECT id, content FROM knowledge_chunks WHERE document_id = ?", (doc_id,)
        )}
        keep = {c["content"] for c in new}
        stale = [cid for content, cid in old.items() if content not in keep]
        if stale:
            conn.execute(f"DELETE FROM knowledge_chunks WHERE id IN ({','.join('?' * len(stale))})", stale)
        added = [c for c in new if c["content"] not in old]
        conn.executemany(
            """INSERT INTO knowledge_chunks (document_id, user_id, title, topic, content, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(doc_id, user_id, c["title"], topic, c["content"], c["source"], now) for c in added],
        )
        # Title or topic changes apply to every chunk (the FTS update trigger keeps search in sync).
        conn.execute(
            "UPDATE knowledge_chunks SET topic = ?, source = ? WHERE document_id = ? AND (topic != ? OR source != ?)",
            (topic, f"{title} (note)", doc_id, topic, f"{title} (note)"),
        )
        count = conn.execute("SELECT COUNT(*) c FROM knowledge_chunks WHERE document_id = ?", (doc_id,)).fetchone()["c"]
        conn.execute("UPDATE documents SET chunk_count = ? WHERE id = ?", (count, doc_id))
    return {"added": len(added), "removed": len(stale), "kept": len(new) - len(added)}


def _note_row(user_id: int, note_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ? AND file_type = 'note'", (note_id, user_id)
        ).fetchone()
    if not row:
        raise NoteError("Note not found")
    return row


def _summary(row) -> dict:
    d = row_to_dict(row)
    body = d.get("body") or ""
    return {
        "id": d["id"], "title": d["title"], "topic": d["topic"], "created_at": d["created_at"],
        "updated_at": d.get("updated_at") or d["created_at"], "chunk_count": d["chunk_count"],
        "preview": _plain(body)[:160],
    }


def list_notes(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM documents WHERE user_id = ? AND file_type = 'note'
               ORDER BY COALESCE(updated_at, created_at) DESC""",
            (user_id,),
        ).fetchall()
    return [_summary(r) for r in rows]


def get_note(user_id: int, note_id: int) -> dict:
    row = _note_row(user_id, note_id)
    note = {**_summary(row), "body": row["body"] or ""}
    with get_db() as conn:
        others = conn.execute(
            "SELECT id, title, body FROM documents WHERE user_id = ? AND file_type = 'note' AND id != ?",
            (user_id, note_id),
        ).fetchall()
    by_title = {o["title"].strip().lower(): o["id"] for o in others}
    note["links"] = [{"title": t, "id": by_title.get(t.lower())} for t in links_in(note["body"])]
    title = (row["title"] or "").strip().lower()
    note["backlinks"] = [
        {"id": o["id"], "title": o["title"]}
        for o in others if title in {t.lower() for t in links_in(o["body"] or "")}
    ]
    return note


def _clean(title: str, topic: str | None, body: str) -> tuple[str, str, str]:
    title = re.sub(r"\s+", " ", title or "").strip()[:200]
    if not title:
        raise NoteError("A note needs a title")
    if len(body or "") > MAX_BODY:
        raise NoteError("That note is too long")
    return title, (topic or "").strip()[:120] or title, body or ""


def create_note(user_id: int, title: str, topic: str | None = None, body: str = "") -> dict:
    title, topic, body = _clean(title, topic, body)
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (user_id, filename, file_type, title, topic, body, chunk_count,
                                      summary_status, created_at, updated_at)
               VALUES (?, ?, 'note', ?, ?, ?, 0, 'empty', ?, ?)""",
            (user_id, f"{title}.md", title, topic, body, now, now),
        )
        note_id = cur.lastrowid
    _sync_chunks(user_id, note_id, title, topic, body)
    return get_note(user_id, note_id)


def update_note(user_id: int, note_id: int, title: str, topic: str | None, body: str) -> dict:
    _note_row(user_id, note_id)
    title, topic, body = _clean(title, topic, body)
    with get_db() as conn:
        conn.execute(
            "UPDATE documents SET title = ?, topic = ?, body = ?, filename = ?, updated_at = ? WHERE id = ?",
            (title, topic, body, f"{title}.md", datetime.utcnow().isoformat(), note_id),
        )
    sync = _sync_chunks(user_id, note_id, title, topic, body)
    return {**get_note(user_id, note_id), "sync": sync}


def find_by_title(user_id: int, title: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM documents WHERE user_id = ? AND file_type = 'note' AND LOWER(title) = LOWER(?)",
            (user_id, title.strip()),
        ).fetchone()
    return row["id"] if row else None


async def assist(user_id: int, action: str, text: str, note_id: int | None = None) -> dict:
    """AI help on a selection: continue / simplify / explain / summarize text, or make flashcards."""
    text = (text or "").strip()
    if not text:
        raise NoteError("Select some text first")
    if action == "flashcards":
        topic = _note_row(user_id, note_id)["topic"] if note_id else "Notes"
        try:
            raw = await llm.complete([{"role": "user", "content": f"Notes:\n{text[:6000]}\n\nWrite flashcards."}],
                                     system=GENERATE_SYSTEM, json_mode=True)
            data = json.loads(_extract_json(raw))
        except llm.LLMError as e:
            raise NoteError(f"AI unavailable: {e}") from e
        except json.JSONDecodeError as e:
            raise NoteError("The AI returned an unreadable answer, please try again") from e
        cards = data.get("cards") if isinstance(data, dict) else data
        created = create_cards(user_id, topic, [c for c in cards or [] if isinstance(c, dict)][:15], note_id)
        return {"action": action, "created": len(created)}
    if action not in ASSIST_PROMPTS:
        raise NoteError("Unknown action")
    try:
        out = await llm.complete([{"role": "user", "content": text[:8000]}],
                                 system=f"{ASSIST_PROMPTS[action]} {HUMAN_STYLE_RULE}")
    except llm.LLMError as e:
        raise NoteError(f"AI unavailable: {e}") from e
    return {"action": action, "text": out.strip()}
