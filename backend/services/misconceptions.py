"""Find patterns in wrong answers ("you keep confusing mitosis and meiosis") and drill them away.

analyze() groups recent wrong answers by meaning within each topic (embeddings; by topic alone when
no embedding model is available), then asks the AI to name the shared misconception, if there is one.
Each misconception gets a short targeted drill; three correct drill answers in a row resolve it.
"""
import json
from datetime import datetime

import numpy as np

from database import get_db, row_to_dict
from services import llm
from services.ai import _extract_json
from services.quiz import record_quiz_attempt
from services.text_style import humanize_text

MIN_MISTAKES = 3  # fewer wrong answers than this: just list them
MIN_GROUP = 2  # wrong answers needed before a pattern is named
CLUSTER_SIMILARITY = 0.7
MAX_ANALYZED = 200
RESOLVE_STREAK = 3
DRILL_SIZE = 3

NAME_SYSTEM = (
    "You find the misconception behind a student's wrong answers. Return ONLY valid JSON, no markdown: "
    '{"is_pattern":true,"same_as":null,"title":"short name, e.g. Confuses mitosis with meiosis",'
    '"description":"what the student seems to believe, one or two sentences",'
    '"correction":"the correct idea, explained simply in two or three sentences"}. '
    "Set is_pattern to false if the mistakes share no common wrong belief (for example random slips). "
    "If an existing misconception listed in the prompt already explains them, set same_as to its id."
)

DRILL_SYSTEM = (
    "You write practice questions that target one specific misconception. Return ONLY valid JSON, no markdown: "
    '{"questions":[{"question":"...","options":["A","B","C","D"],"correct_answer":"exact text of one option",'
    '"explanation":"why, addressing the misconception"}]}. '
    f"Write exactly {DRILL_SIZE} multiple-choice questions. Make the misconception's wrong belief a tempting "
    "wrong option. Write math in LaTeX between dollar signs."
)


class MisconceptionError(Exception):
    pass


def _now() -> str:
    return datetime.utcnow().isoformat()


