import json
import logging

from database import get_db
from services import llm
from services.ai import _extract_json
from services.text_style import humanize_text

logger = logging.getLogger(__name__)

SAMPLE_CHUNKS = 8
MAX_CONCEPTS = 8

SYSTEM = (
    "You summarise study material for a student. Return ONLY valid JSON, no markdown. Schema: "
    '{"summary":"4-6 plain sentences covering the main ideas",'
    '"concepts":[{"term":"key term","definition":"one short sentence",'
    '"related":["other key terms from this list it connects to"]}]}. '
    f"Give at most {MAX_CONCEPTS} concepts, most important first."
)


def _sample_chunks(document_id: int) -> list[str]:
    """Evenly spaced chunks so long documents are covered start to end."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT content FROM knowledge_chunks WHERE document_id = ? ORDER BY id",
            (document_id,),
        ).fetchall()
    if len(rows) <= SAMPLE_CHUNKS:
        return [r["content"] for r in rows]
    step = len(rows) / SAMPLE_CHUNKS
    return [rows[int(i * step)]["content"] for i in range(SAMPLE_CHUNKS)]


def _set_status(document_id: int, status: str, summary: str | None = None, concepts: list | None = None):
    with get_db() as conn:
        conn.execute(
            "UPDATE documents SET summary_status = ?, summary = COALESCE(?, summary), "
            "concepts_json = COALESCE(?, concepts_json) WHERE id = ?",
            (status, summary, json.dumps(concepts) if concepts is not None else None, document_id),
        )


def parse_summary(raw: str) -> tuple[str, list[dict]]:
    data = json.loads(_extract_json(raw))
    summary = humanize_text(str(data.get("summary", "")).strip())
    terms = []
    for c in data.get("concepts") or []:
        if isinstance(c, dict) and str(c.get("term", "")).strip():
            terms.append(
                {
                    "term": str(c["term"]).strip(),
                    "definition": str(c.get("definition", "")).strip(),
                    "related": [str(r).strip() for r in (c.get("related") or []) if str(r).strip()],
                }
            )
    terms = terms[:MAX_CONCEPTS]
    known = {t["term"].lower() for t in terms}
    for t in terms:  # keep only links that point at another concept on the map
        t["related"] = [r for r in t["related"] if r.lower() in known and r.lower() != t["term"].lower()]
    if not summary:
        raise ValueError("empty summary")
    return summary, terms


async def summarize_document(document_id: int) -> None:
    chunks = _sample_chunks(document_id)
    if not chunks:
        _set_status(document_id, "empty")
        return
    _set_status(document_id, "running")
    prompt = "Study material excerpts:\n\n" + "\n\n---\n\n".join(c[:900] for c in chunks)
    try:
        raw = await llm.complete([{"role": "user", "content": prompt}], system=SYSTEM, json_mode=True)
        summary, concepts = parse_summary(raw)
    except (llm.LLMError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.warning("Summary failed for document %s: %s", document_id, e)
        _set_status(document_id, "failed")
        return
    _set_status(document_id, "done", summary, concepts)
