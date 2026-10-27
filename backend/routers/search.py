from fastapi import APIRouter

from services.search import global_search

router = APIRouter(prefix="/api/search", tags=["search"])

USER_ID = 1


@router.get("")
def search(q: str, limit: int = 20):
    return {"query": q, "results": global_search(USER_ID, q, min(max(limit, 1), 50))}
