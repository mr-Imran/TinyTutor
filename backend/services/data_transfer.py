"""Backup/restore of the whole library, and flashcard/quiz export and import (Anki, CSV)."""
import csv
import io
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from html import unescape
from pathlib import Path

import database
from config import UPLOAD_DIR
from database import get_db
from services.card_types import CLOZE_RE, create_cloze, render_cloze, render_occlusion_png
from services.flashcards import create_cards

BACKUP_FORMAT = 1
# Stable ids so re-exported decks update the same Anki note type and deck instead of duplicating.
ANKI_MODEL_ID = 1607392319
ANKI_DECK_BASE_ID = 2059400110


class DataError(ValueError):
    pass


# ---------------------------------------------------------------- backup / restore

def _copy_db(source: Path, target: Path):
    """Consistent page-level copy using SQLite's online backup API."""
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def create_backup() -> bytes:
    """Zip of a consistent database snapshot plus every uploaded file."""
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "tutor.db"
        _copy_db(database.DB_PATH, snapshot)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "app": "TinyTutor", "format": BACKUP_FORMAT, "created_at": datetime.utcnow().isoformat(),
            }))
            zf.write(snapshot, "tutor.db")
            if UPLOAD_DIR.exists():
                for f in sorted(UPLOAD_DIR.iterdir()):
                    if f.is_file() and f.name != ".gitkeep":
                        zf.write(f, f"uploads/{f.name}")
    return buf.getvalue()


