from fastapi import APIRouter

from services.search import hybrid_global_search

router = APIRouter(prefix="/api/search", tags=["search"])

USER_ID = 1


@router.get("")
async def search(q: str, limit: int = 20):
    return {"query": q, "results": await hybrid_global_search(USER_ID, q, min(max(limit, 1), 50))}
