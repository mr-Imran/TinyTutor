"""Agent mode for the tutor: the model can search notes and act (make flashcards, quizzes, read the plan).

run_agent() yields events for an NDJSON stream:
  {"type": "tool", "name", "label"}      a tool is running
  {"type": "card", "card": {...}}        something to show inline (flashcards made, a quiz, mastery)
  {"type": "delta", "text"}              streamed answer text (fallback mode)
  {"type": "text", "text"}               the full final answer (agent mode)
  {"type": "notice", "message"}          e.g. "this model cannot use tools"
  {"type": "error", "message"}
  {"type": "done", "sources": [...]}     citation targets for [n] markers
"""
import json
from datetime import date
from typing import AsyncIterator

from services import llm
from services.ai import CITE_RULE, build_context, llm_chat_stream, prepare_chat, source_refs
from services.search import hybrid_search
from services.text_style import HUMAN_STYLE_RULE, humanize_text

MAX_STEPS = 6
MAX_CARDS = 20
MAX_QUIZ = 5

SYSTEM = (
    "You are a friendly study tutor with tools. Use them instead of guessing: search the student's notes "
    "before answering questions about their material, read their mastery or plan when they ask what to "
    "study, and create flashcards or quizzes when they ask for practice. Do not call a tool when you can "
    "answer from the conversation. Quizzes are shown to the student as interactive cards, so never reveal "
    "the answers in your reply; just introduce the quiz. After creating flashcards, say how many were made. "
    f"Keep answers concise. {CITE_RULE} "
    f"{HUMAN_STYLE_RULE}"
)

TOOLS = [
    {
        "name": "search_notes",
        "description": "Search the student's uploaded study notes. Returns numbered excerpts to cite as [n].",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, in a few words"},
                "topic": {"type": "string", "description": "Optional topic name to search within"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_materials",
        "description": "List the student's study materials with their topics.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_mastery",
        "description": "Get the student's mastery percentage per topic, weakest first.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_study_plan",
        "description": "Get today's study plan tasks and which are done.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_misconceptions",
        "description": "Get the student's open misconceptions found from their wrong answers.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "create_flashcards",
        "description": "Create spaced-repetition flashcards about a topic from the student's notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic name, ideally one from list_materials"},
                "count": {"type": "integer", "description": f"How many cards, 1 to {MAX_CARDS}"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "create_quiz",
        "description": "Create practice questions on a topic. They are shown to the student as an interactive quiz.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "count": {"type": "integer", "description": f"How many questions, 1 to {MAX_QUIZ}"},
                "question_type": {"type": "string", "enum": ["mcq", "true_false", "short_answer"]},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            },
            "required": ["topic"],
        },
    },
]

TOOL_LABELS = {
    "search_notes": "Searching your notes",
    "list_materials": "Looking at your materials",
    "get_mastery": "Checking your mastery",
    "get_study_plan": "Reading today's plan",
    "get_misconceptions": "Checking your common mistakes",
    "create_flashcards": "Creating flashcards",
    "create_quiz": "Writing a quiz",
}


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


class AgentState:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.chunks: list[dict] = []  # cited notes, in citation order
        self.cards: list[dict] = []

    def number_chunks(self, chunks: list[dict]) -> list[dict]:
        """Give new chunks the next citation numbers; reuse numbers for chunks seen before."""
        known = {c["id"]: i for i, c in enumerate(self.chunks, 1)}
        out = []
        for ch in chunks:
            if ch["id"] not in known:
                self.chunks.append(ch)
                known[ch["id"]] = len(self.chunks)
            out.append((known[ch["id"]], ch))
        return out


