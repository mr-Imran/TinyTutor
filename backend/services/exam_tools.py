import json
import re

from database import get_db, row_to_dict
from services.ai import build_context, ollama_chat
from services.quiz import get_strong_topics, get_weak_topics
from services.search import search_chunks
from services.study_plan import calculate_study_targets


def _chunks_for_docs(user_id: int, file_types: list[str] | None = None, name_hint: str = "") -> list[dict]:
    with get_db() as conn:
        q = "SELECT id, filename, file_type FROM documents WHERE user_id = ?"
        params: list = [user_id]
        if file_types:
            q += f" AND file_type IN ({','.join('?' * len(file_types))})"
            params.extend(file_types)
        docs = conn.execute(q, params).fetchall()

        doc_ids = []
        for d in docs:
            fn = (d["filename"] or "").lower()
            if name_hint and name_hint not in fn:
                continue
            doc_ids.append(d["id"])

        if not doc_ids:
            rows = conn.execute(
                "SELECT title, topic, content, source FROM knowledge_chunks WHERE user_id = ? LIMIT 30",
                (user_id,),
            ).fetchall()
        else:
            placeholders = ",".join("?" * len(doc_ids))
            rows = conn.execute(
                f"""SELECT title, topic, content, source FROM knowledge_chunks
                    WHERE user_id = ? AND document_id IN ({placeholders}) LIMIT 30""",
                [user_id, *doc_ids],
            ).fetchall()
    return [dict(r) for r in rows]


async def explain_selection(
    user_id: int, selected_text: str, question: str | None = None, language: str = "bn"
) -> dict:
    chunks = search_chunks(user_id, selected_text, limit=4)
    context = build_context(chunks)
    if language.lower().startswith("bn"):
        system = (
            "তুমি একজন সহায়ক শিক্ষক। খুব সংক্ষেপে সহজ বাংলায় বুঝিয়ে বলবে। "
            "একটি ছোট বাস্তব উদাহরণ দেবে। মার্কডাউন ব্যবহার করবে না।"
        )
        q = question or "হাইলাইট করা অংশটি সহজ বাংলায় ছোট করে বুঝিয়ে দাও, সাথে একটি ছোট উদাহরণ দাও।"
    else:
        system = "You are a helpful teacher. Explain briefly in easy words with one short example."
        q = question or "Explain this highlighted part briefly in simple words with one short example."
    prompt = (
        f"Study context:\n{context}\n\n"
        f"Highlighted text from PDF:\n{selected_text}\n\n"
        f"Student asks: {q}"
    )
    reply = await ollama_chat(prompt, system=system)
    return {"explanation": reply}


async def previous_question_analysis(user_id: int, topic: str | None = None) -> dict:
    chunks = _chunks_for_docs(user_id, file_types=["pdf"], name_hint="question")
    if len(chunks) < 3:
        chunks = _chunks_for_docs(user_id, file_types=["pdf"])
    if topic:
        chunks = [c for c in chunks if topic.lower() in (c.get("topic") or "").lower()] or chunks
    context = build_context(chunks[:15])
    system = "You analyze past exam question papers for students. Write in plain friendly sentences only."
    prompt = (
        f"Analyze these past questions and notes:\n{context}\n\n"
        "Tell the student: common question patterns, important topics that repeat, "
        "and how they should prepare. Keep it practical."
    )
    analysis = await ollama_chat(prompt, system=system)
    return {"analysis": analysis, "sources_used": len(chunks)}


async def ppt_analysis(user_id: int, topic: str | None = None) -> dict:
    chunks = _chunks_for_docs(user_id, file_types=["pptx"])
    if topic:
        chunks = [c for c in chunks if topic.lower() in (c.get("topic") or "").lower()] or chunks
    context = build_context(chunks[:15])
    system = "You summarize teacher presentation slides for exam prep. Plain conversational text only."
    prompt = (
        f"Teacher PPT content:\n{context}\n\n"
        "Summarize main points, likely exam focus areas, and what the student must memorize."
    )
    analysis = await ollama_chat(prompt, system=system)
    return {"analysis": analysis, "slides_sources": len(chunks)}


