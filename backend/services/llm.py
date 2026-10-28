"""Provider-agnostic LLM access: Ollama, OpenAI-compatible, Anthropic Claude, Google Gemini.

All providers take the same input: a system prompt plus a list of
{"role": "user" | "assistant", "content": str} messages.
"""
import base64
import json
from typing import AsyncIterator

import httpx

from config import OLLAMA_MODEL, OLLAMA_URL
from services.settings_store import get_setting
from services.token_log import log_usage

PROVIDERS = ("ollama", "openai", "anthropic", "gemini")

DEFAULT_MODELS = {
    "ollama": OLLAMA_MODEL,
    "openai": "",
    "anthropic": "claude-opus-5-5",
    "gemini": "gemini-2.5-flash",
}

DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Claude models that accept output_config.effort / server-side refusal fallbacks.
_CLAUDE_EFFORT_PREFIXES = (
    "claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5",
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
)
_CLAUDE_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

TIMEOUT = 120.0
VISION_TIMEOUT = 300.0
MAX_TOKENS = 16000


class LLMError(Exception):
    pass


def get_llm_config(provider: str | None = None) -> dict:
    provider = provider or get_setting("llm_provider", "ollama")
    if provider not in PROVIDERS:
        provider = "ollama"
    cfg = {
        "provider": provider,
        "model": get_setting(f"llm_model_{provider}", DEFAULT_MODELS[provider]),
    }
    if provider == "ollama":
        cfg["base_url"] = get_setting("ollama_url", OLLAMA_URL).rstrip("/")
    elif provider == "openai":
        cfg["base_url"] = get_setting("openai_base_url", DEFAULT_OPENAI_BASE).rstrip("/")
        cfg["api_key"] = get_setting("openai_api_key")
    elif provider == "anthropic":
        cfg["api_key"] = get_setting("anthropic_api_key")
    elif provider == "gemini":
        cfg["api_key"] = get_setting("gemini_api_key")
    return cfg


def offline_hint(cfg: dict) -> str:
    if cfg["provider"] == "ollama":
        return f"Please start Ollama and run: ollama pull {cfg['model']}."
    return f"Check the {cfg['provider']} API key and model in Settings."


async def complete(
    messages: list[dict],
    system: str = "",
    json_mode: bool = False,
    cfg: dict | None = None,
    temperature: float | None = None,
) -> str:
    """temperature is best effort: Claude models that take an effort setting have no sampling knobs."""
    cfg = cfg or get_llm_config()
    if temperature is not None:
        cfg = {**cfg, "temperature": temperature}
    if not cfg.get("model"):
        raise LLMError(f"No model selected for {cfg['provider']}.")
    try:
        return await _COMPLETE[cfg["provider"]](cfg, messages, system, json_mode)
    except LLMError:
        raise
    except Exception as e:  # network errors, SDK errors, malformed responses
        raise LLMError(str(e)) from e


async def stream(messages: list[dict], system: str = "", cfg: dict | None = None) -> AsyncIterator[str]:
    cfg = cfg or get_llm_config()
    if not cfg.get("model"):
        raise LLMError(f"No model selected for {cfg['provider']}.")
    try:
        async for chunk in _STREAM[cfg["provider"]](cfg, messages, system):
            yield chunk
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(str(e)) from e


VISION_PROMPT = (
    "Transcribe all text in this image exactly, keeping the reading order. "
    "Then describe every diagram, chart, table or figure in plain sentences so a student "
    "can study from the description alone. Do not use markdown."
)


async def describe_image(image: bytes, mime: str, prompt: str = VISION_PROMPT, cfg: dict | None = None) -> str:
    """Send one image to the active provider's vision model and return its text."""
    cfg = dict(cfg or get_llm_config())
    # Ollama text models usually cannot see; a separate vision model can be set (e.g. qwen2.5vl).
    cfg["model"] = get_setting(f"llm_vision_model_{cfg['provider']}") or cfg.get("model")
    if not cfg.get("model"):
        raise LLMError(f"No model selected for {cfg['provider']}.")
    try:
        return await _VISION[cfg["provider"]](cfg, image, mime, prompt)
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(str(e)) from e


