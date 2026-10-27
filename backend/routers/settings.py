from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import llm
from services.settings_store import SECRET_KEYS, get_setting, mask_secret, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

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