async def cq_generator(user_id: int, topic: str, count: int = 5) -> dict:
    chunks = search_chunks(user_id, topic, topic=topic, limit=8)
    context = build_context(chunks)
    system = (
        'Return ONLY JSON: {"questions":["q1","q2",...]}. '
        "Creative questions (CQ style) need short paragraph answers, not MCQ."
    )
    prompt = (
        f"Topic: {topic}\nMaterials:\n{context}\n\n"
        f"Create {count} creative exam questions (CQ) for university level."
    )
    raw = await ollama_chat(prompt, system=system, json_mode=True)
    try:
        data = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
        questions = data.get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        questions = [f"Explain the core ideas of {topic} with examples." for _ in range(count)]
    return {"topic": topic, "questions": questions[:count]}


async def exam_predictor(user_id: int, exam_type: str, topic: str | None = None) -> dict:
    chunks = search_chunks(user_id, topic or "", topic=topic, limit=12)
    weak = get_weak_topics(user_id, 5)
    weak_list = ", ".join(w["topic"] for w in weak) if weak else "none tracked yet"
    context = build_context(chunks)
    label = "midterm" if exam_type == "midterm" else "final"
    system = f"You predict likely {label} exam questions. Plain human language, no markdown."
    prompt = (
        f"Study materials:\n{context}\n\n"
        f"Weak topics: {weak_list}\n\n"
        f"Predict 8 to 10 likely {label} questions, why they matter, and quick prep tips."
    )
    prediction = await ollama_chat(prompt, system=system)
    return {"exam_type": label, "prediction": prediction, "topic": topic}


async def viva_simulator(user_id: int, topic: str, count: int = 5) -> dict:
    chunks = search_chunks(user_id, topic, topic=topic, limit=6)
    context = build_context(chunks)
    system = (
        'Return ONLY JSON: {"pairs":[{"question":"...","model_answer":"..."}]}. '
        "Viva oral exam style, short answers."
    )
    prompt = f"Topic: {topic}\nNotes:\n{context}\n\nCreate {count} viva Q and model answer pairs."
    raw = await ollama_chat(prompt, system=system, json_mode=True)
    try:
        data = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
        pairs = data.get("pairs", [])
    except (json.JSONDecodeError, AttributeError):
        pairs = [{"question": f"What is {topic}?", "model_answer": "Review your uploaded notes."}]
    return {"topic": topic, "pairs": pairs[:count]}


def calculate_cgpa(courses: list[dict]) -> dict:
    total_credits = 0.0
    total_points = 0.0
    for c in courses:
        credit = float(c.get("credit", 0))
        gp = float(c.get("grade_point", 0))
        if credit <= 0:
            continue
        total_credits += credit
        total_points += credit * gp
    cgpa = round(total_points / total_credits, 2) if total_credits else 0.0
    return {"cgpa": cgpa, "total_credits": total_credits}


def semester_dashboard(user_id: int) -> dict:
    with get_db() as conn:
        docs = conn.execute(
            "SELECT id, title, filename, file_type, topic, chunk_count FROM documents WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        doc_list = [row_to_dict(d) for d in docs]

    weak = get_weak_topics(user_id, 10)
    strong = get_strong_topics(user_id, 5)
    targets = calculate_study_targets(user_id)

    scores = []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT mastery_percentage FROM topic_scores WHERE user_id = ?", (user_id,)
        ).fetchall()
    readiness = round(sum(r["mastery_percentage"] for r in scores) / len(scores), 1) if scores else 0.0

    return {
        "readiness_score": readiness,
        "weak_topics": weak,
        "strong_topics": strong,
        "study_targets": targets,
        "documents": doc_list,
        "pdf_count": sum(1 for d in doc_list if d.get("file_type") == "pdf"),
        "ppt_count": sum(1 for d in doc_list if d.get("file_type") == "pptx"),
    }