async def _ollama_vision(cfg, image, mime, prompt):
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(image).decode()]}],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        resp = await client.post(f"{cfg['base_url']}/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
    log_usage("ollama/vision", cfg["model"], data.get("prompt_eval_count"), data.get("eval_count"))
    return data["message"]["content"]


async def _openai_vision(cfg, image, mime, prompt):
    data_url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    body = {
        "model": cfg["model"],
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}],
        }],
    }
    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        resp = await client.post(f"{cfg['base_url']}/chat/completions", json=body, headers=_openai_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usage") or {}
    log_usage("openai/vision", cfg["model"], usage.get("prompt_tokens"), usage.get("completion_tokens"))
    return data["choices"][0]["message"].get("content") or ""


async def _anthropic_vision(cfg, image, mime, prompt):
    client = _anthropic_client(cfg)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(image).decode()}},
        {"type": "text", "text": prompt},
    ]
    params = _anthropic_params(cfg, [{"role": "user", "content": "x"}], "")
    params["messages"] = [{"role": "user", "content": content}]
    resp = await client.beta.messages.create(**params)
    log_usage("anthropic/vision", resp.model, resp.usage.input_tokens, resp.usage.output_tokens)
    if resp.stop_reason == "refusal":
        raise LLMError("Claude declined to read this image.")
    return "".join(b.text for b in resp.content if b.type == "text")


async def _gemini_vision(cfg, image, mime, prompt):
    body = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}},
        {"text": prompt},
    ]}]}
    url = f"{GEMINI_BASE}/models/{cfg['model']}:generateContent"
    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=_gemini_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usageMetadata") or {}
    log_usage("gemini/vision", cfg["model"], usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
    return _gemini_text(data)


async def list_models(provider: str) -> list[str]:
    cfg = get_llm_config(provider)
    try:
        return await _MODELS[provider](cfg)
    except Exception as e:
        raise LLMError(str(e)) from e


# ---------------------------------------------------------------- Ollama

async def _ollama_complete(cfg, messages, system, json_mode):
    body = {"model": cfg["model"], "messages": _with_system(messages, system), "stream": False}
    if json_mode:
        body["format"] = "json"
    if cfg.get("temperature") is not None:
        body["options"] = {"temperature": cfg["temperature"]}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{cfg['base_url']}/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
    log_usage("ollama", cfg["model"], data.get("prompt_eval_count"), data.get("eval_count"))
    return data["message"]["content"]


async def _ollama_stream(cfg, messages, system):
    body = {"model": cfg["model"], "messages": _with_system(messages, system), "stream": True}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", f"{cfg['base_url']}/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    log_usage("ollama", cfg["model"], data.get("prompt_eval_count"), data.get("eval_count"), stream=True)
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk


async def _ollama_models(cfg):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{cfg['base_url']}/api/tags")
        resp.raise_for_status()
    return sorted(m["name"] for m in resp.json().get("models", []))


# ---------------------------------------------------------------- OpenAI-compatible

def _openai_headers(cfg):
    return {"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {}


async def _openai_complete(cfg, messages, system, json_mode):
    body = {"model": cfg["model"], "messages": _with_system(messages, system)}
    if cfg.get("temperature") is not None:
        body["temperature"] = cfg["temperature"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{cfg['base_url']}/chat/completions", json=body, headers=_openai_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usage") or {}
    log_usage("openai", cfg["model"], usage.get("prompt_tokens"), usage.get("completion_tokens"))
    return data["choices"][0]["message"].get("content") or ""


async def _openai_stream(cfg, messages, system):
    body = {"model": cfg["model"], "messages": _with_system(messages, system), "stream": True}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST", f"{cfg['base_url']}/chat/completions", json=body, headers=_openai_headers(cfg)
        ) as resp:
            resp.raise_for_status()
            usage = {}
            async for data in _sse_json(resp):
                usage = data.get("usage") or usage  # only some compatible servers send it when streaming
                for choice in data.get("choices") or []:
                    chunk = (choice.get("delta") or {}).get("content")
                    if chunk:
                        yield chunk
    log_usage("openai", cfg["model"], usage.get("prompt_tokens"), usage.get("completion_tokens"), stream=True)


async def _openai_models(cfg):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{cfg['base_url']}/models", headers=_openai_headers(cfg))
        resp.raise_for_status()
    return sorted(m["id"] for m in resp.json().get("data", []))


# ---------------------------------------------------------------- Anthropic Claude

def _anthropic_client(cfg):
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("The 'anthropic' package is not installed (pip install anthropic).") from e
    # With no key in settings, the SDK resolves ANTHROPIC_API_KEY / an `ant auth login` profile.
    return anthropic.AsyncAnthropic(api_key=cfg.get("api_key") or None, timeout=TIMEOUT)


def _anthropic_params(cfg, messages, system):
    model = cfg["model"]
    params = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": _merge_roles(messages),
    }
    if system:
        params["system"] = system
    if model.startswith(_CLAUDE_EFFORT_PREFIXES):
        # Tutoring replies are short; low effort keeps latency and cost down.
        params["output_config"] = {"effort": "low"}
    if model in _CLAUDE_FALLBACK_MODELS:
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"
    return params


