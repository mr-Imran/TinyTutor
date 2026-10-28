"""Token usage per provider, model and feature, with estimated cost and a monthly budget.

Every LLM call is recorded by token_log.log_usage. The feature comes from a context variable
that a middleware sets from the request path, so background tasks started by a request (summaries,
embeddings, transcription) are counted toward the feature that started them.
"""
import json
import sqlite3
from contextvars import ContextVar
from datetime import date, datetime, timedelta

from database import get_db
from services.settings_store import get_setting, set_setting

current_feature: ContextVar[str] = ContextVar("current_feature", default="other")

# Request path prefix -> feature label shown on the usage page. First match wins.
FEATURE_PREFIXES = [
    ("/api/chat/agent", "agent"),
    ("/api/chat", "tutor"),
    ("/api/study", "mentor"),
    ("/api/quiz", "quiz"),
    ("/api/math", "quiz"),
    ("/api/mock-exams", "mock_exam"),
    ("/api/flashcards", "flashcards"),
    ("/api/documents", "documents"),
    ("/api/notes", "notes"),
    ("/api/exam-tools", "exam_hub"),
    ("/api/grading", "grading"),
    ("/api/misconceptions", "misconceptions"),
    ("/api/knowledge", "knowledge_graph"),
    ("/api/search", "search"),
    ("/api/settings", "settings"),
]

PRICES_KEY = "llm_prices"
BUDGET_KEY = "monthly_budget_usd"
WARN_AT = 0.8


def feature_for_path(path: str) -> str:
    for prefix, feature in FEATURE_PREFIXES:
        if path.startswith(prefix):
            return feature
    return "other"


class FeatureMiddleware:
    """Pure ASGI middleware, so the context variable is visible to background tasks too."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = current_feature.set(feature_for_path(scope.get("path", "")))
        try:
            await self.app(scope, receive, send)
        finally:
            current_feature.reset(token)


def record(provider: str, model: str, input_tokens: int, output_tokens: int):
    """Never raises: usage accounting must not break an AI answer."""
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO llm_usage (created_at, provider, model, feature, input_tokens, output_tokens)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.utcnow().isoformat(), provider.split("/")[0], model or "", current_feature.get(),
                 input_tokens, output_tokens),
            )
    except sqlite3.Error:
        pass


# ---------------------------------------------------------------- prices

def get_prices() -> dict[str, dict]:
    """{model: {"input": usd per 1M tokens, "output": usd per 1M tokens}}, entered by the user.

    No prices ship with the app: they change often, and a wrong default is worse than none.
    Local models (Ollama) are always free.
    """
    try:
        data = json.loads(get_setting(PRICES_KEY, "{}") or "{}")
    except json.JSONDecodeError:
        return {}
    return {
        m: {"input": float(p.get("input", 0)), "output": float(p.get("output", 0))}
        for m, p in data.items() if isinstance(p, dict)
    }


def set_prices(prices: dict[str, dict]):
    clean = {
        m.strip(): {"input": max(float(p.get("input", 0)), 0.0), "output": max(float(p.get("output", 0)), 0.0)}
        for m, p in prices.items() if m.strip()
    }
    set_setting(PRICES_KEY, json.dumps(clean))


def _cost(provider: str, model: str, inp: int, out: int, prices: dict) -> float | None:
    if provider == "ollama":
        return 0.0
    p = prices.get(model)
    if not p:
        return None
    return (inp * p["input"] + out * p["output"]) / 1_000_000


def get_budget() -> float | None:
    try:
        value = float(get_setting(BUDGET_KEY, "") or 0)
    except ValueError:
        return None
    return value or None


def set_budget(value: float | None):
    set_setting(BUDGET_KEY, str(value) if value else "")


# ---------------------------------------------------------------- report

def _add(bucket: dict, inp: int, out: int, cost: float | None):
    bucket["input_tokens"] += inp
    bucket["output_tokens"] += out
    bucket["calls"] += 1
    if cost is None:
        bucket["unpriced_calls"] += 1
    else:
        bucket["cost"] += cost


def _empty(**extra) -> dict:
    return {**extra, "input_tokens": 0, "output_tokens": 0, "calls": 0, "cost": 0.0, "unpriced_calls": 0}


def usage_report(days: int = 30, today: date | None = None) -> dict:
    today = today or date.today()
    since = today - timedelta(days=days - 1)
    month_start = today.replace(day=1)
    first = min(since, month_start).isoformat()
    prices = get_prices()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT created_at, provider, model, feature, input_tokens, output_tokens FROM llm_usage WHERE created_at >= ?",
            (first,),
        ).fetchall()

    by_day = {(since + timedelta(days=i)).isoformat(): _empty(date=(since + timedelta(days=i)).isoformat())
              for i in range(days)}
    by_feature: dict[str, dict] = {}
    by_model: dict[tuple, dict] = {}
    total = _empty()
    month = _empty()
    for r in rows:
        day = r["created_at"][:10]
        cost = _cost(r["provider"], r["model"], r["input_tokens"], r["output_tokens"], prices)
        args = (r["input_tokens"], r["output_tokens"], cost)
        if day >= month_start.isoformat():
            _add(month, *args)
        if day < since.isoformat():
            continue
        _add(total, *args)
        if day in by_day:
            _add(by_day[day], *args)
        _add(by_feature.setdefault(r["feature"], _empty(feature=r["feature"])), *args)
        key = (r["provider"], r["model"])
        _add(by_model.setdefault(key, _empty(provider=r["provider"], model=r["model"],
                                            priced=r["provider"] == "ollama" or r["model"] in prices)), *args)

    budget = get_budget()
    status = None
    if budget:
        share = month["cost"] / budget
        status = "over" if share >= 1 else "warning" if share >= WARN_AT else "ok"
    return {
        "days": days,
        "total": total,
        "month": month,
        "by_day": list(by_day.values()),
        "by_feature": sorted(by_feature.values(), key=lambda b: -(b["input_tokens"] + b["output_tokens"])),
        "by_model": sorted(by_model.values(), key=lambda b: -(b["input_tokens"] + b["output_tokens"])),
        "prices": prices,
        "budget": budget,
        "budget_status": status,
    }
