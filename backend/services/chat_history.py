import json
from datetime import datetime

from database import get_db, row_to_dict

TITLE_LENGTH = 60


def _now() -> str:
    return datetime.utcnow().isoformat()


def create_session(user_id: int, kind: str, first_message: str) -> int:
    title = first_message.strip().replace("\n", " ")
    if len(title) > TITLE_LENGTH:
        title = title[: TITLE_LENGTH - 1].rstrip() + "…"
    now = _now()
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO chat_sessions (user_id, kind, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, title or "New chat", now, now),
        )
        return cur.lastrowid


def get_session(user_id: int, session_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
        ).fetchone()
    return row_to_dict(row)


def list_sessions(user_id: int, kind: str | None = None) -> list[dict]:
    sql = """SELECT s.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count
             FROM chat_sessions s WHERE s.user_id = ?"""
    params: list = [user_id]
    if kind:
        sql += " AND s.kind = ?"
        params.append(kind)
    sql += " ORDER BY s.updated_at DESC"
    with get_db() as conn:
        return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def get_messages(session_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, role, content, sources_json, cards_json, grounding_json, created_at
               FROM chat_messages WHERE session_id = ? ORDER BY id""",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["sources"] = json.loads(d.pop("sources_json") or "[]")
        d["cards"] = json.loads(d.pop("cards_json") or "[]")
        d["grounding"] = json.loads(d.pop("grounding_json") or "null")
        out.append(d)
    return out


def history_for_llm(session_id: int) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in get_messages(session_id)]


def add_message(
    session_id: int, role: str, content: str, sources: list[dict] | None = None, cards: list[dict] | None = None
) -> int:
    now = _now()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO chat_messages (session_id, role, content, sources_json, cards_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, json.dumps(sources) if sources else None,
             json.dumps(cards) if cards else None, now),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        return cur.lastrowid


def latest_assistant_message(session_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    d = row_to_dict(row)
    d["sources"] = json.loads(d.pop("sources_json") or "[]")
    return d


def save_grounding(message_id: int, grounding: dict):
    with get_db() as conn:
        conn.execute("UPDATE chat_messages SET grounding_json = ? WHERE id = ?", (json.dumps(grounding), message_id))


def rename_session(user_id: int, session_id: int, title: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
            (title.strip()[:120] or "Untitled", session_id, user_id),
        )


def delete_session(user_id: int, session_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
