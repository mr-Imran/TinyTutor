"""Import study material from a URL: web articles, YouTube transcripts, or linked files."""
import asyncio
import re
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlparse

import httpx

from services.document_processor import EXTRACTORS, Segment, process_upload, save_document

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
# Transcript lines are grouped into windows of about this many seconds per segment.
TRANSCRIPT_WINDOW_SECONDS = 90
USER_AGENT = "Mozilla/5.0 (compatible; TinyTutor/2.0; +https://github.com/mr-Imran/TinyTutor)"
STRIP_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe", "sup")
# Page furniture recognised by class or id: menus, reference lists, share bars, cookie banners…
BOILERPLATE = re.compile(
    r"(^|[-_ ])(nav|navbox|menu|footer|sidebar|comments?|share|social|related|references?|reflist|"
    r"cookie|toc|breadcrumbs?|editsection|advert|ads|promo|newsletter|catlinks)([-_ ]|$)",
    re.I,
)
# Headings that start an article's back matter; nothing after them is study content.
BACK_MATTER = re.compile(
    r"^(see also|references|notes|footnotes|citations|sources|bibliography|further reading|"
    r"external links|related articles|comments)$",
    re.I,
)
# "Article title - Site name" / "Article | Site" -> "Article title"
TITLE_SUFFIX = re.compile(r"\s+[-|–—:]\s+[^-|–—:]{2,40}$")

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class UrlImportError(ValueError):
    pass


def youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        else:
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
                candidate = parts[1]
    return candidate if candidate and _YT_ID.match(candidate) else None


def _validate_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UrlImportError("Enter a full http:// or https:// link.")
    return url


def group_transcript(snippets: list[tuple[float, str]], window: int = TRANSCRIPT_WINDOW_SECONDS) -> list[Segment]:
    """[(start_seconds, text)] -> one Segment per ~window seconds, keeping the window's start time."""
    segments: list[Segment] = []
    start, lines = None, []
    for t, text in snippets:
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        if start is None:
            start = t
        elif t - start >= window:
            segments.append(Segment(" ".join(lines), start_seconds=int(start)))
            start, lines = t, []
        lines.append(text)
    if lines:
        segments.append(Segment(" ".join(lines), start_seconds=int(start or 0)))
    return segments


def _fetch_transcript(video_id: str) -> list[tuple[float, str]]:
    from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        except NoTranscriptFound:
            # Fall back to whatever language the video has (manual captions preferred).
            transcripts = sorted(api.list(video_id), key=lambda t: t.is_generated)
            if not transcripts:
                raise
            fetched = transcripts[0].fetch()
    except TranscriptsDisabled as e:
        raise UrlImportError("This video has captions turned off, so there is no transcript to import.") from e
    except NoTranscriptFound as e:
        raise UrlImportError("No transcript was found for this video.") from e
    except Exception as e:  # network errors, YouTube blocking the request, removed videos
        raise UrlImportError(f"Could not fetch the YouTube transcript: {e}") from e
    return [(s.start, s.text) for s in fetched]


async def _youtube_title(client: httpx.AsyncClient, url: str, video_id: str) -> str:
    try:
        resp = await client.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"})
        resp.raise_for_status()
        return resp.json().get("title") or f"YouTube video {video_id}"
    except (httpx.HTTPError, ValueError):
        return f"YouTube video {video_id}"


def extract_article(html: str) -> tuple[str, str]:
    """Returns (title, text) from an HTML page, keeping headings and paragraphs."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    title = (og.get("content") if og else None) or (soup.title.string if soup.title else "") or "Web page"
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.decomposed:
            continue
        marker = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if BOILERPLATE.search(marker) and tag.name not in ("body", "html", "main", "article"):
            tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote", "td"]):
        if el.find_parent(["li", "blockquote", "td"]) and el.name in ("p",):
            continue  # already captured through its container
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if el.name in ("h2", "h3") and BACK_MATTER.match(text) and blocks:
            break
        if len(text) >= 3:
            blocks.append(text)
    if not blocks:  # pages built from divs only
        blocks = [re.sub(r"\s+", " ", t) for t in root.get_text("\n", strip=True).split("\n") if len(t.strip()) > 2]
    return clean_title(title), "\n\n".join(dict.fromkeys(blocks))


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    shorter = TITLE_SUFFIX.sub("", title)
    return (shorter if len(shorter) >= 4 else title)[:200]


async def import_url(user_id: int, url: str, topic: str | None = None) -> dict:
    url = _validate_url(url)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        video_id = youtube_video_id(url)
        if video_id:
            snippets = await asyncio.to_thread(_fetch_transcript, video_id)
            title = await _youtube_title(client, url, video_id)
            segments = group_transcript(snippets)
            if not segments:
                raise UrlImportError("The transcript is empty.")
            return save_document(
                user_id, filename=title, file_type="youtube", title=title, segments=segments,
                topic=topic, source_url=f"https://www.youtube.com/watch?v={video_id}",
            )

        try:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                body = bytearray()
                async for part in resp.aiter_bytes():
                    body.extend(part)
                    if len(body) > MAX_DOWNLOAD_BYTES:
                        raise UrlImportError("That page or file is larger than 25MB.")
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                final_url = str(resp.url)
        except httpx.HTTPError as e:
            raise UrlImportError(f"Could not download the link: {e}") from e

    # A direct link to a supported file (PDF, slides, images…) is processed like an upload.
    name = PurePosixPath(urlparse(final_url).path).name or "download"
    ext = PurePosixPath(name).suffix.lower()
    if content_type == "application/pdf" and ext != ".pdf":
        name, ext = f"{name}.pdf", ".pdf"
    if ext in EXTRACTORS and ext not in (".txt", ".md") and "html" not in content_type:
        result = await process_upload(user_id, name, bytes(body), topic=topic)
        return result

    if "html" not in content_type and not content_type.startswith("text/"):
        raise UrlImportError(f"Unsupported content type: {content_type or 'unknown'}")
    text_body = bytes(body).decode(resp.encoding or "utf-8", errors="replace")
    if "html" in content_type:
        title, text = extract_article(text_body)
    else:
        title, text = name, text_body
    if len(text.strip()) < 50:
        raise UrlImportError("No readable article text was found on that page.")
    return save_document(
        user_id, filename=title, file_type="web", title=title, segments=[Segment(text)],
        topic=topic, source_url=final_url,
    )