async def _anthropic_complete(cfg, messages, system, json_mode):
    client = _anthropic_client(cfg)
    resp = await client.beta.messages.create(**_anthropic_params(cfg, messages, system))
    log_usage("anthropic", resp.model, resp.usage.input_tokens, resp.usage.output_tokens)
    if resp.stop_reason == "refusal":
        raise LLMError("Claude declined to answer this request.")
    return "".join(b.text for b in resp.content if b.type == "text")


async def _anthropic_stream(cfg, messages, system):
    client = _anthropic_client(cfg)
    async with client.beta.messages.stream(**_anthropic_params(cfg, messages, system)) as s:
        async for text in s.text_stream:
            yield text
        final = await s.get_final_message()
    log_usage("anthropic", final.model, final.usage.input_tokens, final.usage.output_tokens, stream=True)
    if final.stop_reason == "refusal":
        yield "\n\n(Claude declined to continue this answer.)"


async def _anthropic_models(cfg):
    client = _anthropic_client(cfg)
    return [m.id async for m in client.models.list()]


# ---------------------------------------------------------------- Google Gemini

def _gemini_body(messages, system, json_mode=False):
    body = {
        "contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in _merge_roles(messages)
        ]
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}
    return body


def _gemini_headers(cfg):
    if not cfg.get("api_key"):
        raise LLMError("Gemini API key is not set.")
    return {"x-goog-api-key": cfg["api_key"]}


def _gemini_text(data):
    parts = []
    for cand in data.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            if part.get("text") and not part.get("thought"):
                parts.append(part["text"])
    return "".join(parts)


async def _gemini_complete(cfg, messages, system, json_mode):
    url = f"{GEMINI_BASE}/models/{cfg['model']}:generateContent"
    body = _gemini_body(messages, system, json_mode)
    if cfg.get("temperature") is not None:
        body.setdefault("generationConfig", {})["temperature"] = cfg["temperature"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=_gemini_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usageMetadata") or {}
    log_usage("gemini", cfg["model"], usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
    return _gemini_text(data)


async def _gemini_stream(cfg, messages, system):
    url = f"{GEMINI_BASE}/models/{cfg['model']}:streamGenerateContent?alt=sse"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST", url, json=_gemini_body(messages, system), headers=_gemini_headers(cfg)
        ) as resp:
            resp.raise_for_status()
            usage = {}
            async for data in _sse_json(resp):
                usage = data.get("usageMetadata") or usage
                chunk = _gemini_text(data)
                if chunk:
                    yield chunk
    log_usage("gemini", cfg["model"], usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), stream=True)


async def _gemini_models(cfg):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{GEMINI_BASE}/models?pageSize=200", headers=_gemini_headers(cfg))
        resp.raise_for_status()
    return sorted(
        m["name"].removeprefix("models/")
        for m in resp.json().get("models", [])
        if "generateContent" in (m.get("supportedGenerationMethods") or [])
    )


# ---------------------------------------------------------------- tool calling
#
# The agent keeps one provider-neutral transcript:
#   {"role": "user", "content": str}
#   {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "args"}], "raw": <provider message>}
#   {"role": "tool", "tool_call_id": str, "name": str, "content": str}
# Each provider converts it on every call. "raw" echoes the provider's own assistant message
# back verbatim, which Claude and Gemini need to continue after a tool call.
# Tools are {"name", "description", "parameters": <JSON schema object>}.

_ollama_tool_support: dict[tuple[str, str], bool] = {}


async def supports_tools(cfg: dict | None = None) -> bool | None:
    """None when it cannot be known right now (Ollama not running)."""
    cfg = cfg or get_llm_config()
    if cfg["provider"] != "ollama":
        return bool(cfg.get("model"))
    key = (cfg["base_url"], cfg["model"])
    if key not in _ollama_tool_support:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{cfg['base_url']}/api/show", json={"model": cfg["model"]})
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None  # not cached: Ollama may simply not be running yet
        caps = data.get("capabilities")
        # Older Ollama versions have no capabilities list; their chat template mentions .Tools instead.
        _ollama_tool_support[key] = "tools" in caps if caps is not None else ".Tools" in (data.get("template") or "")
    return _ollama_tool_support[key]


