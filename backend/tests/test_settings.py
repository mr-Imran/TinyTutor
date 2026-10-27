from services import llm


def test_settings_roundtrip_masks_keys(client):
    r = client.put("/api/settings/llm", json={
        "provider": "anthropic", "model": "claude-sonnet-5-5", "anthropic_api_key": "sk-ant-1234567890abcd",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-sonnet-5-5"
    assert body["keys"]["anthropic_api_key"] == "sk-a…abcd"
    assert "1234567890" not in r.text

    # Omitted key is unchanged; empty string clears it.
    r = client.put("/api/settings/llm", json={"provider": "anthropic"})
    assert r.json()["keys"]["anthropic_api_key"] == "sk-a…abcd"
    r = client.put("/api/settings/llm", json={"anthropic_api_key": ""})
    assert r.json()["keys"]["anthropic_api_key"] == ""


def test_unknown_provider_rejected(client):
    assert client.put("/api/settings/llm", json={"provider": "nope"}).status_code == 400


def test_models_endpoint_reports_errors(client, monkeypatch):
    async def boom(provider):
        raise llm.LLMError("connection refused")

    monkeypatch.setattr(llm, "list_models", boom)
    r = client.get("/api/settings/llm/models", params={"provider": "ollama"})
    assert r.json() == {"provider": "ollama", "models": [], "error": "connection refused"}
    h = client.get("/api/settings/llm/health").json()
    assert h["ok"] is False and "refused" in h["error"]
