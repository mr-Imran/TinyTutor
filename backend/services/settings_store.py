import os

from database import get_db

# Settings that fall back to environment variables when not set in the DB.
ENV_FALLBACKS = {
    "llm_provider": "LLM_PROVIDER",
    "ollama_url": "OLLAMA_URL",
    "openai_base_url": "OPENAI_BASE_URL",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
}

SECRET_KEYS = {"openai_api_key", "anthropic_api_key", "gemini_api_key"}


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row and row["value"] not in (None, ""):
        return row["value"]
    env = ENV_FALLBACKS.get(key)
    if env and os.getenv(env):
        return os.getenv(env)
    return default


def set_setting(key: str, value: str | None):
    with get_db() as conn:
        if value is None or value == "":
            conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        else:
            conn.execute(
                """INSERT INTO app_settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value),
            )


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return f"{value[:4]}…{value[-4:]}" if len(value) > 10 else "••••"