async def complete_with_tools(
    messages: list[dict], system: str, tools: list[dict], cfg: dict | None = None, allow_calls: bool = True
) -> dict:
    """One model turn. Returns {"text", "tool_calls", "assistant"}; append "assistant" to the transcript.

    allow_calls=False keeps the tool definitions (earlier calls in the transcript refer to them)
    but makes the model answer in text.
    """
    cfg = {**(cfg or get_llm_config()), "allow_calls": allow_calls}
    if not cfg.get("model"):
        raise LLMError(f"No model selected for {cfg['provider']}.")
    try:
        text, calls, raw = await _TOOLS[cfg["provider"]](cfg, messages, system, tools)
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(str(e)) from e
    return {
        "text": text,
        "tool_calls": calls,
        "assistant": {"role": "assistant", "content": text, "tool_calls": calls, "raw": raw,
                      "raw_provider": cfg["provider"]},
    }


def _raw_for(m: dict, provider: str):
    return m.get("raw") if m.get("raw_provider") == provider else None


def _openai_style_messages(messages, system, ollama: bool):
    out = [{"role": "system", "content": system}] if system else []
    for m in messages:
        if m["role"] == "tool":
            item = {"role": "tool", "content": m["content"]}
            if ollama:
                item["tool_name"] = m["name"]
            else:
                item["tool_call_id"] = m["tool_call_id"]
            out.append(item)
        elif m["role"] == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content") or ("" if ollama else None),
                "tool_calls": [
                    {"function": {"name": c["name"], "arguments": c["args"]}} if ollama else
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                    for c in m["tool_calls"]
                ],
            })
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


def _openai_style_tools(tools):
    return [{"type": "function", "function": t} for t in tools]


async def _ollama_tools(cfg, messages, system, tools):
    body = {
        "model": cfg["model"],
        "messages": _openai_style_messages(messages, system, ollama=True),
        "stream": False,
    }
    if tools and cfg.get("allow_calls", True):  # Ollama has no tool_choice; leaving tools out forbids calls
        body["tools"] = _openai_style_tools(tools)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{cfg['base_url']}/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
    log_usage("ollama", cfg["model"], data.get("prompt_eval_count"), data.get("eval_count"))
    msg = data.get("message") or {}
    calls = []
    for i, c in enumerate(msg.get("tool_calls") or []):
        fn = c.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            args = _loads_args(args)
        calls.append({"id": f"call_{i}", "name": fn.get("name", ""), "args": args})
    return msg.get("content") or "", calls, None


async def _openai_tools(cfg, messages, system, tools):
    body = {
        "model": cfg["model"],
        "messages": _openai_style_messages(messages, system, ollama=False),
    }
    if tools:
        body["tools"] = _openai_style_tools(tools)
        if not cfg.get("allow_calls", True):
            body["tool_choice"] = "none"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{cfg['base_url']}/chat/completions", json=body, headers=_openai_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usage") or {}
    log_usage("openai", cfg["model"], usage.get("prompt_tokens"), usage.get("completion_tokens"))
    msg = data["choices"][0]["message"]
    calls = [
        {"id": c["id"], "name": c["function"]["name"], "args": _loads_args(c["function"].get("arguments"))}
        for c in msg.get("tool_calls") or []
    ]
    return msg.get("content") or "", calls, None


def _loads_args(raw) -> dict:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return args if isinstance(args, dict) else {}


