import json
import re
from typing import AsyncIterator

from services import llm
from services.search import CONTEXT_MATCH_THRESHOLD, hybrid_search, search_chunks, search_chunks_scored
from services.text_style import HUMAN_STYLE_RULE, humanize_text

CITE_RULE = (
    "The notes are numbered. When you use a note, cite it right after the sentence "
    "with its number in square brackets, like [1] or [2][3]. Never invent numbers."
)

# kind -> (persona, label for the student's message, number of chunks to retrieve)
CHAT_PERSONAS = {
    "tutor": (
        "You are a friendly study tutor. Explain simply using the provided notes. "
        "If notes are missing, say so briefly. Keep answers concise.",
        "Student question",
        5,
    ),
    "mentor": (
        "You are a personal AI mentor helping a student prepare for exams. "
        "Use their study materials when available. Be warm, clear, and practical.",
        "Student says",
        6,
    ),
}

# How many earlier messages from a chat session are sent along as context.
HISTORY_MESSAGES = 6


def _system_for(system: str, json_mode: bool) -> str:
    if json_mode:
        return system
    return f"{system}\n\n{HUMAN_STYLE_RULE}" if system else HUMAN_STYLE_RULE


async def llm_chat(
    prompt: str,
    system: str = "",
    json_mode: bool = False,
    history: list[dict] | None = None,
    errors: list[str] | None = None,
) -> str:
    """Never raises: on failure returns a friendly message (and appends to `errors` if given)."""
    cfg = llm.get_llm_config()
    messages = (history or []) + [{"role": "user", "content": prompt}]
    try:
        text = await llm.complete(messages, system=_system_for(system, json_mode), json_mode=json_mode, cfg=cfg)
    except llm.LLMError as e:
        if errors is not None:
            errors.append(str(e))
        return f"Sorry, I cannot reach the AI right now. {llm.offline_hint(cfg)} ({e})"
    return text if json_mode else humanize_text(text)


async def llm_chat_stream(
    prompt: str,
    system: str = "",
    history: list[dict] | None = None,
    errors: list[str] | None = None,
) -> AsyncIterator[str]:
    cfg = llm.get_llm_config()
    messages = (history or []) + [{"role": "user", "content": prompt}]
    try:
        async for chunk in llm.stream(messages, system=_system_for(system, False), cfg=cfg):
            yield chunk
    except llm.LLMError as e:
        if errors is not None:
            errors.append(str(e))
        yield f"Sorry, the AI is offline. {llm.offline_hint(cfg)} ({e})"


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No study materials uploaded yet."
    parts = []
    for i, ch in enumerate(chunks, 1):
        where = ch.get("source") or "notes"
        if ch.get("page_number"):
            where += f", page {ch['page_number']}"
        elif ch.get("start_seconds") is not None:
            where += f", at {ch['start_seconds'] // 60}:{ch['start_seconds'] % 60:02d}"
        parts.append(f"[{i}] Topic: {ch.get('topic', 'General')} ({where})\n{ch['content'][:800]}")
    return "\n\n".join(parts)


def source_refs(chunks: list[dict]) -> list[dict]:
    """Citation targets matching the [n] numbers used in build_context."""
    return [
        {
            "n": i,
            "chunk_id": ch.get("id"),
            "document_id": ch.get("document_id"),
            "title": ch.get("title"),
            "source": ch.get("source"),
            "page_number": ch.get("page_number"),
            "file_type": ch.get("file_type"),
            "source_url": ch.get("source_url"),
            "start_seconds": ch.get("start_seconds"),
            "preview": (ch.get("content") or "")[:240],
        }
        for i, ch in enumerate(chunks, 1)
    ]


async def prepare_chat(
    user_id: int, kind: str, message: str, topic: str | None = None, history: list[dict] | None = None
) -> tuple[str, str, list[dict], list[dict]]:
    """Returns (prompt, system, history, sources) for a tutor or mentor turn."""
    from services import grounding

    persona, label, limit = CHAT_PERSONAS[kind]
    chunks = await hybrid_search(user_id, message, topic=topic, limit=limit)
    history = (history or [])[-HISTORY_MESSAGES:]
    # Follow-ups ("and why?") lean on the conversation, so only the first question is gated.
    if chunks and not history and grounding.settings()["enabled"] and not grounding.coverage(message, chunks)["covered"]:
        return f"{label}: {message}", f"{persona} {grounding.NOT_COVERED_RULE}", history, []
    prompt = f"Study notes:\n{build_context(chunks)}\n\n{label}: {message}"
    system = f"{persona} {CITE_RULE}" if chunks else persona
    return prompt, system, history, source_refs(chunks)


