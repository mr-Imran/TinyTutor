import io

from docx import Document as DocxDocument

from services.document_processor import Segment, chunk_segments


def test_chunks_keep_paragraphs_and_pages():
    para = "Sentence one is here. " * 10  # ~220 chars
    segments = [Segment(f"{para}\n\n{para}\n\n{para}", page_number=1), Segment("Short page two.", page_number=2)]
    chunks = chunk_segments(segments, "Doc", "Topic", "doc.pdf")
    assert chunks[-1]["page_number"] == 2
    assert all(len(c["content"]) <= 700 for c in chunks)
    assert chunks[-1]["content"] == "Short page two."
    assert chunks[0]["title"] == "Doc — Part 1"


def test_long_paragraph_is_split():
    text = "word " * 500
    chunks = chunk_segments([Segment(text)], "Doc", "T", "s")
    assert len(chunks) > 3
    assert all(c["page_number"] is None for c in chunks)


def _docx_bytes(text: str) -> bytes:
    doc = DocxDocument()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_upload_txt_and_docx_then_search(client, db):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("cell_biology.txt", b"Mitochondria make ATP.\n\nRibosomes build proteins.")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["file_type"] == "txt"

    r = client.post(
        "/api/documents/upload", files={"file": ("plants.docx", _docx_bytes("Chlorophyll absorbs light energy."))}
    )
    assert r.status_code == 200, r.text

    hits = client.get("/api/search", params={"q": "chlorophyll"}).json()["results"]
    assert len(hits) == 1 and "[[Chlorophyll]]" in hits[0]["snippet"]


def test_upload_rejects_unknown_type(client):
    r = client.post("/api/documents/upload", files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 400


def test_same_filename_does_not_overwrite_and_delete_removes_file(client, db):
    a = client.post("/api/documents/upload", files={"file": ("notes.txt", b"First version about atoms.")}).json()
    b = client.post("/api/documents/upload", files={"file": ("notes.txt", b"Second version about stars.")}).json()
    assert len(list((db / "uploads").iterdir())) == 2

    assert client.delete(f"/api/documents/{a['document_id']}").status_code == 200
    assert len(list((db / "uploads").iterdir())) == 1
    assert client.get("/api/search", params={"q": "atoms"}).json()["results"] == []
    stars = client.get("/api/search", params={"q": "stars"}).json()["results"]
    assert stars[0]["document_id"] == b["document_id"]


def test_upload_generates_summary_and_concept_map(client):
    doc = client.post("/api/documents/upload", files={"file": ("photosynthesis.txt", b"Plants use light.")}).json()
    detail = client.get(f"/api/documents/{doc['document_id']}").json()
    assert detail["summary_status"] == "done"
    assert detail["summary"] == "Plants turn light into chemical energy."
    terms = {c["term"]: c for c in detail["concepts"]}
    # Links to terms that are not on the map are dropped.
    assert terms["Photosynthesis"]["related"] == ["Chlorophyll"]


def test_pdf_upload_keeps_page_numbers(client):
    import fitz

    pdf = fitz.open()
    for text in ("Page one talks about osmosis in cells.", "Page two covers diffusion gradients."):
        pdf.new_page().insert_text((72, 72), text)
    data = pdf.tobytes()
    pdf.close()

    doc = client.post("/api/documents/upload", files={"file": ("membranes.pdf", data)}).json()
    assert doc["page_count"] == 2
    hit = client.get("/api/search", params={"q": "diffusion"}).json()["results"][0]
    assert hit["page_number"] == 2
    pdf_resp = client.get(f"/api/exam-tools/pdf/{doc['document_id']}/file")
    assert pdf_resp.status_code == 200 and pdf_resp.content[:4] == b"%PDF"
