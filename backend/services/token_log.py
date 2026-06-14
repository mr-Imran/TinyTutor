import logging

logger = logging.getLogger("study_coach.tokens")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[tokens] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_ollama_usage(endpoint: str, model: str, data: dict, stream: bool = False) -> None:
    """Log prompt/completion token counts from an Ollama API response."""
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")

    if prompt_tokens is None and completion_tokens is None:
        logger.info(
            "%s | model=%s | stream=%s | tokens=n/a",
            endpoint,
            model,
            stream,
        )
        return

    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    total = prompt_tokens + completion_tokens

    logger.info(
        "%s | model=%s | stream=%s | prompt=%s | completion=%s | total=%s",
        endpoint,
        model,
        stream,
        prompt_tokens,
        completion_tokens,
        total,
    )
