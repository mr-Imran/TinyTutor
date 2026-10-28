"""Is an answer backed by the student's notes?

Two checks:
- coverage(): before answering, do the retrieved notes actually cover the question? If not, the
  tutor says so plainly instead of dressing up unrelated notes as an answer.
- check_answer(): after answering, each sentence is matched against the notes it cites (or all
  retrieved notes when it cites none) by meaning (embeddings) and by shared content words.
  An optional AI pass confirms borderline sentences.
"""
import json
import re

import numpy as np

from services import llm
from services.settings_store import get_setting, set_setting

# Coverage: share of the question's content words found in the best note, or meaning similarity.
COVERAGE_WORD_SHARE = 0.5
COVERAGE_SEMANTIC = 0.55
# A sentence counts as supported at or above either score.
SUPPORT_SEMANTIC = 0.6
SUPPORT_WORD_SHARE = 0.6
# Overall label thresholds on the share of checkable sentences that are supported.
FULLY = 0.8
PARTLY = 0.4
MIN_SENTENCE_CHARS = 25

ENABLED_KEY = "grounding_enabled"
AI_CHECK_KEY = "grounding_ai_check"

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers
him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our
out over own same she should so some such than that the their them then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your yours
explain tell describe define mean means meaning please give show example examples also like use used using
""".split())

NOT_COVERED_RULE = (
    "The student's notes do not cover this question. Start your reply with exactly: "
    "\"Your notes don't cover this.\" Then give a short general answer from your own knowledge, "
    "and say it is general knowledge, not from their notes. Do not cite any numbers."
)


def settings() -> dict:
    return {
        "enabled": get_setting(ENABLED_KEY, "1") == "1",
        "ai_check": get_setting(AI_CHECK_KEY, "0") == "1",
    }


def save_settings(enabled: bool | None = None, ai_check: bool | None = None) -> dict:
    if enabled is not None:
        set_setting(ENABLED_KEY, "1" if enabled else "0")
    if ai_check is not None:
        set_setting(AI_CHECK_KEY, "1" if ai_check else "0")
    return settings()


def content_words(text: str) -> set[str]:
    words = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) > 2 and w not in STOPWORDS:
            words.add(_stem(w))
    return words


def _stem(w: str) -> str:
    for suffix in ("ing", "ies", "es", "ed", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w


def word_share(text: str, note: str) -> float:
    words = content_words(text)
    if not words:
        return 0.0
    return len(words & content_words(note)) / len(words)


def coverage(question: str, chunks: list[dict]) -> dict:
    """{"covered": bool, "score": best evidence 0-1} for retrieved chunks."""
    if not chunks:
        return {"covered": False, "score": 0.0}
    best_words = max(word_share(question, f"{c.get('title', '')} {c.get('topic', '')} {c.get('content', '')}")
                     for c in chunks)
    best_sem = max((c.get("semantic_score") or 0.0) for c in chunks)
    covered = best_words >= COVERAGE_WORD_SHARE or best_sem >= COVERAGE_SEMANTIC
    # A question with no content words ("what's next?") cannot be judged; assume covered.
    if not content_words(question):
        covered = True
    return {"covered": covered, "score": round(max(best_words, best_sem), 3)}


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"```[\s\S]*?```", " ", text)  # code is not a factual claim
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[$])|\n{2,}", text)
    return [p.strip() for p in parts if p and p.strip()]


def _checkable(sentence: str) -> bool:
    plain = re.sub(r"\[\d+\]", "", sentence).strip()
    if len(plain) < MIN_SENTENCE_CHARS or plain.endswith("?"):
        return False
    return bool(content_words(plain))


async def _embed(texts: list[str]) -> np.ndarray | None:
    from services.embeddings import EmbeddingError, _normalize, embed_texts

    try:
        return _normalize(await embed_texts(texts))
    except EmbeddingError:
        return None


AI_CHECK_SYSTEM = (
    "You check whether statements are supported by study notes. Return ONLY valid JSON: "
    '{"results":[{"n":1,"supported":true}]}. A statement is supported only if the notes state or '
    "directly imply it. One result per numbered statement."
)


async def _ai_confirm(sentences: list[str], notes: str) -> dict[int, bool]:
    from services.ai import _extract_json

    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    try:
        raw = await llm.complete(
            [{"role": "user", "content": f"Notes:\n{notes}\n\nStatements:\n{numbered}"}],
            system=AI_CHECK_SYSTEM, json_mode=True, temperature=0,
        )
        data = json.loads(_extract_json(raw))
        return {int(r["n"]): bool(r["supported"]) for r in data.get("results", []) if str(r.get("n", "")).isdigit()}
    except (llm.LLMError, json.JSONDecodeError, TypeError, KeyError, AttributeError):
        return {}


async def check_answer(answer: str, chunks: list[dict], use_ai: bool = False) -> dict:
    """chunks: dicts with "n" (citation number) and "content"."""
    sentences = split_sentences(answer)
    if not chunks:
        return {"label": "not_in_notes", "supported": 0, "checked": 0, "sentences": [
            {"text": s, "supported": False, "score": 0.0} for s in sentences if _checkable(s)
        ], "method": "none"}
    if answer.strip().lower().startswith("your notes don't cover this"):
        return {"label": "not_in_notes", "supported": 0, "checked": 0, "sentences": [], "method": "none"}

    by_n = {c["n"]: c for c in chunks}
    checkable = [s for s in sentences if _checkable(s)]
    if not checkable:
        return {"label": "fully", "supported": 0, "checked": 0, "sentences": [], "method": "none"}

    vectors = await _embed([re.sub(r"\[\d+\]", "", s) for s in checkable] + [c["content"] for c in chunks])
    sent_vecs = vectors[: len(checkable)] if vectors is not None else None
    note_index = {c["n"]: len(checkable) + i for i, c in enumerate(chunks)}

    results = []
    for i, s in enumerate(checkable):
        cited = [int(n) for n in re.findall(r"\[(\d+)\]", s) if int(n) in by_n]
        targets = cited or list(by_n)
        words = max(word_share(re.sub(r"\[\d+\]", "", s), by_n[n]["content"]) for n in targets)
        sem = 0.0
        if sent_vecs is not None:
            sem = max(float(sent_vecs[i] @ vectors[note_index[n]]) for n in targets)
        supported = sem >= SUPPORT_SEMANTIC or words >= SUPPORT_WORD_SHARE
        results.append({"text": s, "supported": supported, "score": round(max(sem, words), 3), "cited": cited})

    method = "embeddings" if vectors is not None else "words"
    if use_ai:
        unsure = [r for r in results if not r["supported"] or r["score"] < 0.75]
        if unsure:
            notes = "\n\n".join(f"[{c['n']}] {c['content'][:800]}" for c in chunks)
            verdicts = await _ai_confirm([r["text"] for r in unsure], notes)
            for i, r in enumerate(unsure, 1):
                if i in verdicts:
                    r["supported"] = verdicts[i]
            if verdicts:
                method += "+ai"

    share = sum(r["supported"] for r in results) / len(results)
    label = "fully" if share >= FULLY else "partly" if share >= PARTLY else "unsupported"
    return {
        "label": label,
        "supported": sum(r["supported"] for r in results),
        "checked": len(results),
        "sentences": results,
        "method": method,
    }
