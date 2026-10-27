import json

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from config import UPLOAD_DIR
from database import get_db, row_to_dict
from services.document_processor import process_upload
from services.summaries import summarize_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

USER_ID = 1


def _doc_out(row) -> dict:
    d = row_to_dict(row)
    d["concepts"] = json.loads(d["concepts_json"]) if d.get("concepts_json") else []
    d.pop("concepts_json", None)
    return d


@router.post("/upload")
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No filename")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 25MB)")
    try:
        result = process_upload(USER_ID, file.filename, content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result["empty"]:
        background.add_task(summarize_document, result["document_id"])
    return result


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


@router.delete("/{doc_id}")
def delete_document(doc_id: int):
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
        (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
    return {"ok": True}