async def chat_reply(
    user_id: int, kind: str, message: str, topic: str | None = None, history: list[dict] | None = None
) -> dict:
    prompt, system, history, sources = await prepare_chat(user_id, kind, message, topic, history)
    errors: list[str] = []
    reply = await llm_chat(prompt, system=system, history=history, errors=errors)
    return {"reply": reply, "sources": sources, "failed": bool(errors)}


async def generate_quiz_question(
    user_id: int,
    topic: str,
    question_type: str,
    difficulty: str,
) -> dict:
    chunks = search_chunks(user_id, topic, topic=topic, limit=4)
    context = build_context(chunks)

    system = (
        "Return ONLY valid JSON, no markdown. Schema: "
        '{"question":"...","options":["A","B","C","D"] or null for short answer,'
        '"correct_answer":"...","explanation":"..."}. '
        "Write math in LaTeX between dollar signs, like $x^2$. For a math short answer, "
        "make correct_answer just the value or expression, like 3/4 or 2x+1."
    )
    type_hint = {
        "mcq": "multiple choice with exactly 4 options",
        "true_false": "true/false question, options must be [\"True\",\"False\"]",
        "short_answer": "short answer question, options null",
    }.get(question_type, "mcq")

    prompt = (
        f"Create one {difficulty} {type_hint} question about topic: {topic}\n"
        f"Based on:\n{context}\n"
        "JSON only."
    )
    raw = await llm_chat(prompt, system=system, json_mode=True)
    return _parse_quiz_json(raw, topic, question_type, difficulty)


async def evaluate_answer(
    question: str,
    correct_answer: str,
    user_answer: str,
    question_type: str,
) -> dict:
    if question_type in ("mcq", "true_false"):
        is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
        return {"is_correct": is_correct, "feedback": "Correct!" if is_correct else f"Correct answer: {correct_answer}"}

    from services.math_check import equivalent

    same = equivalent(user_answer, correct_answer)
    if same is not None:  # both are math: algebra decides, no AI needed
        return {
            "is_correct": same,
            "feedback": "Correct! Your answer is equivalent to the expected one (checked with algebra)." if same
            else f"Not equivalent to the expected answer ({correct_answer}), checked with algebra.",
            "checked_by": "algebra",
        }

    system ="Reply with JSON only: {\"is_correct\":true/false,\"feedback\":\"brief explanation\"}"
    prompt = (
        f"Question: {question}\nExpected: {correct_answer}\nStudent: {user_answer}\n"
        "Grade generously if meaning matches."
    )
    raw = await llm_chat(prompt, system=system, json_mode=True)
    try:
        data = json.loads(_extract_json(raw))
        return {
            "is_correct": bool(data.get("is_correct")),
            "feedback": humanize_text(data.get("feedback", "")),
        }
    except (json.JSONDecodeError, TypeError):
        is_correct = user_answer.strip().lower() in correct_answer.strip().lower()
        return {"is_correct": is_correct, "feedback": "Graded with simple match."}


def _extract_json(text: str) -> str:
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else text


def _chunks_matched(chunks: list[dict]) -> bool:
    if not chunks:
        return False
    return chunks[0].get("match_score", 0) >= CONTEXT_MATCH_THRESHOLD


async def generate_broad_question(
    user_id: int,
    topic: str,
    difficulty: str = "medium",
) -> dict:
    """Auto-generate an open-ended question from knowledge chunks."""
    chunks = search_chunks(user_id, topic, topic=topic, limit=4)
    context = build_context(chunks)

    system = (
        'Return ONLY valid JSON: {"question":"one clear open-ended exam question"}. '
        "No markdown. Question should need a written paragraph answer (explain, describe, why, compare)."
    )
    prompt = (
        f"Topic: {topic}\nDifficulty: {difficulty}\n"
        f"Study material:\n{context}\n\n"
        "Write one broad question a student can answer in their own words."
    )
    raw = await llm_chat(prompt, system=system, json_mode=True)
    try:
        data = json.loads(_extract_json(raw))
        question = str(data.get("question", "")).strip()
    except (json.JSONDecodeError, TypeError):
        question = ""

    if not question:
        question = f"Explain the main ideas of {topic} in your own words."

    return {"question": question, "topic": topic, "difficulty": difficulty}