def _pending_mistakes(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT q.id, COALESCE(q.topic, 'General') topic, q.question, q.user_answer, q.correct_answer, q.created_at
               FROM quiz_attempts q
               LEFT JOIN misconception_attempts m ON m.attempt_id = q.id
               WHERE q.user_id = ? AND q.is_correct = 0 AND m.attempt_id IS NULL
                 AND TRIM(COALESCE(q.user_answer, '')) != ''
               ORDER BY q.id DESC LIMIT ?""",
            (user_id, MAX_ANALYZED),
        ).fetchall()
    return [dict(r) for r in rows]


def _mistake_text(m: dict) -> str:
    return f"{m['question']} Student answered: {m['user_answer']}. Correct: {m['correct_answer']}"


async def _vectors(mistakes: list[dict]) -> np.ndarray | None:
    from services.embeddings import EmbeddingError, _normalize, embed_texts

    try:
        return _normalize(await embed_texts([_mistake_text(m) for m in mistakes]))
    except EmbeddingError:
        return None


def cluster(mistakes: list[dict], vectors: np.ndarray | None) -> list[list[dict]]:
    """Greedy clustering within each topic. Without vectors, one group per topic."""
    groups: list[list[int]] = []
    centroids: list[np.ndarray] = []
    topics: list[str] = []
    for i, m in enumerate(mistakes):
        best, best_sim = None, CLUSTER_SIMILARITY
        for g, (centroid, topic) in enumerate(zip(centroids, topics)):
            if topic != m["topic"]:
                continue
            sim = 1.0 if vectors is None else float(centroid @ vectors[i] / (np.linalg.norm(centroid) or 1))
            if sim >= best_sim:
                best, best_sim = g, sim
        if best is None:
            groups.append([i])
            centroids.append(vectors[i].copy() if vectors is not None else np.zeros(1))
            topics.append(m["topic"])
        else:
            groups[best].append(i)
            if vectors is not None:
                centroids[best] = centroids[best] + vectors[i]
    return [[mistakes[i] for i in g] for g in groups]


def _link(attempt_ids: list[int], misconception_id: int | None):
    with get_db() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO misconception_attempts (attempt_id, misconception_id) VALUES (?, ?)",
            [(a, misconception_id) for a in attempt_ids],
        )


def _open_in_topic(user_id: int, topic: str) -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, title, description FROM misconceptions WHERE user_id = ? AND topic = ? AND status = 'open'",
            (user_id, topic),
        ).fetchall()]


async def _name_group(user_id: int, group: list[dict]) -> dict | None:
    topic = group[0]["topic"]
    existing = _open_in_topic(user_id, topic)
    listing = "\n".join(f"- id {e['id']}: {e['title']}: {e['description']}" for e in existing) or "none"
    mistakes = "\n".join(
        f"{i}. Question: {m['question']}\n   Student answered: {m['user_answer']}\n   Correct: {m['correct_answer']}"
        for i, m in enumerate(group, 1)
    )
    prompt = f"Topic: {topic}\nExisting misconceptions:\n{listing}\n\nWrong answers:\n{mistakes}"
    raw = await llm.complete([{"role": "user", "content": prompt}], system=NAME_SYSTEM, json_mode=True,
                             temperature=0)
    data = json.loads(_extract_json(raw))
    return data if isinstance(data, dict) else None


async def analyze(user_id: int) -> dict:
    mistakes = _pending_mistakes(user_id)
    if len(mistakes) < MIN_MISTAKES and not _has_any(user_id):
        return {"created": [], "updated": [], "analyzed": 0,
                "message": f"Answer a few more questions first: patterns need at least {MIN_MISTAKES} wrong answers."}
    vectors = await _vectors(mistakes) if mistakes else None
    created, updated, analyzed = [], [], 0
    for group in cluster(mistakes, vectors):
        if len(group) < MIN_GROUP:
            continue  # left unlinked, so it can join a pattern with later mistakes
        try:
            data = await _name_group(user_id, group)
        except llm.LLMError as e:
            raise MisconceptionError(f"AI unavailable: {e}") from e
        except (json.JSONDecodeError, TypeError):
            continue
        ids = [m["id"] for m in group]
        analyzed += len(ids)
        if not data or not data.get("is_pattern") or not str(data.get("title", "")).strip():
            _link(ids, None)
            continue
        same = data.get("same_as")
        known = {e["id"] for e in _open_in_topic(user_id, group[0]["topic"])}
        if str(same).isdigit() and int(same) in known:
            _link(ids, int(same))
            _touch(int(same))
            updated.append(int(same))
            continue
        with get_db() as conn:
            cur = conn.execute(
                """INSERT INTO misconceptions (user_id, topic, title, description, correction, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, group[0]["topic"], str(data["title"]).strip()[:120],
                 humanize_text(str(data.get("description", "")).strip()),
                 humanize_text(str(data.get("correction", "")).strip()), _now(), _now()),
            )
        _link(ids, cur.lastrowid)
        created.append(cur.lastrowid)
    return {"created": created, "updated": updated, "analyzed": analyzed, "message": None}


def _has_any(user_id: int) -> bool:
    with get_db() as conn:
        return bool(conn.execute("SELECT 1 FROM misconceptions WHERE user_id = ? LIMIT 1", (user_id,)).fetchone())


def _touch(misconception_id: int):
    with get_db() as conn:
        conn.execute("UPDATE misconceptions SET updated_at = ? WHERE id = ?", (_now(), misconception_id))


def _out(row, examples: list[dict]) -> dict:
    d = row_to_dict(row)
    drill = json.loads(d.pop("drill_json") or "null")
    d["drill"] = None if drill is None else {
        "questions": [{k: q[k] for k in ("question", "options")} for q in drill["questions"]],
        "answered": drill.get("answered", []),
    }
    d["examples"] = examples
    d["evidence"] = len(examples)
    return d