async def run_tool(state: AgentState, name: str, args: dict) -> dict:
    """Returns the data the model sees. Cards for the UI are added to state.cards."""
    uid = state.user_id
    if name == "search_notes":
        query = str(args.get("query") or "").strip()
        if not query:
            return {"error": "query is required"}
        found = await hybrid_search(uid, query, topic=(args.get("topic") or None), limit=5)
        numbered = state.number_chunks(found)
        if not numbered:
            return {"notes": [], "message": "Nothing found in the student's notes."}
        context = build_context([ch for _, ch in numbered])
        # build_context numbers from 1; swap in the agent-wide citation numbers.
        for local, (n, _) in enumerate(numbered, 1):
            context = context.replace(f"[{local}] Topic:", f"[#{n}] Topic:", 1)
        return {"notes": context.replace("[#", "[")}

    if name == "list_materials":
        from database import get_db

        with get_db() as conn:
            rows = conn.execute(
                "SELECT title, topic, file_type FROM documents WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
                (uid,),
            ).fetchall()
        return {"materials": [dict(r) for r in rows]}

    if name == "get_mastery":
        from database import get_db
        from services.mastery import refresh_mastery

        refresh_mastery(uid)
        with get_db() as conn:
            rows = conn.execute(
                """SELECT topic, mastery_percentage, correct_answers + wrong_answers AS answers
                   FROM topic_scores WHERE user_id = ? ORDER BY mastery_percentage""",
                (uid,),
            ).fetchall()
        topics = [{"topic": r["topic"], "mastery": r["mastery_percentage"], "answers": r["answers"]} for r in rows]
        state.cards.append({"type": "mastery", "topics": topics[:8]})
        return {"topics": topics, "note": "Mastery is shown to the student as a card."}

    if name == "get_study_plan":
        from services.daily_plan import get_plan

        plan = get_plan(uid)
        tasks = [{"title": t["title"], "done": t["done"], "minutes": t["minutes"], "link": t["link"]}
                 for t in plan["tasks"]]
        state.cards.append({"type": "plan", "tasks": tasks})
        return {"date": plan["date"], "tasks": tasks}

    if name == "get_misconceptions":
        from services.misconceptions import list_misconceptions

        items = [m for m in list_misconceptions(uid) if m["status"] == "open"]
        return {"misconceptions": [
            {"topic": m["topic"], "title": m["title"], "description": m["description"], "correction": m["correction"]}
            for m in items
        ]}

    if name == "create_flashcards":
        from services.flashcards import generate_cards

        topic = str(args.get("topic") or "").strip()
        if not topic:
            return {"error": "topic is required"}
        count = _clamp(args.get("count"), 1, MAX_CARDS, 8)
        try:
            created = await generate_cards(uid, topic=topic, count=count)
        except ValueError as e:
            return {"error": str(e)}
        state.cards.append({
            "type": "flashcards", "topic": topic, "count": len(created),
            "cards": [{"front": c["front"], "back": c["back"]} for c in created[:5]],
        })
        return {"created": len(created), "topic": topic}

    if name == "create_quiz":
        from services.ai import generate_quiz_question

        topic = str(args.get("topic") or "").strip()
        if not topic:
            return {"error": "topic is required"}
        count = _clamp(args.get("count"), 1, MAX_QUIZ, 3)
        qtype = args.get("question_type") if args.get("question_type") in ("mcq", "true_false", "short_answer") else "mcq"
        difficulty = args.get("difficulty") if args.get("difficulty") in ("easy", "medium", "hard") else "medium"
        questions = [await generate_quiz_question(uid, topic, qtype, difficulty) for _ in range(count)]
        state.cards.append({"type": "quiz", "topic": topic, "questions": questions})
        return {"questions_shown": [q["question"] for q in questions]}

    return {"error": f"Unknown tool {name}"}


async def _fallback(user_id: int, message: str, topic: str | None, history: list[dict], result: dict):
    """Plain tutor turn for models without tool calling."""
    prompt, system, history, sources = await prepare_chat(user_id, "tutor", message, topic, history)
    errors: list[str] = []
    full = ""
    async for chunk in llm_chat_stream(prompt, system=system, history=history, errors=errors):
        full += chunk
        yield {"type": "delta", "text": chunk}
    result.update(text=humanize_text(full), sources=sources, failed=bool(errors))


async def run_agent(
    user_id: int, message: str, topic: str | None, history: list[dict], result: dict
) -> AsyncIterator[dict]:
    """Yields events; fills `result` with text, sources, cards and failed for the caller to save."""
    cfg = llm.get_llm_config()
    result.update(text="", sources=[], cards=[], failed=False)
    # None (unknown, e.g. Ollama not running) goes ahead, so an offline AI is reported as offline.
    if await llm.supports_tools(cfg) is False:
        yield {"type": "notice", "message": f"{cfg['model'] or cfg['provider']} cannot use tools, so this is a "
                                            "normal tutor answer. Pick a model with tool support for agent mode."}
        async for event in _fallback(user_id, message, topic, history, result):
            yield event
        yield {"type": "done", "sources": result["sources"]}
        return

    state = AgentState(user_id)
    system = SYSTEM + f" Today is {date.today().isoformat()}."
    if topic:
        system += f" The student is focusing on the topic: {topic}."
    transcript = list(history) + [{"role": "user", "content": message}]
    text = ""
    try:
        for step in range(MAX_STEPS + 1):
            # Last step: answer with what was found so far.
            turn = await llm.complete_with_tools(transcript, system, TOOLS, cfg, allow_calls=step < MAX_STEPS)
            transcript.append(turn["assistant"])
            text = turn["text"]
            if not turn["tool_calls"]:
                break
            for call in turn["tool_calls"]:
                yield {"type": "tool", "name": call["name"], "label": TOOL_LABELS.get(call["name"], call["name"])}
                cards_before = len(state.cards)
                try:
                    data = await run_tool(state, call["name"], call["args"] or {})
                except llm.LLMError as e:
                    data = {"error": f"AI unavailable: {e}"}
                for card in state.cards[cards_before:]:
                    yield {"type": "card", "card": card}
                transcript.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                                   "content": json.dumps(data, default=str)})
    except llm.LLMError as e:
        result["failed"] = True
        yield {"type": "error", "message": f"Sorry, the AI is offline. {llm.offline_hint(cfg)} ({e})"}
        return

    text = humanize_text(text) or "Done."
    sources = source_refs(state.chunks)
    result.update(text=text, sources=sources, cards=state.cards)
    yield {"type": "text", "text": text}
    yield {"type": "done", "sources": sources}
