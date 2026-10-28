import json
import re

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import embeddings, grounding, llm, ollama_admin, transcription
from services.settings_store import SECRET_KEYS, get_setting, mask_secret, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

USER_ID = 1

EDITABLE_KEYS = {"ollama_url", "openai_base_url", *SECRET_KEYS}


class LlmSettingsBody(BaseModel):
    provider: str | None = None
    model: str | None = None
    # Connection fields; a secret sent as "" clears it, omitted (None) leaves it unchanged.
    ollama_url: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None


def _settings_out() -> dict:
    active = llm.get_llm_config()
    return {
        "provider": active["provider"],
        "model": active["model"],
        "providers": {
            p: {"model": llm.get_llm_config(p)["model"], "default_model": llm.DEFAULT_MODELS[p]}
            for p in llm.PROVIDERS
        },
        "ollama_url": llm.get_llm_config("ollama")["base_url"],
        "openai_base_url": llm.get_llm_config("openai")["base_url"],
        "keys": {k: mask_secret(get_setting(k)) for k in sorted(SECRET_KEYS)},
    }


@router.get("/llm")
def get_llm_settings():
    return _settings_out()


@router.put("/llm")
def update_llm_settings(body: LlmSettingsBody):
    provider = body.provider or get_setting("llm_provider", "ollama")
    if provider not in llm.PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {provider}")
    if body.provider:
        set_setting("llm_provider", body.provider)
    if body.model is not None:
        set_setting(f"llm_model_{provider}", body.model.strip())
    for key in EDITABLE_KEYS:
        value = getattr(body, key)
        if value is not None:
            set_setting(key, value.strip())
    return _settings_out()


@router.get("/llm/models")
async def models(provider: str):
    if provider not in llm.PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {provider}")
    try:
        return {"provider": provider, "models": await llm.list_models(provider), "error": None}
    except llm.LLMError as e:
        return {"provider": provider, "models": [], "error": str(e)}


@router.get("/llm/health")
async def health():
    """Cheap reachability check: listing models needs a live server / valid key but no tokens."""
    cfg = llm.get_llm_config()
    try:
        available = await llm.list_models(cfg["provider"])
    except llm.LLMError as e:
        return {"ok": False, "provider": cfg["provider"], "model": cfg["model"], "error": str(e)}
    model_found = not available or cfg["model"] in available
    return {
        "ok": bool(cfg["model"]) and model_found,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "error": None if model_found else f"Model '{cfg['model']}' is not available on this provider.",
    }


class EmbeddingSettingsBody(BaseModel):
    provider: str | None = None
    model: str | None = None


class VisionSettingsBody(BaseModel):
    # Separate vision model for the given provider; "" means "use the chat model".
    provider: str
    model: str


def _embedding_out() -> dict:
    return {
        "choice": get_setting("embed_provider", "auto"),
        "choices": list(embeddings.EMBED_PROVIDERS),
        "defaults": embeddings.DEFAULT_EMBED_MODELS,
        **embeddings.index_status(USER_ID),
    }


@router.get("/embeddings")
def get_embedding_settings():
    return _embedding_out()


@router.put("/embeddings")
def update_embedding_settings(body: EmbeddingSettingsBody):
    if body.provider is not None:
        if body.provider not in embeddings.EMBED_PROVIDERS:
            raise HTTPException(400, f"Unknown embedding provider: {body.provider}")
        set_setting("embed_provider", body.provider)
    if body.model is not None:
        provider = embeddings.get_embed_config()["provider"]
        if not provider:
            raise HTTPException(400, "Embeddings are turned off")
        set_setting(f"embed_model_{provider}", body.model.strip())
    return _embedding_out()


@router.post("/embeddings/reindex")
async def reindex(limit: int = 2000):
    """Embed chunks missing a vector for the current model. Call repeatedly for huge libraries."""
    try:
        embedded = await embeddings.index_chunks(USER_ID, limit=min(max(limit, 1), 5000))
    except embeddings.EmbeddingError as e:
        return {**_embedding_out(), "embedded": 0, "error": str(e)}
    return {**_embedding_out(), "embedded": embedded, "error": None}


MODEL_NAME = re.compile(r"^[\w.\-/:]{1,120}$")


class PullBody(BaseModel):
    name: str


class GroundingBody(BaseModel):
    enabled: bool | None = None
    ai_check: bool | None = None


class TranscriptionBody(BaseModel):
    model: str | None = None
    language: str | None = None


@router.get("/ollama")
async def ollama_overview():
    info = ollama_admin.system_info()
    try:
        models, error = await ollama_admin.installed_models(), None
    except httpx.HTTPError as e:
        models, error = [], f"Ollama is not reachable at {llm.get_llm_config('ollama')['base_url']}: {e}"
    names = {m["name"] for m in models}
    return {"system": info, "installed": models, "catalog": ollama_admin.recommendations(info, names), "error": error}


@router.post("/ollama/pull")
async def ollama_pull(body: PullBody):
    """Newline-delimited JSON progress events from Ollama's download."""
    if not MODEL_NAME.match(body.name):
        raise HTTPException(400, "Invalid model name")

    async def events():
        try:
            async for event in ollama_admin.pull(body.name):
                yield json.dumps(event) + "\n"
        except httpx.HTTPError as e:
            yield json.dumps({"status": "error", "error": f"Ollama is not reachable: {e}"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.delete("/ollama/models/{name:path}")
async def ollama_delete(name: str):
    if not MODEL_NAME.match(name):
        raise HTTPException(400, "Invalid model name")
    try:
        await ollama_admin.delete(name)
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Could not delete {name}: {e}")
    return {"ok": True}


@router.get("/grounding")
def get_grounding():
    return grounding.settings()


@router.put("/grounding")
def update_grounding(body: GroundingBody):
    return grounding.save_settings(body.enabled, body.ai_check)


@router.get("/transcription")
def get_transcription():
    return transcription.settings()


@router.put("/transcription")
def update_transcription(body: TranscriptionBody):
    try:
        return transcription.save_settings(body.model, body.language)
    except transcription.TranscriptionError as e:
        raise HTTPException(400, str(e))


@router.get("/vision")
def get_vision_settings():
    return {p: get_setting(f"llm_vision_model_{p}", "") for p in llm.PROVIDERS}


@router.put("/vision")
def update_vision_settings(body: VisionSettingsBody):
    if body.provider not in llm.PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    set_setting(f"llm_vision_model_{body.provider}", body.model.strip())
    return get_vision_settings()
