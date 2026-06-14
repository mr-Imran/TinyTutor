from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import DB_PATH
from database import get_db, row_to_dict

router = APIRouter(prefix="/api/db", tags=["database"])

USER_ID = 1

# Only these tables can be browsed (prevents SQL injection via table name)
ALLOWED_TABLES = [
    "users",
    "documents",
    "knowledge_chunks",
    "quiz_attempts",
    "topic_scores",
    "scheduled_questions",
]

MANUAL_FILENAME = "__manual_context__"


def _validate_table(table: str) -> str:
    if table not in ALLOWED_TABLES:
        raise HTTPException(404, f"Unknown table: {table}")
    return table


def _get_manual_document_id(conn) -> int:
    row = conn.execute(
        "SELECT id FROM documents WHERE user_id = ? AND filename = ?",
        (USER_ID, MANUAL_FILENAME),
    ).fetchone()
    if row:
        return row["id"]
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        """INSERT INTO documents (user_id, filename, file_type, title, topic, page_count, chunk_count, created_at)
           VALUES (?, ?, 'manual', 'Manual Context', 'General', 0, 0, ?)""",
        (USER_ID, MANUAL_FILENAME, now),
    )
    return cur.lastrowid


def _refresh_document_chunk_count(conn, document_id: int):
    count = conn.execute(
        "SELECT COUNT(*) as c FROM knowledge_chunks WHERE document_id = ?",
        (document_id,),
    ).fetchone()["c"]
    conn.execute("UPDATE documents SET chunk_count = ? WHERE id = ?", (count, document_id))


class AddContextBody(BaseModel):
    title: str = Field(default="Manual note", max_length=200)
    topic: str = Field(default="General", max_length=120)
    content: str = Field(min_length=1, max_length=50000)
    source: str = Field(default="Manual entry", max_length=200)


class UpdateChunkBody(BaseModel):
    title: str | None = None
    topic: str | None = None
    content: str | None = None
    source: str | None = None


@router.get("/overview")
def db_overview():
    with get_db() as conn:
        tables = []
        for name in ALLOWED_TABLES:
            count = conn.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()["c"]
            tables.append({"name": name, "row_count": count})
    return {"db_path": str(DB_PATH), "tables": tables}


@router.get("/tables/{table}")
def list_rows(
    table: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str = Query(""),
):
    table = _validate_table(table)
    with get_db() as conn:
        if table == "knowledge_chunks" and search.strip():
            q = f"%{search.strip()}%"
            total = conn.execute(
                """SELECT COUNT(*) as c FROM knowledge_chunks
                   WHERE user_id = ? AND (content LIKE ? OR topic LIKE ? OR title LIKE ?)""",
                (USER_ID, q, q, q),
            ).fetchone()["c"]
            rows = conn.execute(
                """SELECT * FROM knowledge_chunks
                   WHERE user_id = ? AND (content LIKE ? OR topic LIKE ? OR title LIKE ?)
                   ORDER BY id DESC LIMIT ? OFFSET ?""",
                (USER_ID, q, q, q, limit, offset),
            ).fetchall()
        elif table in ("documents", "knowledge_chunks", "quiz_attempts", "topic_scores", "scheduled_questions"):
            total = conn.execute(f"SELECT COUNT(*) as c FROM {table} WHERE user_id = ?", (USER_ID,)).fetchone()["c"]
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (USER_ID, limit, offset),
            ).fetchall()
        else:
            total = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

    return {
        "table": table,
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [row_to_dict(r) for r in rows],
    }


@router.get("/tables/{table}/{row_id}")
def get_row(table: str, row_id: int):
    table = _validate_table(table)
    with get_db() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Row not found")
    return row_to_dict(row)


@router.post("/context")
def add_context(body: AddContextBody):
    """Add a knowledge chunk manually — used by AI tutor search."""
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        doc_id = _get_manual_document_id(conn)
        cur = conn.execute(
            """INSERT INTO knowledge_chunks (document_id, user_id, title, topic, content, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, USER_ID, body.title.strip(), body.topic.strip(), body.content.strip(), body.source.strip(), now),
        )
        chunk_id = cur.lastrowid
        _refresh_document_chunk_count(conn, doc_id)

    return {"id": chunk_id, "document_id": doc_id, "message": "Context added"}


@router.put("/chunks/{chunk_id}")
def update_chunk(chunk_id: int, body: UpdateChunkBody):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_chunks WHERE id = ? AND user_id = ?",
            (chunk_id, USER_ID),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Chunk not found")

        title = body.title if body.title is not None else row["title"]
        topic = body.topic if body.topic is not None else row["topic"]
        content = body.content if body.content is not None else row["content"]
        source = body.source if body.source is not None else row["source"]

        conn.execute(
            "UPDATE knowledge_chunks SET title = ?, topic = ?, content = ?, source = ? WHERE id = ?",
            (title, topic, content, source, chunk_id),
        )
        _refresh_document_chunk_count(conn, row["document_id"])

    return {"ok": True}


@router.delete("/chunks/{chunk_id}")
def delete_chunk(chunk_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT document_id FROM knowledge_chunks WHERE id = ? AND user_id = ?",
            (chunk_id, USER_ID),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Chunk not found")
        doc_id = row["document_id"]
        conn.execute("DELETE FROM knowledge_chunks WHERE id = ?", (chunk_id,))
        _refresh_document_chunk_count(conn, doc_id)
    return {"ok": True}
