import asyncio
import json
from datetime import date

import pytest

import database
from services import llm, ollama_admin, transcription, usage


@pytest.fixture
def fake_whisper(monkeypatch):
    calls = []

    def run(path, model_name, language, on_progress):
        calls.append(model_name)
        on_progress(0.5)
        return [(0.0, "Welcome to the lecture on cells."), (40.0, "Cells have membranes."),
                (95.0, "Mitochondria make ATP.")], 120.0

    monkeypatch.setattr(transcription, "_run_whisper", run)
    monkeypatch.setattr(transcription, "installed", lambda: True)
    return calls


def test_audio_upload_is_transcribed_in_background(client, fake_whisper, db):
    resp = client.post("/api/documents/upload", files={"file": ("Lecture 1.mp3", b"ID3 fake audio", "audio/mpeg")})
    data = resp.json()
    assert data["file_type"] == "audio" and data["media_status"] == "pending"
    doc = client.get(f"/api/documents/{data['document_id']}").json()  # background task already ran
    assert doc["media_status"] == "done" and doc["duration_seconds"] == 120.0 and doc["chunk_count"] == 2
    transcript = client.get(f"/api/documents/{data['document_id']}/transcript").json()
    assert [t["start_seconds"] for t in transcript] == [0, 95]
    hits = client.get("/api/search?q=mitochondria").json()["results"]
    assert hits[0]["start_seconds"] == 95 and hits[0]["file_type"] == "audio"
    media = client.get(f"/api/documents/{data['document_id']}/media", headers={"Range": "bytes=0-2"})
    assert media.status_code == 206 and media.content == b"ID3"
    assert fake_whisper == ["base"]


