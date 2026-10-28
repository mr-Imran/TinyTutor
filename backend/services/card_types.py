"""Fill-in-the-blank (cloze) and image-hiding (occlusion) flashcards.

Both follow Anki's model: one note makes several sibling cards, each with its own SM-2 schedule.
- Cloze text marks blanks as {{c1::answer}} or {{c1::answer::hint}}; each number is one card,
  and blanks that share a number are hidden together.
- Occlusion draws boxes over an image; each box is one card ("hide one, guess one").
Images are stored in the uploads folder (prefix card_) so backups include them.
"""
import json
import re
import uuid
from datetime import datetime

from config import UPLOAD_DIR
from database import get_db, row_to_dict
from services import llm

CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)
IMAGE_PREFIX = "card_"
MAX_MASKS = 40

SUGGEST_SYSTEM = (
    "You turn a study passage into a fill-in-the-blank flashcard. Return ONLY valid JSON: "
    '{"text":"the passage with 1 to 3 key terms wrapped like {{c1::term}}, {{c2::term}}"}. '
    "Keep every other word of the passage exactly as given. Blank the terms a student must remember, "
    "never filler words."
)


class CardError(ValueError):
    pass


def cloze_indices(text: str) -> list[int]:
    return sorted({int(m.group(1)) for m in CLOZE_RE.finditer(text)})


def render_cloze(text: str, index: int, reveal: bool) -> str:
    """Plain-text rendering: the asked blank is [...] (or [hint]); other blanks show their answer."""
    def repl(m):
        if int(m.group(1)) != index:
            return m.group(2)
        if reveal:
            return f"[{m.group(2)}]"
        return f"[{m.group(3)}]" if m.group(3) else "[...]"

    return CLOZE_RE.sub(repl, text)


def strip_cloze(text: str) -> str:
    return CLOZE_RE.sub(lambda m: m.group(2), text)


def _now() -> str:
    return datetime.utcnow().isoformat()


def _rows(ids: list[int]) -> list[dict]:
    from services.flashcards import card_out

    if not ids:
        return []
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM flashcards WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id", ids)
        return [card_out(row_to_dict(r)) for r in rows.fetchall()]


def create_cloze(user_id: int, topic: str, text: str, extra: str = "", document_id: int | None = None) -> list[dict]:
    text, topic = text.strip(), topic.strip()
    indices = cloze_indices(text)
    if not indices:
        raise CardError("Mark at least one blank like {{c1::answer}}.")
    note_id = f"cloze-{uuid.uuid4().hex[:12]}"
    now = _now()
    ids = []
    with get_db() as conn:
        existing = {
            (r["front"], r["cloze_index"]) for r in conn.execute(
                "SELECT front, cloze_index FROM flashcards WHERE user_id = ? AND card_type = 'cloze'", (user_id,)
            )
        }
        for i in indices:
            if (text, i) in existing:
                continue
            cur = conn.execute(
                """INSERT INTO flashcards (user_id, document_id, topic, front, back, card_type, note_id, cloze_index,
                                           due_at, created_at)
                   VALUES (?, ?, ?, ?, ?, 'cloze', ?, ?, ?, ?)""",
                (user_id, document_id, topic, text, extra.strip(), note_id, i, now, now),
            )
            ids.append(cur.lastrowid)
    return _rows(ids)


async def suggest_cloze(text: str) -> dict:
    """AI picks the blanks. Falls back to the original text unchanged so the student marks them."""
    from services.ai import _extract_json

    text = text.strip()
    try:
        raw = await llm.complete([{"role": "user", "content": text}], system=SUGGEST_SYSTEM, json_mode=True,
                                 temperature=0)
        marked = str(json.loads(_extract_json(raw)).get("text", ""))
    except (llm.LLMError, json.JSONDecodeError, AttributeError, TypeError):
        return {"text": text, "used_ai": False}
    # Reject answers that rewrote the passage instead of just marking it.
    same = re.sub(r"\s+", " ", strip_cloze(marked)).strip() == re.sub(r"\s+", " ", text).strip()
    if not cloze_indices(marked) or not same:
        return {"text": text, "used_ai": False}
    return {"text": marked, "used_ai": True}


def clean_masks(masks) -> list[dict]:
    out = []
    for m in masks or []:
        try:
            x, y, w, h = (float(m[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            continue
        x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
        w, h = min(max(w, 0.0), 1.0 - x), min(max(h, 0.0), 1.0 - y)
        if w < 0.005 or h < 0.005:
            continue
        out.append({"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4),
                    "label": str(m.get("label") or "").strip()[:200]})
    return out[:MAX_MASKS]


def create_occlusion(
    user_id: int, topic: str, image: bytes, ext: str, masks, header: str = ""
) -> list[dict]:
    masks = clean_masks(masks)
    if not masks:
        raise CardError("Draw at least one box over the image.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_name = f"{IMAGE_PREFIX}{uuid.uuid4().hex[:12]}{ext}"
    (UPLOAD_DIR / image_name).write_bytes(image)
    note_id = f"occl-{uuid.uuid4().hex[:12]}"
    front = header.strip() or "What is hidden?"
    now = _now()
    ids = []
    with get_db() as conn:
        for i, m in enumerate(masks):
            cur = conn.execute(
                """INSERT INTO flashcards (user_id, topic, front, back, card_type, note_id, cloze_index, image_name,
                                           masks_json, due_at, created_at)
                   VALUES (?, ?, ?, ?, 'occlusion', ?, ?, ?, ?, ?, ?)""",
                (user_id, topic.strip(), front, m["label"] or f"Box {i + 1}", note_id, i, image_name,
                 json.dumps(masks), now, now),
            )
            ids.append(cur.lastrowid)
    return _rows(ids)


def image_path(name: str):
    """Only card images, and only by bare file name."""
    if not re.fullmatch(rf"{IMAGE_PREFIX}[0-9a-f]{{12}}\.(png|jpe?g|webp)", name):
        return None
    path = UPLOAD_DIR / name
    return path if path.is_file() else None


def remove_unused_image(name: str | None):
    if not name:
        return
    with get_db() as conn:
        used = conn.execute("SELECT 1 FROM flashcards WHERE image_name = ? LIMIT 1", (name,)).fetchone()
    if not used:
        path = image_path(name)
        if path:
            path.unlink(missing_ok=True)


def render_occlusion_png(image_name: str, masks: list[dict], index: int, reveal: bool) -> bytes:
    """Image with boxes burned in, for Anki export: the asked box is filled (question) or outlined (answer)."""
    import io

    from PIL import Image, ImageDraw

    with Image.open(UPLOAD_DIR / image_name) as src:
        img = src.convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    for i, m in enumerate(masks):
        box = (m["x"] * width, m["y"] * height, (m["x"] + m["w"]) * width, (m["y"] + m["h"]) * height)
        if i != index:
            continue
        if reveal:
            draw.rectangle(box, outline=(220, 38, 38), width=max(2, width // 200))
        else:
            draw.rectangle(box, fill=(249, 115, 22), outline=(194, 65, 12), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