def _anthropic_tool_messages(messages):
    out: list[dict] = []
    for m in messages:
        if m["role"] == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            prev = out[-1] if out else None
            if prev and prev["role"] == "user" and isinstance(prev["content"], list) \
                    and prev["content"] and prev["content"][-1].get("type") == "tool_result":
                prev["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        raw = _raw_for(m, "anthropic") if m["role"] == "assistant" else None
        if raw is not None:
            content = raw
        elif m["role"] == "assistant" and m.get("tool_calls"):  # transcript from another provider
            content = ([{"type": "text", "text": m["content"]}] if m.get("content") else []) + [
                {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in m["tool_calls"]
            ]
        else:
            content = m["content"]
        if out and out[-1]["role"] == m["role"]:
            prev = out[-1]
            as_list = lambda c: [{"type": "text", "text": c}] if isinstance(c, str) else list(c)  # noqa: E731
            if isinstance(prev["content"], str) and isinstance(content, str):
                prev["content"] = f"{prev['content']}\n\n{content}"
            else:
                prev["content"] = as_list(prev["content"]) + as_list(content)
        else:
            out.append({"role": m["role"], "content": content})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _anthropic_block_input(block) -> dict:
    """Turn a response content block back into request form."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.model_dump(exclude_none=True)


async def _anthropic_tools(cfg, messages, system, tools):
    client = _anthropic_client(cfg)
    params = _anthropic_params(cfg, [{"role": "user", "content": "x"}], system)
    params["messages"] = _anthropic_tool_messages(messages)
    if tools:
        params["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                           for t in tools]
        if not cfg.get("allow_calls", True):
            params["tool_choice"] = {"type": "none"}
    resp = await client.beta.messages.create(**params)
    log_usage("anthropic", resp.model, resp.usage.input_tokens, resp.usage.output_tokens)
    if resp.stop_reason == "refusal":
        raise LLMError("Claude declined to answer this request.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    calls = [{"id": b.id, "name": b.name, "args": dict(b.input or {})} for b in resp.content if b.type == "tool_use"]
    return text, calls, [_anthropic_block_input(b) for b in resp.content]


def _gemini_tool_contents(messages):
    contents: list[dict] = []
    for m in messages:
        if m["role"] == "tool":
            try:
                result = json.loads(m["content"])
            except json.JSONDecodeError:
                result = m["content"]
            response = {"name": m["name"], "response": {"result": result}}
            if m["tool_call_id"] and not m["tool_call_id"].startswith("gemini_"):
                response["id"] = m["tool_call_id"]
            part = {"functionResponse": response}
            if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][-1]:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
            continue
        role = "model" if m["role"] == "assistant" else "user"
        raw = _raw_for(m, "gemini") if m["role"] == "assistant" else None
        if raw is not None:
            parts = raw
        elif m["role"] == "assistant" and m.get("tool_calls"):
            parts = ([{"text": m["content"]}] if m.get("content") else []) + [
                {"functionCall": {"name": c["name"], "args": c["args"]}} for c in m["tool_calls"]
            ]
        else:
            parts = [{"text": m["content"]}]
        if contents and contents[-1]["role"] == role and "functionResponse" not in contents[-1]["parts"][-1]:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": list(parts)})
    while contents and contents[0]["role"] != "user":
        contents.pop(0)
    return contents


async def _gemini_tools(cfg, messages, system, tools):
    body = {"contents": _gemini_tool_contents(messages)}
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]
        if not cfg.get("allow_calls", True):
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    url = f"{GEMINI_BASE}/models/{cfg['model']}:generateContent"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=_gemini_headers(cfg))
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usageMetadata") or {}
    log_usage("gemini", cfg["model"], usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    calls = [
        {"id": p["functionCall"].get("id") or f"gemini_{i}", "name": p["functionCall"]["name"],
         "args": p["functionCall"].get("args") or {}}
        for i, p in enumerate(parts) if "functionCall" in p
    ]
    return _gemini_text(data), calls, parts


# ---------------------------------------------------------------- helpers

def _with_system(messages, system):
    return ([{"role": "system", "content": system}] if system else []) + list(messages)


def _merge_roles(messages):
    """Claude and Gemini require alternating roles starting with user."""
    merged: list[dict] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1] = {"role": m["role"], "content": f"{merged[-1]['content']}\n\n{m['content']}"}
        else:
            merged.append({"role": m["role"], "content": m["content"]})
    while merged and merged[0]["role"] != "user":
        merged.pop(0)
    return merged


async def _sse_json(resp) -> AsyncIterator[dict]:
    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue


_COMPLETE = {
    "ollama": _ollama_complete,
    "openai": _openai_complete,
    "anthropic": _anthropic_complete,
    "gemini": _gemini_complete,
}
_STREAM = {
    "ollama": _ollama_stream,
    "openai": _openai_stream,
    "anthropic": _anthropic_stream,
    "gemini": _gemini_stream,
}
_VISION = {
    "ollama": _ollama_vision,
    "openai": _openai_vision,
    "anthropic": _anthropic_vision,
    "gemini": _gemini_vision,
}
_TOOLS = {
    "ollama": _ollama_tools,
    "openai": _openai_tools,
    "anthropic": _anthropic_tools,
    "gemini": _gemini_tools,
}
_MODELS = {
    "ollama": _ollama_models,
    "openai": _openai_models,
    "anthropic": _anthropic_models,
    "gemini": _gemini_models,
}