async def check_broad_answer(
    user_id: int,
    question: str,
    user_answer: str,
    topic: str | None = None,
) -> dict:
    """Compare broad answer against knowledge chunks."""
    query = f"{question} {user_answer}"
    chunks = search_chunks_scored(user_id, query, topic=topic, limit=5)
    matched = _chunks_matched(chunks)

    if not matched:
        return {
            "matched": False,
            "match_score": chunks[0].get("match_score", 0) if chunks else 0,
            "feedback": "Your answer doesn't match anything in your uploaded study materials yet.",
            "chunks": [],
            "is_correct": None,
        }

    context = build_context(chunks)
    system = (
        "Reply with JSON only: "
        '{"is_correct":true/false,"feedback":"short encouraging feedback",'
        '"alignment":"strong|partial"}'
    )
    prompt = (
        f"Study notes:\n{context}\n\n"
        f"Question: {question}\n"
        f"Student answer: {user_answer}\n"
        "Judge if the answer is reasonable based on the notes. Grade generously if the idea is right."
    )
    raw = await llm_chat(prompt, system=system, json_mode=True)
    try:
        data = json.loads(_extract_json(raw))
        return {
            "matched": True,
            "match_score": chunks[0].get("match_score", 0),
            "feedback": humanize_text(data.get("feedback", "Checked against your materials.")),
            "chunks": [{"title": c.get("title"), "topic": c.get("topic"), "source": c.get("source")} for c in chunks],
            "is_correct": bool(data.get("is_correct")),
            "alignment": data.get("alignment", "partial"),
        }
    except (json.JSONDecodeError, TypeError):
        return {
            "matched": True,
            "match_score": chunks[0].get("match_score", 0),
            "feedback": "Your answer relates to your study materials.",
            "chunks": [{"title": c.get("title"), "topic": c.get("topic"), "source": c.get("source")} for c in chunks],
            "is_correct": True,
            "alignment": "partial",
        }


async def generate_ai_help(
    user_id: int,
    question: str,
    user_answer: str | None = None,
    topic: str | None = None,
) -> dict:
    """Simple explanation with an easy example — uses chunks when available."""
    query = f"{question} {user_answer or ''}"
    chunks = search_chunks_scored(user_id, query, topic=topic, limit=5)
    matched = _chunks_matched(chunks)
    context = build_context(chunks) if matched else ""

    system = (
        "You are a kind tutor for students. Use very simple words. "
        "Give a simple explanation in 2-3 short paragraphs, then one easy real-life example, "
        "then one quick tip sentence. Write as plain flowing text, not markdown."
    )
    if user_answer:
        extra = f"\nThe student tried to answer: {user_answer}\nGently correct gaps if needed."
    else:
        extra = ""

    if matched:
        prompt = f"Study notes:\n{context}\n\nQuestion: {question}{extra}\nExplain using the notes first, then simplify."
    else:
        prompt = (
            f"Question: {question}{extra}\n"
            "This topic is NOT in the student's uploaded notes. "
            "Explain from general knowledge in the simplest way possible."
        )

    explanation = await llm_chat(prompt, system=system)
    return {
        "matched": matched,
        "question": question,
        "explanation": explanation,
        "chunks": [{"title": c.get("title"), "topic": c.get("topic"), "source": c.get("source")} for c in chunks[:3]],
    }


def _parse_quiz_json(raw: str, topic: str, question_type: str, difficulty: str) -> dict:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        data = {
            "question": f"Sample question about {topic}?",
            "options": ["A", "B", "C", "D"] if question_type == "mcq" else ["True", "False"],
            "correct_answer": "A" if question_type == "mcq" else "True",
            "explanation": "Could not parse AI response — fallback question.",
        }

    options = data.get("options")
    if question_type == "true_false":
        options = ["True", "False"]

    return {
        "topic": topic,
        "question_type": question_type,
        "difficulty": difficulty,
        "question": data.get("question", f"Question about {topic}?"),
        "options": options,
        "correct_answer": str(data.get("correct_answer", "")),
        "explanation": data.get("explanation", ""),
    }
