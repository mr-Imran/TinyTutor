from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from services import data_transfer

router = APIRouter(prefix="/api/data", tags=["data"])

USER_ID = 1
MAX_RESTORE_BYTES = 500 * 1024 * 1024


def _download(content: bytes | str, filename: str, media_type: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/backup")
def backup():
    return _download(data_transfer.create_backup(), f"tinytutor-backup-{date.today()}.zip", "application/zip")


@router.post("/restore")
async def restore(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_RESTORE_BYTES:
        raise HTTPException(400, "Backup is larger than 500MB")
    try:
        return data_transfer.restore_backup(data)
    except data_transfer.DataError as e:
        raise HTTPException(400, str(e))


@router.get("/flashcards.csv")
def flashcards_csv(topic: str | None = None):
    return _download(data_transfer.flashcards_csv(USER_ID, topic), "tinytutor-flashcards.csv", "text/csv; charset=utf-8")


@router.get("/flashcards.apkg")
def flashcards_apkg(topic: str | None = None):
    try:
        content = data_transfer.flashcards_apkg(USER_ID, topic)
    except data_transfer.DataError as e:
        raise HTTPException(400, str(e))
    return _download(content, "tinytutor-flashcards.apkg", "application/octet-stream")


@router.post("/flashcards/import")
async def import_flashcards(file: UploadFile = File(...), topic: str = Form("Imported")):
    data = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".apkg") or name.endswith(".colpkg"):
            return data_transfer.import_flashcards_apkg(USER_ID, data, topic.strip() or "Imported")
        if name.endswith((".csv", ".txt", ".tsv")):
            text = data.decode("utf-8-sig", errors="replace")
            return data_transfer.import_flashcards_csv(USER_ID, text, topic.strip() or "Imported")
    except data_transfer.DataError as e:
        raise HTTPException(400, str(e))
    raise HTTPException(400, "Import a .csv, .txt or .apkg file")


@router.get("/quiz-history.csv")
def quiz_history_csv():
    return _download(data_transfer.quiz_history_csv(USER_ID), "tinytutor-quiz-history.csv", "text/csv; charset=utf-8")
