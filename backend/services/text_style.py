import re

HUMAN_STYLE_RULE = (
    "Write like a warm human mentor speaking to a student. "
    "Use normal conversational sentences and short paragraphs. "
    "Never use markdown headings, bold, hashtags, bullet lists, or JSON unless the user explicitly asks for data. "
    "For math, write LaTeX between dollar signs, like $x^2 + 1$ inline or $$\\frac{a}{b}$$ on its own line. "
    "Put code in fenced blocks with the language name, like ```python."
)

# Math ($...$, $$...$$, \(...\), \[...\]) and code (``` fences) pass through humanize_text untouched.
_PROTECTED = re.compile(
    r"```[\s\S]*?```|\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<![\\\w$])\$[^\s$][^$\n]*?(?<![\s\\])\$(?!\d)"
)


def humanize_text(text: str) -> str:
    """Strip common markdown so UI reads like plain human text. Math and code blocks are kept."""
    if not text:
        return text
    kept: list[str] = []

    def stash(m):
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    t = _PROTECTED.sub(stash, text)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^[\-\*]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], t)
    return t.strip()
