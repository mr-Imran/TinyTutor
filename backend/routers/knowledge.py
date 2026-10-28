from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import knowledge_graph as kg

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

USER_ID = 1


class LinkBody(BaseModel):
    source: str
    target: str
    kind: str = "prereq"


@router.get("/graph")
def graph():
    return kg.get_graph(USER_ID)


@router.post("/rebuild")
async def rebuild(use_ai: bool = True, force_ai: bool = False):
    return await kg.rebuild(USER_ID, use_ai=use_ai, force_ai=force_ai)


@router.get("/path")
def path(key: str):
    try:
        return kg.learning_path(USER_ID, key)
    except kg.GraphError as e:
        raise HTTPException(404, str(e))


@router.post("/links")
def add_link(body: LinkBody):
    try:
        kg.add_link(USER_ID, body.source, body.target, body.kind)
    except kg.GraphError as e:
        raise HTTPException(400, str(e))
    return kg.get_graph(USER_ID)


@router.delete("/links/{link_id}")
def remove_link(link_id: int):
    try:
        kg.remove_link(USER_ID, link_id)
    except kg.GraphError as e:
        raise HTTPException(404, str(e))
    return kg.get_graph(USER_ID)


@router.post("/links/{link_id}/flip")
def flip_link(link_id: int):
    try:
        kg.flip_link(USER_ID, link_id)
    except kg.GraphError as e:
        raise HTTPException(404, str(e))
    return kg.get_graph(USER_ID)
