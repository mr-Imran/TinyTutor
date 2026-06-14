import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import UPLOAD_DIR
from database import get_db, row_to_dict
from services.exam_tools import (
    calculate_cgpa,
    cq_generator,
    exam_predictor,
    explain_selection,
    ppt_analysis,
    previous_question_analysis,
    semester_dashboard,
    viva_simulator,
)

router = APIRouter(prefix="/api/exam-tools", tags=["exam-tools"])

USER_ID = 1


class ExplainSelectionBody(BaseModel):
    selected_text: str
    question: str | None = None
    document_id: int | None = None
    language: str = "bn"


class TopicBody(BaseModel):
    topic: str
    count: int = Field(default=5, ge=1, le=15)


class CgpaBody(BaseModel):
    courses: list[dict]


class MarkerBody(BaseModel):
    document_id: int
    page_number: int | None = None
    marker_type: str = "highlight"
    color: str = "yellow"
    selected_text: str
    note: str | None = None


class SaveDocumentBody(BaseModel):
    title: str
    topic: str = "Saved Notes"
    content: str
    source: str = "Reader Save"


@router.get("/semester-dashboard")
def get_semester_dashboard():
    return semester_dashboard(USER_ID)


@router.post("/cgpa")
def cgpa_calc(body: CgpaBody):
    if not body.courses:
        raise HTTPException(400, "Add at least one course")
    return calculate_cgpa(body.courses)


@router.post("/previous-questions")
async def analyze_previous(topic: str | None = Query(None)):
    return await previous_question_analysis(USER_ID, topic)


@router.post("/ppt-analysis")
async def analyze_ppt(topic: str | None = Query(None)):
    return await ppt_analysis(USER_ID, topic)


@router.post("/cq-generate")
async def generate_cq(body: TopicBody):
    return await cq_generator(USER_ID, body.topic, body.count)


@router.post("/predict/midterm")
async def predict_midterm(topic: str | None = Query(None)):
    return await exam_predictor(USER_ID, "midterm", topic)


@router.post("/predict/final")
async def predict_final(topic: str | None = Query(None)):
    return await exam_predictor(USER_ID, "final", topic)


@router.post("/viva")
async def viva(body: TopicBody):
    return await viva_simulator(USER_ID, body.topic, body.count)


@router.post("/explain-selection")
async def explain_highlight(body: ExplainSelectionBody):
    if len(body.selected_text.strip()) < 3:
        raise HTTPException(400, "Select more text from the PDF")
    return await explain_selection(USER_ID, body.selected_text.strip(), body.question, body.language)


@router.get("/pdfs")
def list_pdfs():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, filename, topic, page_count FROM documents WHERE user_id = ? AND file_type = 'pdf'",
            (USER_ID,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.get("/documents")
def list_documents(file_type: str | None = Query(None)):
    with get_db() as conn:
        if file_type in ("pdf", "pptx"):
            rows = conn.execute(
                """SELECT id, title, filename, topic, file_type, page_count, chunk_count
                   FROM documents WHERE user_id = ? AND file_type = ? ORDER BY id DESC""",
                (USER_ID, file_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, title, filename, topic, file_type, page_count, chunk_count
                   FROM documents WHERE user_id = ? AND file_type IN ('pdf','pptx')
                   ORDER BY id DESC""",
                (USER_ID,),
            ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.get("/document/{doc_id}/chunks")
def get_document_chunks(doc_id: int):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, title, topic, content, source
               FROM knowledge_chunks WHERE user_id = ? AND document_id = ?
               ORDER BY id ASC""",
            (USER_ID, doc_id),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.get("/document/{doc_id}/markers")
def list_markers(doc_id: int):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, document_id, page_number, marker_type, color, selected_text, note, created_at
               FROM document_annotations WHERE user_id = ? AND document_id = ? ORDER BY id DESC""",
            (USER_ID, doc_id),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.post("/document/marker")
def save_marker(body: MarkerBody):
    if body.marker_type not in ("highlight", "underline", "note"):
        raise HTTPException(400, "marker_type must be highlight, underline, or note")
    if len(body.selected_text.strip()) < 2:
        raise HTTPException(400, "Selected text is too short")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO document_annotations
               (user_id, document_id, page_number, marker_type, color, selected_text, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                USER_ID,
                body.document_id,
                body.page_number,
                body.marker_type,
                body.color,
                body.selected_text.strip(),
                body.note,
            ),
        )
    return {"id": cur.lastrowid, "message": "Marker saved"}


@router.delete("/document/marker/{marker_id}")
def delete_marker(marker_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM document_annotations WHERE id = ? AND user_id = ?",
            (marker_id, USER_ID),
        )
    return {"ok": True}


@router.post("/save-document")
def save_document(body: SaveDocumentBody):
    if not body.content.strip():
        raise HTTPException(400, "Content is required")
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents
               (user_id, filename, file_type, title, topic, page_count, chunk_count, created_at)
               VALUES (?, ?, 'saved', ?, ?, 0, 1, datetime('now'))""",
            (USER_ID, f"saved_{body.title}.txt", body.title.strip(), body.topic.strip()),
        )
        document_id = cur.lastrowid
        conn.execute(
            """INSERT INTO knowledge_chunks
               (document_id, user_id, title, topic, content, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                document_id,
                USER_ID,
                body.title.strip(),
                body.topic.strip(),
                body.content.strip(),
                body.source,
            ),
        )
        conn.execute(
            "UPDATE documents SET chunk_count = 1 WHERE id = ?",
            (document_id,),
        )
    return {"document_id": document_id, "message": "Document saved"}


@router.get("/pdf/{doc_id}/file")
def serve_pdf(doc_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename FROM documents WHERE id = ? AND user_id = ? AND file_type = 'pdf'",
            (doc_id, USER_ID),
        ).fetchone()
    if not row:
        raise HTTPException(404, "PDF not found")
    safe = _safe_filename(row["filename"])
    path = UPLOAD_DIR / f"{USER_ID}_{safe}"
    if not path.exists():
        matches = list(UPLOAD_DIR.glob(f"{USER_ID}_*{Path(row['filename']).name}"))
        if not matches:
            raise HTTPException(404, "File missing on disk")
        path = matches[0]
    return FileResponse(path, media_type="application/pdf", filename=row["filename"])


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)
