import asyncio
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import UPLOAD_DIR
from database import get_db, row_to_dict
from services import transcription
from services.document_processor import process_upload, safe_filename
from services.embeddings import index_document_quietly
from services.importers import import_url
from services.summaries import summarize_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

USER_ID = 1


def _doc_out(row) -> dict:
    d = row_to_dict(row)
    d["concepts"] = json.loads(d["concepts_json"]) if d.get("concepts_json") else []
    d.pop("concepts_json", None)
    return d


class ImportUrlBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    topic: str | None = Field(default=None, max_length=120)


def _after_import(background: BackgroundTasks, result: dict) -> dict:
    """Summary and embeddings are built after the response so uploads stay fast."""
    if not result["empty"]:
        background.add_task(summarize_document, result["document_id"])
        background.add_task(index_document_quietly, USER_ID, result["document_id"])
    return result


def _save_media(file: UploadFile) -> str:
    """Stream a recording to disk (they can be far larger than documents). Returns the stored name."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{USER_ID}_{uuid.uuid4().hex[:8]}_{safe_filename(file.filename)}"
    path = UPLOAD_DIR / stored_name
    written = 0
    with open(path, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > transcription.MAX_MEDIA_BYTES:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(400, "Recording too large (max 1GB)")
            out.write(chunk)
    return stored_name


@router.post("/upload")
async def upload_document(
    background: BackgroundTasks, file: UploadFile = File(...), topic: str | None = Form(None)
):
    if not file.filename:
        raise HTTPException(400, "No filename")
    if transcription.is_media(file.filename):
        stored_name = await asyncio.to_thread(_save_media, file)
        result = transcription.create_media_document(USER_ID, file.filename, stored_name, topic)
        background.add_task(transcription.transcribe_document, USER_ID, result["document_id"])
        return result
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 25MB)")
    try:
        result = await process_upload(USER_ID, file.filename, content, topic=topic)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _after_import(background, result)


@router.post("/import-url")
async def import_from_url(background: BackgroundTasks, body: ImportUrlBody):
    try:
        result = await import_url(USER_ID, body.url, body.topic)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _after_import(background, result)


@router.get("")
def list_documents():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
            (USER_ID,),
        ).fetchall()
    return [_doc_out(r) for r in rows]


@router.get("/{doc_id}")
def get_document(doc_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, USER_ID)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return _doc_out(row)


@router.post("/{doc_id}/summarize")
async def resummarize(doc_id: int):
    get_document(doc_id)
    await summarize_document(doc_id)
    return get_document(doc_id)


@router.get("/{doc_id}/media")
def media(doc_id: int):
    """The original recording; FileResponse answers Range requests, so the player can seek."""
    doc = get_document(doc_id)
    if doc["file_type"] not in ("audio", "video") or not doc.get("stored_name"):
        raise HTTPException(404, "Not a recording")
    path = UPLOAD_DIR / doc["stored_name"]
    if not path.is_file():
        raise HTTPException(404, "Recording file is missing")
    return FileResponse(path, media_type=transcription.media_type(doc["filename"])[1])


@router.get("/{doc_id}/transcript")
def transcript(doc_id: int):
    get_document(doc_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, content, start_seconds FROM knowledge_chunks WHERE document_id = ? ORDER BY start_seconds, id",
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/{doc_id}/cancel-transcription")
def cancel_transcription(doc_id: int):
    if not transcription.cancel(USER_ID, doc_id):
        raise HTTPException(400, "Nothing is being transcribed for this document")
    return get_document(doc_id)


@router.post("/{doc_id}/transcribe")
def retry_transcription(doc_id: int, background: BackgroundTasks):
    doc = get_document(doc_id)
    if doc["file_type"] not in ("audio", "video"):
        raise HTTPException(400, "Not a recording")
    if doc["media_status"] in ("pending", "running"):
        raise HTTPException(400, "Already transcribing")
    with get_db() as conn:
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (doc_id,))
        conn.execute(
            "UPDATE documents SET media_status = 'pending', media_progress = 0, media_error = NULL, chunk_count = 0 "
            "WHERE id = ?",
            (doc_id,),
        )
    background.add_task(transcription.transcribe_document, USER_ID, doc_id)
    return get_document(doc_id)


@router.delete("/{doc_id}")
def delete_document(doc_id: int):
    transcription.cancel(USER_ID, doc_id)
    with get_db() as conn:
        row = conn.execute(
            "SELECT stored_name FROM documents WHERE id = ? AND user_id = ?", (doc_id, USER_ID)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM document_annotations WHERE document_id = ?", (doc_id,))
        conn.execute("UPDATE flashcards SET document_id = NULL WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    if row["stored_name"]:
        try:
            (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
        except OSError:  # Windows: a recording still open by a cancelled transcription
            pass
    return {"ok": True}
