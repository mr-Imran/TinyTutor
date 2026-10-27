from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import usage

router = APIRouter(prefix="/api/usage", tags=["usage"])


class Price(BaseModel):
    input: float = Field(ge=0, le=10000)
    output: float = Field(ge=0, le=10000)


class PricesBody(BaseModel):
    prices: dict[str, Price]


class BudgetBody(BaseModel):
    monthly_usd: float | None = Field(default=None, ge=0, le=1_000_000)


@router.get("")
def report(days: int = 30):
    return usage.usage_report(min(max(days, 1), 365))


@router.put("/prices")
def set_prices(body: PricesBody):
    usage.set_prices({m: p.model_dump() for m, p in body.prices.items()})
    return usage.usage_report()


@router.put("/budget")
def set_budget(body: BudgetBody):
    usage.set_budget(body.monthly_usd)
    return usage.usage_report()
