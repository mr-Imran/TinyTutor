import re

HUMAN_STYLE_RULE = (
    "Write like a warm human mentor speaking to a student. "
    "Use normal conversational sentences and short paragraphs. "
    "Never use markdown, hashtags, asterisks, bullet lists, or JSON unless the user explicitly asks for data."
)


def humanize_text(text: str) -> str:
    """Strip common markdown so UI reads like plain human text."""
    if not text:
        return text
    t = text
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^[\-\*]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