def test_transcription_failure_and_retry(client, monkeypatch, fake_whisper):
    def broken(*a):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(transcription, "_run_whisper", broken)
    doc_id = client.post("/api/documents/upload", files={"file": ("talk.wav", b"RIFF", "audio/wav")}).json()["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["media_status"] == "failed" and "download failed" in doc["media_error"]

    monkeypatch.setattr(transcription, "_run_whisper",
                        lambda path, m, lang, cb: ([(0.0, "Retry worked fine this time.")], 10.0))
    assert client.post(f"/api/documents/{doc_id}/transcribe").json()["media_status"] == "pending"
    assert client.get(f"/api/documents/{doc_id}").json()["media_status"] == "done"


def test_cancel_and_interrupted(db):
    with database.get_db() as conn:
        conn.execute("""INSERT INTO documents (id, user_id, filename, stored_name, file_type, title, topic,
                        media_status, created_at) VALUES (9, 1, 'a.mp3', 'x', 'audio', 'a', 'a', 'pending', 'now')""")
    assert transcription.cancel(1, 9)
    with database.get_db() as conn:
        assert conn.execute("SELECT media_status FROM documents WHERE id = 9").fetchone()[0] == "cancelled"
        conn.execute("UPDATE documents SET media_status = 'running' WHERE id = 9")
    transcription.mark_interrupted()
    with database.get_db() as conn:
        assert conn.execute("SELECT media_status FROM documents WHERE id = 9").fetchone()[0] == "failed"


def test_transcription_settings(client):
    assert client.put("/api/settings/transcription", json={"model": "small", "language": "EN"}).json()["language"] == "en"
    assert client.put("/api/settings/transcription", json={"model": "huge"}).status_code == 400


# ---------------------------------------------------------------- usage

def test_usage_records_feature_and_costs(client, fake_llm, monkeypatch):
    async def logging_complete(messages, system="", json_mode=False, cfg=None, temperature=None):
        llm.log_usage("anthropic", "claude-opus-5-5", 1000, 200)  # what a real provider call records
        return await fake_llm.complete(messages, system, json_mode, cfg, temperature)

    monkeypatch.setattr(llm, "complete", logging_complete)
    client.post("/api/quiz/generate", json={"topic": "Cells"})
    llm.log_usage("ollama", "qwen2.5:3b", 50, 50)  # outside a request: feature "other"

    report = client.get("/api/usage").json()
    features = {f["feature"]: f for f in report["by_feature"]}
    assert features["quiz"]["input_tokens"] == 1000 and features["quiz"]["unpriced_calls"] == 1
    assert features["other"]["cost"] == 0 and features["other"]["unpriced_calls"] == 0

    report = client.put("/api/usage/prices", json={"prices": {"claude-opus-5-5": {"input": 5, "output": 25}}}).json()
    assert report["total"]["cost"] == pytest.approx(0.01)  # 1000*5/1M + 200*25/1M
    report = client.put("/api/usage/budget", json={"monthly_usd": 0.011}).json()
    assert report["budget_status"] == "warning"
    report = client.put("/api/usage/budget", json={"monthly_usd": 0.005}).json()
    assert report["budget_status"] == "over"
    assert client.put("/api/usage/budget", json={"monthly_usd": None}).json()["budget"] is None


def test_usage_report_days(db):
    usage.record("openai", "gpt-x", 10, 5)
    report = usage.usage_report(days=7, today=date.today())
    assert len(report["by_day"]) == 7 and report["by_day"][-1]["calls"] == 1


def test_feature_for_path():
    assert usage.feature_for_path("/api/chat/agent") == "agent"
    assert usage.feature_for_path("/api/chat/stream") == "tutor"
    assert usage.feature_for_path("/api/unknown") == "other"


# ---------------------------------------------------------------- Ollama model manager

def test_recommendations_fit_hardware():
    info = {"model_budget_gb": 6.0}
    rows = {r["name"]: r for r in ollama_admin.recommendations(info, {"nomic-embed-text:latest"})}
    assert rows["qwen2.5:3b"]["fits"] and not rows["qwen2.5:7b"]["fits"]
    assert rows["llama3.2:3b"]["recommended"] or rows["qwen2.5:3b"]["recommended"]
    assert rows["nomic-embed-text"]["installed"] and rows["nomic-embed-text"]["recommended"]
    # Best vision pick is the largest vision model that fits.
    assert rows["gemma3:4b"]["recommended"] and not rows["qwen2.5vl:3b"]["recommended"]


def test_ollama_overview_when_offline(client, monkeypatch):
    import httpx

    async def offline():
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(ollama_admin, "installed_models", offline)
    data = client.get("/api/settings/ollama").json()
    assert data["error"] and data["system"]["ram_total_gb"] > 0 and data["catalog"]


def test_ollama_pull_streams_progress(client, monkeypatch):
    async def pull(name):
        yield {"status": "pulling", "completed": 50, "total": 100, "percent": 50.0}
        yield {"status": "success", "completed": None, "total": None, "percent": None}

    monkeypatch.setattr(ollama_admin, "pull", pull)
    lines = client.post("/api/settings/ollama/pull", json={"name": "qwen2.5:3b"}).text.splitlines()
    assert [json.loads(line)["status"] for line in lines] == ["pulling", "success"]
    assert client.post("/api/settings/ollama/pull", json={"name": "bad name; rm"}).status_code == 400


def test_supports_tools_reads_ollama_capabilities(monkeypatch):
    import httpx

    llm._ollama_tool_support.clear()

    def handler(request):
        body = json.loads(request.content)
        caps = ["completion", "tools"] if body["model"] == "qwen2.5:3b" else ["completion"]
        return httpx.Response(200, json={"capabilities": caps})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    cfg = {"provider": "ollama", "model": "qwen2.5:3b", "base_url": "http://x"}
    assert asyncio.run(llm.supports_tools(cfg))
    assert not asyncio.run(llm.supports_tools({**cfg, "model": "qwen2.5:0.5b"}))


def test_whisper_falls_back_to_cpu_without_cuda(monkeypatch):
    class Seg:
        start, end, text = 0.0, 1.0, "hello"

    class Info:
        duration = 1.0

    devices = []

    class FakeModel:
        def __init__(self, device):
            self.device = device

        def transcribe(self, audio, language=None, vad_filter=True):
            devices.append(self.device)
            if self.device == "auto":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            return iter([Seg()]), Info()

    monkeypatch.setattr(transcription, "_decode_audio", lambda path: [0.0])
    monkeypatch.setattr(transcription, "_load_model", lambda name, device="auto": FakeModel(device))
    monkeypatch.setattr(transcription, "_cpu_only", False)
    assert transcription._run_whisper("x.wav", "tiny", None, lambda f: None) == ([(0.0, "hello")], 1.0)
    assert transcription._run_whisper("x.wav", "tiny", None, lambda f: None)[1] == 1.0
    assert devices == ["auto", "cpu", "cpu"]  # the GPU is not retried after it failed once


def test_supports_tools_unknown_when_ollama_offline(monkeypatch):
    import httpx

    llm._ollama_tool_support.clear()

    def handler(request):
        raise httpx.ConnectError("refused")

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    cfg = {"provider": "ollama", "model": "qwen2.5:3b", "base_url": "http://x"}
    assert asyncio.run(llm.supports_tools(cfg)) is None
