"""Rubric grading for long answers (typed or photographed) and the Feynman "teach it back" mode.

Grading runs at temperature 0 where the provider allows it, and every score comes with the rubric
it was marked against, so the student can see why. Results feed mastery like quiz answers do.
"""
import json
from datetime import datetime

from database import get_db, row_to_dict
from services import llm
from services.ai import _extract_json, build_context
from services.mastery import record_event
from services.quiz import touch_study_streak
from services.search import hybrid_search
from services.text_style import humanize_text

PASS_SHARE = 0.6
TEACH_BACK_PASS = 70
MAX_CRITERIA = 6
MAX_ANSWER_CHARS = 8000

RUBRIC_SYSTEM = (
    "You write marking rubrics for exam answers. Return ONLY valid JSON, no markdown: "
    '{"criteria":[{"name":"short name","description":"what earns full marks","points":2}]}. '
    f"Use 3 to {MAX_CRITERIA} criteria and 1 to 5 points each. Base them on the study notes when given."
)

GRADE_SYSTEM = (
    "You are a fair, encouraging examiner. Mark the student's answer against each rubric criterion. "
    "Return ONLY valid JSON, no markdown: "
    '{"criteria":[{"name":"criterion name","score":1,"max":2,"feedback":"one or two sentences",'
    '"evidence":[1]}],"overall_feedback":"2-3 sentences: strengths, then the most useful fix",'
    '"model_answer":"a short full-marks answer"}. '
    "score is between 0 and max. evidence lists the note numbers that back your marking. "
    "Do not reward length; reward correct, relevant content."
)

TEACH_BACK_SYSTEM = (
    "The student is explaining a concept in their own words, as if teaching a 12-year-old (the Feynman "
    "technique). Judge the explanation against the study notes. Return ONLY valid JSON, no markdown: "
    '{"score":0-100,"accuracy":0-100,"clarity":0-100,"completeness":0-100,'
    '"gaps":["important idea they left out"],'
    '"jargon":[{"term":"unexplained technical word","suggestion":"plain way to say it"}],'
    '"misconceptions":["anything stated that is wrong"],'
    '"follow_up_question":"one question a curious 12-year-old would ask next",'
    '"verdict":"2 warm sentences of feedback"}'
)

TRANSCRIBE_PROMPT = (
    "This is a photo of a student's handwritten exam answer. Transcribe the handwriting exactly as written, "
    "keeping line breaks, spelling mistakes and crossed-out words out. Write math in LaTeX between dollar "
    "signs. Output only the transcription."
)


class GradingError(Exception):
    pass


async def _json_call(system: str, prompt: str) -> dict:
    try:
        raw = await llm.complete([{"role": "user", "content": prompt}], system=system, json_mode=True, temperature=0)
        data = json.loads(_extract_json(raw))
    except llm.LLMError as e:
        raise GradingError(f"AI unavailable: {e}") from e
    except json.JSONDecodeError as e:
        raise GradingError("The AI returned an unreadable answer, please try again") from e
    if not isinstance(data, dict):
        raise GradingError("The AI returned an unreadable answer, please try again")
    return data


def clean_rubric(criteria) -> list[dict]:
    out = []
    for c in criteria or []:
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            continue
        try:
            points = int(c.get("points", 1))
        except (TypeError, ValueError):
            points = 1
        out.append({
            "name": str(c["name"]).strip()[:80],
            "description": str(c.get("description", "")).strip()[:400],
            "points": max(1, min(10, points)),
        })
    return out[:MAX_CRITERIA]


async def _notes_for(user_id: int, text: str, topic: str | None) -> list[dict]:
    return await hybrid_search(user_id, text, topic=topic, limit=4)


async def make_rubric(user_id: int, question: str, topic: str | None = None) -> list[dict]:
    chunks = await _notes_for(user_id, question, topic)
    prompt = f"Study notes:\n{build_context(chunks)}\n\nExam question: {question}"
    rubric = clean_rubric((await _json_call(RUBRIC_SYSTEM, prompt)).get("criteria"))
    if not rubric:
        raise GradingError("The AI did not return a usable rubric, please try again")
    return rubric


