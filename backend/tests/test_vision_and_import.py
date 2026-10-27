import httpx
import pytest

from services import importers, llm
from services.importers import extract_article, group_transcript, youtube_video_id


def _png() -> bytes:
    import fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), False)
    return pix.tobytes("png")


def test_image_upload_is_read_by_vision_model(client, fake_llm):
    r = client.post("/api/documents/upload", files={"file": ("notes.png", _png())}).json()
    assert r["file_type"] == "image" and r["chunk_count"] == 1 and r["warnings"] == []
    hit = client.get("/api/search", params={"q": "mitochondria"}).json()["results"][0]
    assert hit["page_number"] == 1
    assert {"vision": "image/png"} in fake_llm.calls


def test_scanned_pdf_page_falls_back_to_vision(client, fake_llm):
    import fitz

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Typed page about osmosis and diffusion across membranes.")
    pdf.new_page()  # blank: no text layer, like a scan
    data = pdf.tobytes()
    pdf.close()

    r = client.post("/api/documents/upload", files={"file": ("scan.pdf", data)}).json()
    assert r["page_count"] == 2
    hit = client.get("/api/search", params={"q": "powerhouse"}).json()["results"][0]
    assert hit["page_number"] == 2


def test_vision_failure_becomes_a_warning(client, monkeypatch):
    async def broken(image, mime, prompt=llm.VISION_PROMPT, cfg=None):
        raise llm.LLMError("model cannot see images")

    monkeypatch.setattr(llm, "describe_image", broken)
    r = client.post("/api/documents/upload", files={"file": ("photo.jpg", _png())}).json()
    assert r["empty"] is True
    assert "cannot see images" in r["warnings"][0]


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
    ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ("https://www.youtube.com/watch?v=short", None),
])
def test_youtube_ids(url, expected):
    assert youtube_video_id(url) == expected


def test_transcript_grouping_keeps_start_times():
    snippets = [(0.0, "intro"), (30.0, "part a"), (95.5, "part b"), (100.0, ""), (200.0, "part c")]
    segs = group_transcript(snippets, window=90)
    assert [(s.start_seconds, s.text) for s in segs] == [(0, "intro part a"), (95, "part b"), (200, "part c")]


def test_article_extraction_drops_navigation():
    html = """<html><head><title>Fallback</title><meta property="og:title" content="Cell Biology 101"></head>
    <body><nav>Home | About</nav><article><h1>Cells</h1><p>Cells are the basic unit of life.</p>
    <ul><li>Nucleus holds DNA.</li></ul></article><footer>Copyright</footer><script>x()</script></body></html>"""
    title, text = extract_article(html)
    assert title == "Cell Biology 101"
    assert text == "Cells\n\nCells are the basic unit of life.\n\nNucleus holds DNA."


def test_import_youtube_url(client, monkeypatch):
    monkeypatch.setattr(importers, "_fetch_transcript", lambda vid: [(0, "Plants use light."), (125, "Chlorophyll is green.")])

    async def title(client, url, vid):
        return "Photosynthesis explained"

    monkeypatch.setattr(importers, "_youtube_title", title)
    r = client.post("/api/documents/import-url", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).json()
    assert r["file_type"] == "youtube" and r["title"] == "Photosynthesis explained"
    hit = client.get("/api/search", params={"q": "chlorophyll"}).json()["results"][0]
    assert hit["start_seconds"] == 125
    assert hit["source_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _mock_http(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(importers.httpx, "AsyncClient", factory)


def test_import_web_article_and_linked_pdf(client, monkeypatch):
    import fitz

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Linked PDF about plate tectonics and earthquakes.")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    def handler(request: httpx.Request):
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=pdf_bytes, headers={"content-type": "application/pdf"})
        paragraphs = "".join(f"<p>Magma rises through the crust and erupts, stage {i}.</p>" for i in range(3))
        html = f"<html><title>Volcanoes</title><body><main>{paragraphs}</main></body></html>"
        return httpx.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})

    _mock_http(monkeypatch, handler)
    web = client.post("/api/documents/import-url", json={"url": "https://example.com/volcanoes", "topic": "Geology"}).json()
    assert web["file_type"] == "web" and web["topic"] == "Geology" and web["title"] == "Volcanoes"
    linked = client.post("/api/documents/import-url", json={"url": "https://example.com/files/tectonics.pdf"}).json()
    assert linked["file_type"] == "pdf"
    assert client.get("/api/search", params={"q": "earthquakes"}).json()["results"][0]["page_number"] == 1


def test_import_rejects_bad_urls(client, monkeypatch):
    assert client.post("/api/documents/import-url", json={"url": "file:///etc/passwd"}).status_code == 400
    _mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"\x00\x01", headers={"content-type": "application/zip"}))
    r = client.post("/api/documents/import-url", json={"url": "https://example.com/archive.zip"})
    assert r.status_code == 400 and "Unsupported" in r.json()["detail"]
