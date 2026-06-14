from fastapi import APIRouter, File, HTTPException, UploadFile

from database import get_db, row_to_dict
from services.document_processor import process_upload

router = APIRouter(prefix="/api/documents", tags=["documents"])

USER_ID = 1


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No filename")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 25MB)")
    try:
        result = process_upload(USER_ID, file.filename, content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@router.get("")
def list_documents():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
            (USER_ID,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.delete("/{doc_id}")
def delete_document(doc_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, USER_ID))
    return {"ok": True}
