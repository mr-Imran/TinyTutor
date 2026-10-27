import asyncio

from services import llm
from services.settings_store import set_setting


def test_merge_roles_alternates_and_starts_with_user():
    merged = llm._merge_roles([
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
    ])
    assert merged == [
        {"role": "user", "content": "a\n\nb"},
        {"role": "assistant", "content": "c"},
    ]


def test_anthropic_params_effort_and_fallbacks():
    params = llm._anthropic_params({"model": "claude-opus-5-5"}, [{"role": "user", "content": "hi"}], "sys")
    assert params["output_config"] == {"effort": "low"}
    assert params["fallbacks"] == "default"
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
    assert params["system"] == "sys"

    old = llm._anthropic_params({"model": "claude-haiku-4-5"}, [{"role": "user", "content": "hi"}], "")
    assert "output_config" not in old and "fallbacks" not in old and "system" not in old


def test_config_reads_settings_with_defaults(db):
    cfg = llm.get_llm_config()
    assert cfg["provider"] == "ollama"
    assert cfg["model"] == llm.DEFAULT_MODELS["ollama"]

    set_setting("llm_provider", "openai")
    set_setting("llm_model_openai", "my-model")
    set_setting("openai_base_url", "http://localhost:1234/v1/")
    set_setting("openai_api_key", "sk-test")
    cfg = llm.get_llm_config()
    assert cfg == {
        "provider": "openai",
        "model": "my-model",
        "base_url": "http://localhost:1234/v1",
        "api_key": "sk-test",
    }


def test_complete_without_model_raises(db):
    set_setting("llm_provider", "openai")
    try:
        asyncio.run(llm.complete([{"role": "user", "content": "x"}]))
    except llm.LLMError as e:
        assert "No model selected" in str(e)
    else:
        raise AssertionError("expected LLMError")


def test_sse_parsing_skips_done_and_garbage():
    class Resp:
        async def aiter_lines(self):
            lines = ['data: {"a": 1}', "", ": comment", "data: not-json", 'data: {"b": 2}', "data: [DONE]"]
            for line in lines:
                yield line

    async def collect():
        return [d async for d in llm._sse_json(Resp())]

    assert asyncio.run(collect()) == [{"a": 1}, {"b": 2}]


def test_gemini_body_and_text():
    body = llm._gemini_body(
        [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}], "sys", json_mode=True
    )
    assert body["contents"][1]["role"] == "model"
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    data = {"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": "shown"}]}}]}
    assert llm._gemini_text(data) == "shown"
