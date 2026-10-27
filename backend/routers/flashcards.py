import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services import card_types, flashcards
from services.document_processor import IMAGE_TYPES

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])

USER_ID = 1
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class GenerateBody(BaseModel):
    topic: str | None = None
    document_id: int | None = None
    count: int = Field(default=10, ge=1, le=30)


class CardBody(BaseModel):
    topic: str = Field(min_length=1, max_length=120)
    front: str = Field(min_length=1, max_length=1000)
    back: str = Field(min_length=1, max_length=4000)


class UpdateBody(BaseModel):
    front: str | None = None
    back: str | None = None


class ReviewBody(BaseModel):
    grade: int = Field(ge=0, le=5)


@router.get("")
def list_cards(topic: str | None = None):
    return flashcards.list_cards(USER_ID, topic)


@router.get("/due")
def due(limit: int = 20, topic: str | None = None):
    return flashcards.due_cards(USER_ID, min(max(limit, 1), 100), topic)


@router.get("/stats")
def stats():
    return flashcards.flashcard_stats(USER_ID)


@router.post("/generate")
async def generate(body: GenerateBody):
    try:
        cards = await flashcards.generate_cards(USER_ID, body.topic, body.document_id, body.count)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"created": cards}


class FromHighlightsBody(BaseModel):
    document_id: int
    marker_ids: list[int] | None = None


@router.post("/from-highlights")
async def from_highlights(body: FromHighlightsBody):
    try:
        return await flashcards.cards_from_highlights(USER_ID, body.document_id, body.marker_ids)
    except ValueError as e:
        raise HTTPException(404, str(e))


class ClozeBody(BaseModel):
    topic: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=5, max_length=4000)
    extra: str = Field(default="", max_length=4000)


class SuggestBody(BaseModel):
    text: str = Field(min_length=5, max_length=4000)


@router.post("/cloze")
def create_cloze(body: ClozeBody):
    try:
        return card_types.create_cloze(USER_ID, body.topic, body.text, body.extra)
    except card_types.CardError as e:
        raise HTTPException(400, str(e))


@router.post("/cloze/suggest")
async def suggest_cloze(body: SuggestBody):
    return await card_types.suggest_cloze(body.text)


@router.post("/occlusion")
async def create_occlusion(
    file: UploadFile = File(...),
    topic: str = Form(...),
    masks: str = Form(...),
    header: str = Form(""),
):
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_TYPES:
        raise HTTPException(400, f"Upload an image ({', '.join(IMAGE_TYPES)})")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image too large (max 10MB)")
    try:
        return card_types.create_occlusion(USER_ID, topic, data, ext, json.loads(masks), header)
    except (card_types.CardError, json.JSONDecodeError) as e:
        raise HTTPException(400, str(e))


@router.get("/images/{name}")
def card_image(name: str):
    path = card_types.image_path(name)
    if not path:
        raise HTTPException(404, "Image not found")
    return FileResponse(path)


@router.post("")
def create(body: CardBody):
    return flashcards.create_cards(USER_ID, body.topic.strip(), [body.model_dump()])


@router.post("/{card_id}/review")
def review(card_id: int, body: ReviewBody):
    card = flashcards.review_card(USER_ID, card_id, body.grade)
    if not card:
        raise HTTPException(404, "Card not found")
    return card


@router.put("/{card_id}")
def update(card_id: int, body: UpdateBody):
    flashcards.update_card(USER_ID, card_id, body.front, body.back)
    return {"ok": True}


@router.delete("/{card_id}")
def delete(card_id: int):
    flashcards.delete_card(USER_ID, card_id)
    return {"ok": True}
