"""Local transcription of lecture recordings (audio or video) with faster-whisper.

Uploads are saved first and transcribed in the background; progress, cancel and errors are kept on
the document row (media_status / media_progress / media_error). Transcripts are grouped into
~90-second chunks that keep their start time, so citations jump to the right moment.
"""
import asyncio
import logging
import threading
import time
from datetime import datetime

from config import UPLOAD_DIR
from database import get_db
from services.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    ".mp3": ("audio", "audio/mpeg"), ".m4a": ("audio", "audio/mp4"), ".wav": ("audio", "audio/wav"),
    ".ogg": ("audio", "audio/ogg"), ".flac": ("audio", "audio/flac"),
    ".mp4": ("video", "video/mp4"), ".webm": ("video", "video/webm"), ".mov": ("video", "video/quicktime"),
    ".mkv": ("video", "video/x-matroska"),
}
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
WHISPER_MODELS = ("tiny", "base", "small", "medium")
DEFAULT_MODEL = "base"
PROGRESS_EVERY_SECONDS = 2.0

_models: dict[str, object] = {}
_lock = threading.Lock()  # one transcription at a time: whisper already uses every core
_cancelled: set[int] = set()
_cpu_only = False  # set after the GPU fails for lack of CUDA libraries


class TranscriptionError(Exception):
    pass


class Cancelled(Exception):
    pass


def installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def settings() -> dict:
    model = get_setting("whisper_model", DEFAULT_MODEL)
    return {
        "model": model if model in WHISPER_MODELS else DEFAULT_MODEL,
        "language": get_setting("whisper_language", ""),
        "models": list(WHISPER_MODELS),
        "installed": installed(),
    }


def save_settings(model: str | None = None, language: str | None = None) -> dict:
    if model is not None:
        if model not in WHISPER_MODELS:
            raise TranscriptionError(f"Unknown model: {model}")
        set_setting("whisper_model", model)
    if language is not None:
        set_setting("whisper_language", language.strip().lower()[:8])
    return settings()


def is_media(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in MEDIA_TYPES)


def media_type(filename: str) -> tuple[str, str]:
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    return MEDIA_TYPES[ext]


def _set(doc_id: int, **fields):
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_db() as conn:
        conn.execute(f"UPDATE documents SET {cols} WHERE id = ?", (*fields.values(), doc_id))