def apply_scores(rubric: list[dict], marked: list) -> list[dict]:
    """Match the AI's marks to the rubric by name (falling back to position) and clamp them."""
    by_name = {str(m.get("name", "")).strip().lower(): m for m in marked if isinstance(m, dict)}
    out = []
    for i, c in enumerate(rubric):
        m = by_name.get(c["name"].lower()) or (marked[i] if i < len(marked) and isinstance(marked[i], dict) else {})
        try:
            score = float(m.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        out.append({
            "name": c["name"],
            "description": c["description"],
            "score": max(0.0, min(float(c["points"]), score)),
            "max": c["points"],
            "feedback": humanize_text(str(m.get("feedback", "")).strip()),
            "evidence": [int(n) for n in (m.get("evidence") or []) if str(n).isdigit()],
        })
    return out


def _save(user_id: int, kind: str, topic: str | None, question: str, answer: str,
          rubric: list | None, result: dict, score: float, max_score: float) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO graded_answers (user_id, kind, topic, question, answer, rubric_json, result_json,
                                           score, max_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, kind, topic, question, answer, json.dumps(rubric) if rubric else None,
             json.dumps(result), score, max_score, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


async def grade_answer(
    user_id: int, question: str, answer: str, rubric: list[dict] | None = None,
    topic: str | None = None, transcription: str | None = None,
) -> dict:
    question, answer = question.strip(), answer.strip()[:MAX_ANSWER_CHARS]
    if not question or not answer:
        raise GradingError("Question and answer are required")
    rubric = clean_rubric(rubric) or await make_rubric(user_id, question, topic)
    chunks = await _notes_for(user_id, f"{question} {answer}", topic)
    rubric_text = "\n".join(f"- {c['name']} ({c['points']} points): {c['description']}" for c in rubric)
    prompt = (
        f"Study notes:\n{build_context(chunks)}\n\nQuestion: {question}\n\nRubric:\n{rubric_text}\n\n"
        f"Student answer:\n{answer}"
    )
    data = await _json_call(GRADE_SYSTEM, prompt)
    criteria = apply_scores(rubric, data.get("criteria") or [])
    score = sum(c["score"] for c in criteria)
    max_score = sum(c["max"] for c in criteria)
    result = {
        "criteria": criteria,
        "score": score,
        "max_score": max_score,
        "percentage": round(score / max_score * 100, 1) if max_score else 0.0,
        "overall_feedback": humanize_text(str(data.get("overall_feedback", "")).strip()),
        "model_answer": str(data.get("model_answer", "")).strip(),
        "sources": [{"n": i, "title": c.get("title"), "source": c.get("source"), "page_number": c.get("page_number"),
                     "document_id": c.get("document_id"), "file_type": c.get("file_type"),
                     "preview": (c.get("content") or "")[:240]}
                    for i, c in enumerate(chunks, 1)],
        "rubric": rubric,
    }
    if transcription is not None:
        result["transcription"] = transcription
    result["id"] = _save(user_id, "essay", topic, question, answer, rubric, result, score, max_score)
    record_event(user_id, topic or "General", score >= PASS_SHARE * max_score, "hard", source="essay")
    touch_study_streak(user_id)
    return result


async def transcribe_answer(image: bytes, mime: str) -> str:
    try:
        text = await llm.describe_image(image, mime, prompt=TRANSCRIBE_PROMPT)
    except llm.LLMError as e:
        raise GradingError(f"Could not read the photo: {e}") from e
    if not text.strip():
        raise GradingError("No handwriting was found in the photo")
    return text.strip()


def _pct(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


async def teach_back(user_id: int, concept: str, explanation: str, topic: str | None = None) -> dict:
    concept, explanation = concept.strip(), explanation.strip()[:MAX_ANSWER_CHARS]
    if not concept or not explanation:
        raise GradingError("Concept and explanation are required")
    chunks = await _notes_for(user_id, f"{concept} {explanation}", topic)
    prompt = (
        f"Study notes:\n{build_context(chunks)}\n\nConcept: {concept}\n\nStudent's explanation:\n{explanation}"
    )
    data = await _json_call(TEACH_BACK_SYSTEM, prompt)
    strs = lambda key: [humanize_text(str(x)).strip() for x in (data.get(key) or []) if str(x).strip()][:6]  # noqa: E731
    result = {
        "score": _pct(data.get("score")),
        "accuracy": _pct(data.get("accuracy")),
        "clarity": _pct(data.get("clarity")),
        "completeness": _pct(data.get("completeness")),
        "gaps": strs("gaps"),
        "misconceptions": strs("misconceptions"),
        "jargon": [
            {"term": str(j.get("term", "")).strip(), "suggestion": str(j.get("suggestion", "")).strip()}
            for j in (data.get("jargon") or []) if isinstance(j, dict) and str(j.get("term", "")).strip()
        ][:6],
        "follow_up_question": str(data.get("follow_up_question", "")).strip(),
        "verdict": humanize_text(str(data.get("verdict", "")).strip()),
        "notes_found": bool(chunks),
    }
    result["id"] = _save(user_id, "teach_back", topic, concept, explanation, None, result, result["score"], 100)
    record_event(user_id, topic or "General", result["score"] >= TEACH_BACK_PASS, "medium", source="teach_back")
    touch_study_streak(user_id)
    return result


def history(user_id: int, kind: str | None = None, limit: int = 30) -> list[dict]:
    sql = "SELECT * FROM graded_answers WHERE user_id = ?"
    params: list = [user_id]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    with get_db() as conn:
        rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
    out = []
    for r in rows:
        d = row_to_dict(r)
        d["rubric"] = json.loads(d.pop("rubric_json") or "null")
        d["result"] = json.loads(d.pop("result_json"))
        out.append(d)
    return out
