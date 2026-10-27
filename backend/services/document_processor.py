import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from pptx import Presentation

from config import CHUNK_OVERLAP, CHUNK_SIZE, UPLOAD_DIR
from database import get_db
from services import llm

logger = logging.getLogger(__name__)

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt", ".md", *IMAGE_TYPES)

# A PDF page with less text than this is treated as scanned: OCR first, then a vision model.
OCR_MIN_CHARS = 25
# Upper bound on pages sent to a vision model per upload, to keep time and cost predictable.
VISION_MAX_PAGES = 30
VISION_DPI = 150


@dataclass
class Segment:
    text: str
    page_number: int | None = None  # 1-based page or slide; None for page-less formats
    start_seconds: int | None = None  # position in a video transcript
    # Rendered page image for scanned pages the text layer and OCR could not read.
    image: bytes | None = None


def extract_pdf_segments(path: Path) -> list[Segment]:
    segments = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, 1):
            text = page.get_text()
            image = None
            if len(text.strip()) < OCR_MIN_CHARS:
                text = _ocr_page(page) or text
                if len(text.strip()) < OCR_MIN_CHARS:
                    image = page.get_pixmap(dpi=VISION_DPI).tobytes("png")
            segments.append(Segment(text, page_number=i, image=image))
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
        segments.append(Segment("\n\n".join(parts), page_number=i))
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
    return [Segment("\n\n".join(parts))]


def extract_text_segments(path: Path) -> list[Segment]:
    return [Segment(path.read_text(encoding="utf-8", errors="replace"))]


def extract_image_segments(path: Path) -> list[Segment]:
    return [Segment("", page_number=1, image=path.read_bytes())]


EXTRACTORS = {
    ".pdf": ("pdf", extract_pdf_segments),
    ".pptx": ("pptx", extract_pptx_segments),
    ".docx": ("docx", extract_docx_segments),
    ".txt": ("txt", extract_text_segments),
    ".md": ("md", extract_text_segments),
    **{ext: ("image", extract_image_segments) for ext in IMAGE_TYPES},
}


async def read_images(segments: list[Segment], mime: str = "image/png") -> list[str]:
    """Fill in text for image segments with the vision model. Returns any error messages."""
    errors = []
    pending = [s for s in segments if s.image is not None]
    for i, seg in enumerate(pending):
        if i >= VISION_MAX_PAGES:
            errors.append(f"Only the first {VISION_MAX_PAGES} image pages were read.")
            break
        try:
            seg.text = await llm.describe_image(seg.image, mime)
        except llm.LLMError as e:
            errors.append(f"Vision model could not read page {seg.page_number}: {e}")
            break  # the same failure would repeat for every page
    for seg in segments:
        seg.image = None
    return errors


def guess_topic(title: str, text: str) -> str:
    name = title.replace("_", " ").replace("-", " ").strip()
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
    for seg in segments:
        for piece in _pack_paragraphs(seg.text):
            chunks.append(
                {
                    "title": f"{title} — Part {len(chunks) + 1}",
                    "topic": topic,
                    "content": piece,
                    "source": source,
                    "page_number": seg.page_number,
                    "start_seconds": seg.start_seconds,
                }
            )
    return chunks


def chunk_text(text: str, title: str, topic: str, source: str) -> list[dict]:
    return chunk_segments([Segment(text)], title, topic, source)


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)


def save_document(
    user_id: int,
    *,
    filename: str,
    file_type: str,
    title: str,
    segments: list[Segment],
    topic: str | None = None,
    stored_name: str | None = None,
    source_url: str | None = None,
    page_count: int = 0,
) -> dict:
    """Chunk segments and store the document plus its chunks."""
    full_text = "\n\n".join(s.text for s in segments)
    topic = (topic or "").strip() or guess_topic(title, full_text)
    chunks = chunk_segments(segments, title, topic, filename)
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (user_id, filename, stored_name, source_url, file_type, title, topic,
                                      page_count, chunk_count, summary_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (user_id, filename, stored_name, source_url, file_type, title, topic, page_count, len(chunks), now),
        )
        doc_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO knowledge_chunks
               (document_id, user_id, title, topic, content, source, page_number, start_seconds, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (doc_id, user_id, ch["title"], ch["topic"], ch["content"], ch["source"],
                 ch["page_number"], ch["start_seconds"], now)
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
        "warnings": [],
    }


async def process_upload(user_id: int, filename: str, file_bytes: bytes, topic: str | None = None) -> dict:
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

    warnings = await read_images(segments, IMAGE_TYPES.get(ext, "image/png"))
    result = save_document(
        user_id,
        filename=filename,
        file_type=file_type,
        title=Path(filename).stem,
        segments=segments,
        topic=topic,
        stored_name=stored_name,
        page_count=sum(1 for s in segments if s.page_number is not None),
    )
    result["warnings"] = warnings
    return result