def create_media_document(user_id: int, filename: str, stored_name: str, topic: str | None) -> dict:
    from pathlib import Path

    from services.document_processor import guess_topic

    kind, _ = media_type(filename)
    title = Path(filename).stem
    topic = (topic or "").strip() or guess_topic(title, "")
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (user_id, filename, stored_name, file_type, title, topic, chunk_count,
                                      summary_status, media_status, media_progress, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, 'pending', 'pending', 0, ?)""",
            (user_id, filename, stored_name, kind, title, topic, now),
        )
        doc_id = cur.lastrowid
    return {"document_id": doc_id, "title": title, "topic": topic, "file_type": kind, "page_count": 0,
            "chunk_count": 0, "empty": True, "warnings": [], "media_status": "pending"}


def _load_model(name: str, device: str = "auto"):
    key = f"{name}:{device}"
    if key not in _models:
        from faster_whisper import WhisperModel

        # int8 runs on any CPU and on CUDA; "auto" picks the GPU when one is present.
        _models[key] = WhisperModel(name, device=device, compute_type="int8")
    return _models[key]


def _gpu_libraries_missing(error: Exception) -> bool:
    """An NVIDIA GPU without the CUDA runtime (cuBLAS/cuDNN) installed fails only when decoding starts."""
    text = str(error).lower()
    return any(k in text for k in ("cublas", "cudnn", "cuda", "libcudart"))


SAMPLE_RATE = 16000


def _decode_audio(path: str):
    """Audio track as 16 kHz mono float32. faster-whisper's own decoder passes an argument newer
    PyAV releases removed, so decoding happens here and the model gets the samples."""
    import av
    import numpy as np

    chunks = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    with av.open(path) as container:
        if not container.streams.audio:
            raise TranscriptionError("This file has no audio track.")
        for frame in container.decode(audio=0):
            chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
    chunks.extend(f.to_ndarray() for f in resampler.resample(None))
    if not chunks:
        raise TranscriptionError("No audio could be read from this file.")
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


def _run_whisper(path: str, model_name: str, language: str | None, on_progress) -> tuple[list[tuple[float, str]], float]:
    """Returns ([(start_seconds, text)], duration). on_progress(fraction) may raise Cancelled."""
    audio = _decode_audio(path)

    def run(device: str):
        model = _load_model(model_name, device)
        segments, info = model.transcribe(audio, language=language or None, vad_filter=True)
        out = []
        for seg in segments:  # a generator: decoding happens as we iterate
            out.append((seg.start, seg.text))
            if info.duration:
                on_progress(min(seg.end / info.duration, 1.0))
        return out, float(info.duration or 0)

    global _cpu_only
    if _cpu_only:
        return run("cpu")
    try:
        return run("auto")
    except (RuntimeError, OSError) as e:
        if not _gpu_libraries_missing(e):
            raise
        logger.info("GPU transcription unavailable (%s); using the CPU from now on.", e)
        _cpu_only = True
        _models.pop(f"{model_name}:auto", None)
        return run("cpu")


def _transcribe_blocking(doc_id: int, path: str) -> tuple[list[tuple[float, str]], float]:
    cfg = settings()
    last = [0.0]

    def on_progress(fraction: float):
        if doc_id in _cancelled:
            raise Cancelled()
        if time.monotonic() - last[0] >= PROGRESS_EVERY_SECONDS:
            last[0] = time.monotonic()
            _set(doc_id, media_progress=round(fraction, 3))

    with _lock:
        if doc_id in _cancelled:
            raise Cancelled()
        _set(doc_id, media_status="running", media_progress=0)
        return _run_whisper(path, cfg["model"], cfg["language"], on_progress)


async def transcribe_document(user_id: int, doc_id: int):
    """Background task: transcribe, store chunks, then summarise and index like any upload."""
    from services.document_processor import chunk_segments
    from services.embeddings import index_document_quietly
    from services.importers import group_transcript
    from services.summaries import summarize_document

    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not doc or doc["media_status"] == "cancelled":
        return
    if not installed():
        _set(doc_id, media_status="failed", media_error="faster-whisper is not installed (pip install faster-whisper).",
             summary_status="empty")
        return
    try:
        snippets, duration = await asyncio.to_thread(_transcribe_blocking, doc_id, str(UPLOAD_DIR / doc["stored_name"]))
    except Cancelled:
        _set(doc_id, media_status="cancelled", summary_status="empty")
        return
    except Exception as e:  # model download, decoding or runtime errors
        logger.warning("Transcription failed for document %s: %s", doc_id, e)
        _set(doc_id, media_status="failed", media_error=str(e)[:500], summary_status="empty")
        return
    finally:
        _cancelled.discard(doc_id)

    chunks = chunk_segments(group_transcript(snippets), doc["title"], doc["topic"], doc["filename"])
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO knowledge_chunks (document_id, user_id, title, topic, content, source, start_seconds, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(doc_id, user_id, c["title"], c["topic"], c["content"], c["source"], c["start_seconds"], now)
             for c in chunks],
        )
    _set(doc_id, media_status="done", media_progress=1.0, chunk_count=len(chunks), duration_seconds=duration,
         summary_status="pending" if chunks else "empty")
    if chunks:
        await summarize_document(doc_id)
        await index_document_quietly(user_id, doc_id)


def cancel(user_id: int, doc_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT media_status FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)
        ).fetchone()
    if not row or row["media_status"] not in ("pending", "running"):
        return False
    _cancelled.add(doc_id)
    if row["media_status"] == "pending":
        _set(doc_id, media_status="cancelled", summary_status="empty")
    return True


def mark_interrupted():
    """At startup: transcriptions that were running when the server stopped will not resume."""
    with get_db() as conn:
        conn.execute(
            """UPDATE documents SET media_status = 'failed', media_error = 'Interrupted by a server restart. Press Retry to transcribe again.'
               WHERE media_status IN ('pending', 'running')"""
        )