def restore_backup(data: bytes) -> dict:
    """Replace the library with a backup. The current database is kept as a safety copy first."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise DataError("That file is not a TinyTutor backup (.zip).") from e
    names = set(zf.namelist())
    if "tutor.db" not in names:
        raise DataError("The backup has no tutor.db inside.")

    with tempfile.TemporaryDirectory() as tmp:
        incoming = Path(tmp) / "incoming.db"
        incoming.write_bytes(zf.read("tutor.db"))
        try:
            with closing(sqlite3.connect(incoming)) as check:
                ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                has_docs = check.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
                ).fetchone()
        except sqlite3.DatabaseError as e:
            raise DataError("The database inside the backup is damaged.") from e
        if not ok or not has_docs:
            raise DataError("The database inside the backup is damaged or not from TinyTutor.")

        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        safety = database.DATA_DIR / f"pre-restore-{stamp}.db"
        _copy_db(database.DB_PATH, safety)
        # Copy pages into the live file rather than swapping files (open handles on Windows).
        _copy_db(incoming, database.DB_PATH)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    restored_files = 0
    for name in names:
        if not name.startswith("uploads/") or name.endswith("/"):
            continue
        filename = Path(name).name  # drop any directory parts: no writing outside uploads/
        if not filename or filename in (".", ".."):
            continue
        with zf.open(name) as src, open(UPLOAD_DIR / filename, "wb") as dst:
            shutil.copyfileobj(src, dst)
        restored_files += 1

    database.init_db()  # migrate a backup made by an older version
    with get_db() as conn:
        docs = conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]
        cards = conn.execute("SELECT COUNT(*) c FROM flashcards").fetchone()["c"]
    return {"documents": docs, "flashcards": cards, "files": restored_files, "safety_copy": safety.name}


# ---------------------------------------------------------------- flashcards: CSV

def _cards(user_id: int, topic: str | None = None) -> list[dict]:
    sql = "SELECT * FROM flashcards WHERE user_id = ?"
    params: list = [user_id]
    if topic:
        sql += " AND topic = ?"
        params.append(topic)
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql + " ORDER BY topic, id", params).fetchall()]


def flashcards_csv(user_id: int, topic: str | None = None) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["topic", "front", "back", "interval_days", "repetitions", "due_at"])
    for c in _cards(user_id, topic):
        if c["card_type"] == "occlusion":
            continue  # image cards need the .apkg export
        front, back = c["front"], c["back"]
        if c["card_type"] == "cloze":
            front = render_cloze(c["front"], c["cloze_index"], reveal=False)
            back = render_cloze(c["front"], c["cloze_index"], reveal=True) + (f"\n{c['back']}" if c["back"] else "")
        writer.writerow([c["topic"], front, back, c["interval_days"], c["repetitions"], c["due_at"]])
    return out.getvalue()


def quiz_history_csv(user_id: int) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "topic", "type", "difficulty", "question", "your_answer", "correct_answer", "correct"])
    with get_db() as conn:
        rows = conn.execute(
            """SELECT created_at, topic, question_type, difficulty, question, user_answer, correct_answer, is_correct
               FROM quiz_attempts WHERE user_id = ? ORDER BY created_at""",
            (user_id,),
        ).fetchall()
    for r in rows:
        writer.writerow([r["created_at"], r["topic"], r["question_type"], r["difficulty"], r["question"],
                         r["user_answer"], r["correct_answer"], "yes" if r["is_correct"] else "no"])
    return out.getvalue()


def import_flashcards_csv(user_id: int, text: str, default_topic: str) -> dict:
    """Accepts `front,back[,topic]` rows, with or without a header; also tab-separated (Anki .txt)."""
    # Anki text exports start with "#separator:tab"-style header lines.
    text = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if r]
    if not rows:
        raise DataError("The file has no rows.")

    header = [h.strip().lower() for h in rows[0]]
    if "front" in header and "back" in header:
        fi, bi = header.index("front"), header.index("back")
        ti = header.index("topic") if "topic" in header else None
        rows = rows[1:]
    else:
        fi, bi, ti = 0, 1, (2 if len(rows[0]) > 2 else None)

    by_topic: dict[str, list[dict]] = {}
    for r in rows:
        if len(r) <= max(fi, bi):
            continue
        topic = (r[ti].strip() if ti is not None and ti < len(r) and r[ti].strip() else default_topic)
        by_topic.setdefault(topic, []).append({"front": _strip_html(r[fi]), "back": _strip_html(r[bi])})
    return _create_by_topic(user_id, by_topic, total=len(rows))


def _create_by_topic(user_id: int, by_topic: dict[str, list[dict]], total: int) -> dict:
    created = 0
    for topic, cards in by_topic.items():
        created += len(create_cards(user_id, topic, cards))
    return {"imported": created, "skipped": total - created, "topics": sorted(by_topic)}


# ---------------------------------------------------------------- flashcards: Anki

def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</div>|</p>", "\n", text, flags=re.I)
    text = re.sub(r"\[sound:[^\]]*\]", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def flashcards_apkg(user_id: int, topic: str | None = None) -> bytes:
    import genanki

    model = genanki.Model(
        ANKI_MODEL_ID,
        "TinyTutor Basic",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[{
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }],
    )
    decks: dict[str, genanki.Deck] = {}
    cloze_notes: set[str] = set()

    def deck_for(card):
        name = f"TinyTutor::{card['topic']}"
        if name not in decks:
            decks[name] = genanki.Deck(ANKI_DECK_BASE_ID + len(decks), name)
        return decks[name]

    with tempfile.TemporaryDirectory() as tmp:
        media = []
        for c in _cards(user_id, topic):
            if c["card_type"] == "cloze":
                # Siblings share one note; Anki makes a card per {{cN::}} itself.
                if c["note_id"] in cloze_notes:
                    continue
                cloze_notes.add(c["note_id"])
                deck_for(c).add_note(genanki.Note(
                    model=genanki.CLOZE_MODEL,
                    fields=[_html_escape(c["front"]), _html_escape(c["back"])],
                    guid=genanki.guid_for("tinytutor", c["note_id"]),
                ))
            elif c["card_type"] == "occlusion":
                # Exported as picture cards with the box burned in, which every Anki version can show.
                masks = json.loads(c["masks_json"] or "[]")
                if not (UPLOAD_DIR / (c["image_name"] or "")).is_file() or c["cloze_index"] >= len(masks):
                    continue
                q, a = f"tinytutor_{c['id']}_q.png", f"tinytutor_{c['id']}_a.png"
                (Path(tmp) / q).write_bytes(render_occlusion_png(c["image_name"], masks, c["cloze_index"], False))
                (Path(tmp) / a).write_bytes(render_occlusion_png(c["image_name"], masks, c["cloze_index"], True))
                media += [str(Path(tmp) / q), str(Path(tmp) / a)]
                deck_for(c).add_note(genanki.Note(
                    model=model,
                    fields=[f'{_html_escape(c["front"])}<br><img src="{q}">',
                            f'<img src="{a}"><br>{_html_escape(c["back"])}'],
                    guid=genanki.guid_for("tinytutor", c["id"]),
                ))
            else:
                deck_for(c).add_note(genanki.Note(
                    model=model,
                    fields=[_html_escape(c["front"]), _html_escape(c["back"])],
                    guid=genanki.guid_for("tinytutor", c["id"]),
                ))
        if not decks:
            raise DataError("There are no flashcards to export.")
        path = Path(tmp) / "tinytutor.apkg"
        package = genanki.Package(list(decks.values()))
        package.media_files = media
        package.write_to_file(path)
        return path.read_bytes()


def _html_escape(text: str) -> str:
    from html import escape

    return escape(text).replace("\n", "<br>")


def import_flashcards_apkg(user_id: int, data: bytes, default_topic: str) -> dict:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise DataError("That file is not an Anki package (.apkg).") from e
    names = zf.namelist()
    collection = next((n for n in ("collection.anki21", "collection.anki2") if n in names), None)
    if collection is None:
        raise DataError(
            "This deck uses Anki's newest compressed format. In Anki, export again with "
            "'Support older Anki versions' ticked, or export as plain text."
        )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "collection.db"
        path.write_bytes(zf.read(collection))
        conn = sqlite3.connect(path)
        try:
            deck_names = {}
            row = conn.execute("SELECT decks FROM col").fetchone()
            if row and row[0]:
                deck_names = {int(k): v.get("name", "") for k, v in json.loads(row[0]).items()}
            notes = conn.execute(
                """SELECT n.flds, MIN(c.did) FROM notes n LEFT JOIN cards c ON c.nid = n.id GROUP BY n.id"""
            ).fetchall()
        except sqlite3.DatabaseError as e:
            raise DataError("Could not read the Anki collection.") from e
        finally:
            conn.close()

    by_topic: dict[str, list[dict]] = {}
    cloze_created = 0
    for flds, did in notes:
        fields = flds.split("\x1f")
        deck = deck_names.get(did or 0, "")
        topic = deck.split("::")[-1].strip() if deck and deck != "Default" else default_topic
        if CLOZE_RE.search(fields[0]):
            extra = _strip_html(fields[1]) if len(fields) > 1 else ""
            cloze_created += 1 if create_cloze(user_id, topic, _strip_html(fields[0]), extra) else 0
            continue
        if len(fields) < 2:
            continue
        by_topic.setdefault(topic, []).append({"front": _strip_html(fields[0]), "back": _strip_html(fields[1])})
    result = _create_by_topic(user_id, by_topic, total=len(notes) - cloze_created)
    result["imported"] += cloze_created
    return result
