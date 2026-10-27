from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import flashcards

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])

USER_ID = 1


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
