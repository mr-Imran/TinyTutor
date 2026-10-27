import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from pptx import Presentation

from config import CHUNK_OVERLAP, CHUNK_SIZE, UPLOAD_DIR
from database import get_db

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt", ".md")

# A PDF page with less text than this is treated as scanned and sent to OCR.
OCR_MIN_CHARS = 25

# (page_number, text) — page_number is 1-based; None when the format has no pages.
Segment = tuple[int | None, str]


def extract_pdf_segments(path: Path) -> list[Segment]:
    segments = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, 1):
            text = page.get_text()
            if len(text.strip()) < OCR_MIN_CHARS:
                text = _ocr_page(page) or text
            segments.append((i, text))
    return segments


def _ocr_page(page) -> str:
    """OCR a scanned page. Needs Tesseract installed; silently skipped otherwise."""
    try:
        textpage = page.get_textpage_ocr(full=True, dpi=200)
        return page.get_text(textpage=textpage)
    except Exception as e:  # Tesseract missing or OCR failure
        logger.info("OCR unavailable for page %s: %s", page.number + 1, e)
        return ""


def extract_pptx_segments(path: Path) -> list[Segment]:
    segments = []
    for i, slide in enumerate(Presentation(path).slides, 1):
        parts = [s.text.strip() for s in slide.shapes if hasattr(s, "text") and s.text.strip()]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(notes)
        segments.append((i, "\n\n".join(parts)))
    return segments


def extract_docx_segments(path: Path) -> list[Segment]:
    from docx import Document as DocxDocument

    doc = DocxDocument(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return [(None, "\n\n".join(parts))]


def extract_text_segments(path: Path) -> list[Segment]:
    return [(None, path.read_text(encoding="utf-8", errors="replace"))]


EXTRACTORS = {
    ".pdf": ("pdf", extract_pdf_segments),
    ".pptx": ("pptx", extract_pptx_segments),
    ".docx": ("docx", extract_docx_segments),
    ".txt": ("txt", extract_text_segments),
    ".md": ("md", extract_text_segments),
}


def guess_topic(filename: str, text: str) -> str:
    name = Path(filename).stem.replace("_", " ").replace("-", " ")
    if len(name) > 3:
        return name.title()[:80]
    first_line = text.strip().split("\n")[0][:80] if text.strip() else "General"
    return first_line or "General"


def _split_long(paragraph: str) -> list[str]:
    """Split a paragraph longer than CHUNK_SIZE on sentence boundaries, then hard-cut."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces, current = [], ""
    for s in sentences:
        while len(s) > CHUNK_SIZE:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(s[:CHUNK_SIZE])
            s = s[CHUNK_SIZE - CHUNK_OVERLAP:]
        if len(current) + len(s) + 1 > CHUNK_SIZE and current:
            pieces.append(current)
            current = s
        else:
            current = f"{current} {s}".strip()
    if current:
        pieces.append(current)
    return pieces


def _pack_paragraphs(text: str) -> list[str]:
    """Pack whole paragraphs into chunks of about CHUNK_SIZE characters, with overlap."""
    paragraphs = []
    for p in re.split(r"\n\s*\n", text):
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            paragraphs.extend(_split_long(p) if len(p) > CHUNK_SIZE else [p])

    chunks, current = [], ""
    for p in paragraphs:
        if current and len(current) + len(p) + 1 > CHUNK_SIZE:
            chunks.append(current)
            tail = current[-CHUNK_OVERLAP:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            current = f"{tail} {p}".strip()
        else:
            current = f"{current} {p}".strip()
    if current:
        chunks.append(current)
    return chunks


def chunk_segments(segments: list[Segment], title: str, topic: str, source: str) -> list[dict]:
    chunks = []
    for page_number, text in segments:
        for piece in _pack_paragraphs(text):
            chunks.append(
                {
                    "title": f"{title} — Part {len(chunks) + 1}",
                    "topic": topic,
                    "content": piece,
                    "source": source,
                    "page_number": page_number,
                }
            )
    return chunks


def chunk_text(text: str, title: str, topic: str, source: str) -> list[dict]:
    return chunk_segments([(None, text)], title, topic, source)


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)


def process_upload(user_id: int, filename: str, file_bytes: bytes) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in EXTRACTORS:
        raise ValueError(f"Supported file types: {', '.join(SUPPORTED_EXTENSIONS)}")
    file_type, extract = EXTRACTORS[ext]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Unique prefix so two uploads with the same name never overwrite each other.
    stored_name = f"{user_id}_{uuid.uuid4().hex[:8]}_{safe_filename(filename)}"
    save_path = UPLOAD_DIR / stored_name
    save_path.write_bytes(file_bytes)

    try:
        segments = extract(save_path)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise ValueError(f"Could not read {filename}: {e}") from e

    full_text = "\n\n".join(t for _, t in segments)
    page_count = sum(1 for p, _ in segments if p is not None)
    title = Path(filename).stem
    topic = guess_topic(filename, full_text)
    chunks = chunk_segments(segments, title, topic, filename)
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (user_id, filename, stored_name, file_type, title, topic,
                                      page_count, chunk_count, summary_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (user_id, filename, stored_name, file_type, title, topic, page_count, len(chunks), now),
        )
        doc_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO knowledge_chunks
               (document_id, user_id, title, topic, content, source, page_number, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (doc_id, user_id, ch["title"], ch["topic"], ch["content"], ch["source"], ch["page_number"], now)
                for ch in chunks
            ],
        )

    return {
        "document_id": doc_id,
        "title": title,
        "topic": topic,
        "file_type": file_type,
        "page_count": page_count,
        "chunk_count": len(chunks),
        "empty": not chunks,
    }
