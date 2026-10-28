import logging

logger = logging.getLogger("study_coach.tokens")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[tokens] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_usage(
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    stream: bool = False,
) -> None:
    """Log prompt/completion token counts reported by an LLM provider, and record them for the usage page."""
    from services import usage  # local import: usage -> database -> config, kept off the import path of llm

    if prompt_tokens is None and completion_tokens is None:
        logger.info("%s | model=%s | stream=%s | tokens=n/a", provider, model, stream)
        usage.record(provider, model, 0, 0)
        return

    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    usage.record(provider, model, prompt_tokens, completion_tokens)
    logger.info(
        "%s | model=%s | stream=%s | prompt=%s | completion=%s | total=%s",
        provider,
        model,
        stream,
        prompt_tokens,
        completion_tokens,
        prompt_tokens + completion_tokens,
    )
