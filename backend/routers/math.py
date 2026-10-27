import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import llm, math_check

router = APIRouter(prefix="/api/math", tags=["math"])


class SolveBody(BaseModel):
    problem: str = Field(min_length=2, max_length=2000)


class CheckBody(BaseModel):
    answer: str = Field(max_length=math_check.MAX_LEN)
    expected: str = Field(max_length=math_check.MAX_LEN)


@router.post("/solve")
async def solve(body: SolveBody):
    """Worked solution from the AI, with each algebra step checked by sympy."""
    try:
        return await math_check.solve(body.problem)
    except llm.LLMError as e:
        raise HTTPException(503, f"AI unavailable: {e}")
    except (json.JSONDecodeError, TypeError, AttributeError):
        raise HTTPException(502, "The AI returned an unreadable solution, please try again")


@router.post("/check")
def check(body: CheckBody):
    return {"equivalent": math_check.equivalent(body.answer, body.expected)}