def list_misconceptions(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM misconceptions WHERE user_id = ? AND status != 'dismissed'
               ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, updated_at DESC""",
            (user_id,),
        ).fetchall()
        examples: dict[int, list] = {}
        for r in conn.execute(
            """SELECT m.misconception_id, q.question, q.user_answer, q.correct_answer
               FROM misconception_attempts m JOIN quiz_attempts q ON q.id = m.attempt_id
               WHERE q.user_id = ? AND m.misconception_id IS NOT NULL ORDER BY q.id DESC""",
            (user_id,),
        ):
            examples.setdefault(r["misconception_id"], []).append(
                {"question": r["question"], "user_answer": r["user_answer"], "correct_answer": r["correct_answer"]}
            )
    return [_out(r, examples.get(r["id"], [])) for r in rows]


def get(user_id: int, misconception_id: int) -> dict | None:
    return next((m for m in list_misconceptions(user_id) if m["id"] == misconception_id), None)


def pending_count(user_id: int) -> int:
    return len(_pending_mistakes(user_id))


def _row(user_id: int, misconception_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM misconceptions WHERE id = ? AND user_id = ?", (misconception_id, user_id)
        ).fetchone()
    if not row:
        raise MisconceptionError("Misconception not found")
    return row


async def new_drill(user_id: int, misconception_id: int) -> dict:
    row = _row(user_id, misconception_id)
    prompt = (
        f"Topic: {row['topic']}\nMisconception: {row['title']}\nWhat the student believes: {row['description']}\n"
        f"The correct idea: {row['correction']}"
    )
    try:
        raw = await llm.complete([{"role": "user", "content": prompt}], system=DRILL_SYSTEM, json_mode=True)
        data = json.loads(_extract_json(raw))
    except llm.LLMError as e:
        raise MisconceptionError(f"AI unavailable: {e}") from e
    except json.JSONDecodeError as e:
        raise MisconceptionError("The AI returned an unreadable drill, please try again") from e
    questions = []
    for q in (data.get("questions") if isinstance(data, dict) else None) or []:
        options = [str(o) for o in (q.get("options") or [])] if isinstance(q, dict) else []
        answer = str(q.get("correct_answer", "")).strip() if isinstance(q, dict) else ""
        if q.get("question") and len(options) >= 2 and answer:
            questions.append({"question": str(q["question"]), "options": options[:4], "correct_answer": answer,
                              "explanation": str(q.get("explanation", ""))})
    if not questions:
        raise MisconceptionError("The AI returned no usable questions, please try again")
    with get_db() as conn:
        conn.execute(
            "UPDATE misconceptions SET drill_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps({"questions": questions[:DRILL_SIZE], "answered": []}), _now(), misconception_id),
        )
    return get(user_id, misconception_id)


def answer_drill(user_id: int, misconception_id: int, index: int, answer: str) -> dict:
    row = _row(user_id, misconception_id)
    drill = json.loads(row["drill_json"] or "null")
    if not drill or not 0 <= index < len(drill["questions"]):
        raise MisconceptionError("No such drill question")
    if index in drill["answered"]:
        raise MisconceptionError("That question was already answered")
    q = drill["questions"][index]
    is_correct = answer.strip().lower() == q["correct_answer"].strip().lower()
    attempt_id = record_quiz_attempt(
        user_id, row["topic"], "mcq", "medium", q["question"], q["options"], q["correct_answer"], answer,
        is_correct, source="drill",
    )
    # A wrong drill answer is more evidence for this misconception, not a new pattern to discover.
    _link([attempt_id], misconception_id)
    drill["answered"].append(index)
    streak = row["streak"] + 1 if is_correct else 0
    status = "resolved" if streak >= RESOLVE_STREAK else "open"
    with get_db() as conn:
        conn.execute(
            """UPDATE misconceptions SET streak = ?, status = ?, drill_json = ?, updated_at = ?,
                      resolved_at = CASE WHEN ? = 'resolved' THEN ? ELSE resolved_at END
               WHERE id = ?""",
            (streak, status, json.dumps(drill), _now(), status, _now(), misconception_id),
        )
    return {"is_correct": is_correct, "correct_answer": q["correct_answer"], "explanation": q["explanation"],
            "streak": streak, "status": status, "needed": RESOLVE_STREAK}


def set_status(user_id: int, misconception_id: int, status: str):
    if status not in ("open", "resolved", "dismissed"):
        raise MisconceptionError("Unknown status")
    _row(user_id, misconception_id)
    with get_db() as conn:
        conn.execute(
            "UPDATE misconceptions SET status = ?, streak = CASE WHEN ? = 'open' THEN 0 ELSE streak END, "
            "updated_at = ? WHERE id = ?",
            (status, status, _now(), misconception_id),
        )


def recent_mistakes(user_id: int, limit: int = 10) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, COALESCE(topic, 'General') topic, question, user_answer, correct_answer, created_at
               FROM quiz_attempts WHERE user_id = ? AND is_correct = 0 ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
