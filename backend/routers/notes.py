from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from services import notes
from services.embeddings import index_document_quietly

router = APIRouter(prefix="/api/notes", tags=["notes"])

USER_ID = 1


class NoteBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str | None = Field(default=None, max_length=120)
    body: str = Field(default="", max_length=notes.MAX_BODY)


class AssistBody(BaseModel):
    action: str
    text: str = Field(min_length=1, max_length=20000)
    note_id: int | None = None


@router.get("")
def list_notes():
    return notes.list_notes(USER_ID)


@router.post("")
def create(body: NoteBody, background: BackgroundTasks):
    try:
        note = notes.create_note(USER_ID, body.title, body.topic, body.body)
    except notes.NoteError as e:
        raise HTTPException(400, str(e))
    background.add_task(index_document_quietly, USER_ID, note["id"])
    return note


@router.get("/by-title")
def by_title(title: str):
    note_id = notes.find_by_title(USER_ID, title)
    if note_id is None:
        raise HTTPException(404, "No note with that title")
    return notes.get_note(USER_ID, note_id)


@router.get("/{note_id}")
def get(note_id: int):
    try:
        return notes.get_note(USER_ID, note_id)
    except notes.NoteError as e:
        raise HTTPException(404, str(e))


@router.put("/{note_id}")
def update(note_id: int, body: NoteBody, background: BackgroundTasks):
    try:
        note = notes.update_note(USER_ID, note_id, body.title, body.topic, body.body)
    except notes.NoteError as e:
        raise HTTPException(400 if "found" not in str(e) else 404, str(e))
    if note["sync"]["added"]:
        background.add_task(index_document_quietly, USER_ID, note_id)
    return note


@router.post("/assist")
async def assist(body: AssistBody):
    try:
        return await notes.assist(USER_ID, body.action, body.text, body.note_id)
    except notes.NoteError as e:
        raise HTTPException(400, str(e))
