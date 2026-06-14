import json
import re
from typing import AsyncIterator

import httpx

from config import OLLAMA_MODEL, OLLAMA_URL
from services.search import CONTEXT_MATCH_THRESHOLD, search_chunks, search_chunks_scored
from services.text_style import HUMAN_STYLE_RULE, humanize_text
from services.token_log import log_ollama_usage


async def ollama_chat(prompt: str, system: str = "", json_mode: bool = False) -> str:
    messages = []
    sys = system
    if not json_mode and system:
        sys = f"{system}\n\n{HUMAN_STYLE_RULE}"
    elif not json_mode:
        sys = HUMAN_STYLE_RULE

    if sys:
        messages.append({"role": "system", "content": sys})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            log_ollama_usage("chat", OLLAMA_MODEL, data, stream=False)
            text = data["message"]["content"]
            return text if json_mode else humanize_text(text)
        except httpx.HTTPError as e:
            return f"Sorry, I cannot reach the AI right now. Please start Ollama and run: ollama pull {OLLAMA_MODEL}. ({e})"


async def ollama_chat_stream(prompt: str, system: str = "") -> AsyncIterator[str]:
    messages = []
    sys = f"{system}\n\n{HUMAN_STYLE_RULE}" if system else HUMAN_STYLE_RULE
    messages.append({"role": "system", "content": sys})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("done"):
                            log_ollama_usage("chat/stream", OLLAMA_MODEL, data, stream=True)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPError:
            yield "Sorry, the AI mentor is offline. Please start Ollama on your computer."


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No study materials uploaded yet."
    parts = []
    for i, ch in enumerate(chunks, 1):
        parts.append(f"[{i}] Topic: {ch.get('topic', 'General')}\n{ch['content'][:800]}")
    return "\n\n".join(parts)


async def tutor_chat(user_id: int, message: str, topic: str | None = None) -> dict:
    chunks = search_chunks(user_id, message, topic=topic, limit=5)
    context = build_context(chunks)

    system = (
        "You are a friendly study tutor. Explain simply using the provided notes. "
        "If notes are missing, say so briefly. Keep answers concise."
    )
    prompt = f"Study notes:\n{context}\n\nStudent question: {message}"
    reply = await ollama_chat(prompt, system=system)
    return {"reply": reply, "sources": [c.get("source", "") for c in chunks]}


async def tutor_chat_stream(user_id: int, message: str, topic: str | None = None) -> AsyncIterator[str]:
    chunks = search_chunks(user_id, message, topic=topic, limit=5)
    context = build_context(chunks)
    system = (
        "You are a friendly study tutor. Explain simply using the provided notes. "
        "If notes are missing, say so briefly. Keep answers concise."
    )
    prompt = f"Study notes:\n{context}\n\nStudent question: {message}"
    async for chunk in ollama_chat_stream(prompt, system=system):
        yield chunk


async def mentor_chat(user_id: int, message: str, topic: str | None = None) -> dict:
    chunks = search_chunks(user_id, message, topic=topic, limit=6)
    context = build_context(chunks)
    system = (
        "You are a personal AI mentor helping a student prepare for exams. "
        "Use their study materials when available. Be warm, clear, and practical."
    )
    prompt = f"Their study materials:\n{context}\n\nStudent says: {message}"
    reply = await ollama_chat(prompt, system=system)
    return {"reply": reply, "sources": [c.get("source", "") for c in chunks]}


async def mentor_chat_stream(user_id: int, message: str, topic: str | None = None) -> AsyncIterator[str]:
    chunks = search_chunks(user_id, message, topic=topic, limit=6)
    context = build_context(chunks)
    system = (
        "You are a personal AI mentor helping a student prepare for exams. "
        "Use their study materials when available. Be warm, clear, and practical."
    )
    prompt = f"Their study materials:\n{context}\n\nStudent says: {message}"
    async for chunk in ollama_chat_stream(prompt, system=system):
        yield chunk


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
        '"correct_answer":"...","explanation":"..."}'
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
    raw = await ollama_chat(prompt, system=system, json_mode=True)
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

    system = "Reply with JSON only: {\"is_correct\":true/false,\"feedback\":\"brief explanation\"}"
    prompt = (
        f"Question: {question}\nExpected: {correct_answer}\nStudent: {user_answer}\n"
        "Grade generously if meaning matches."
    )
    raw = await ollama_chat(prompt, system=system, json_mode=True)
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
    raw = await ollama_chat(prompt, system=system, json_mode=True)
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
    raw = await ollama_chat(prompt, system=system, json_mode=True)
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

    explanation = await ollama_chat(prompt, system=system)
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
