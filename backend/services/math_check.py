"""Algebra checks with sympy: equivalent answers and verified worked solutions.

Equivalence is tested numerically at random points (fast, and never hangs the way symbolic
simplification can), then confirmed symbolically for exact numbers. Anything that does not parse
returns None so callers fall back to AI grading.
"""
import json
import random
import re

from services import llm

MAX_LEN = 200
SAMPLES = 6
TOLERANCE = 1e-7

_LATEX = [
    (r"\\left|\\right", ""),
    (r"\\cdot|\\times", "*"),
    (r"\\div", "/"),
    (r"\\pi", "pi"),
    (r"\\infty", "oo"),
    (r"\\ln", "log"),
    (r"\\(sin|cos|tan|log|exp)", r"\1"),
    (r"\\,|\\;|\\!|\\ ", ""),
]


def _latex_to_text(s: str) -> str:
    s = s.strip().strip("$").strip()
    s = re.sub(r"^\\\(|\\\)$|^\\\[|\\\]$", "", s).strip()
    for pattern, repl in _LATEX:
        s = re.sub(pattern, repl, s)
    # \frac{a}{b} and \sqrt{x}, innermost first so nesting works
    for _ in range(5):
        s2 = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
        s2 = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", s2)
        if s2 == s:
            break
        s = s2
    s = s.replace("{", "(").replace("}", ")")
    return s.replace("×", "*").replace("÷", "/").replace("−", "-").replace("·", "*")


def looks_mathematical(text: str) -> bool:
    """True for answers like '2x+3', '3/4', 'x = 5', '\\frac{1}{2}', not for prose."""
    if not text or len(text) > MAX_LEN:
        return False
    if "$" in text or "\\" in text:
        return True
    words = re.findall(r"[A-Za-z]{4,}", text)
    return bool(re.search(r"\d|[=^*/+]", text)) and len(words) <= 1


def parse(text: str, strip_assignment: bool = True):
    """sympy expression, or for an equation lhs - rhs. None when it does not parse.

    With strip_assignment, an answer written as 'x = 5' is read as the value 5.
    """
    if not looks_mathematical(text):
        return None
    from sympy.parsing.sympy_parser import (
        convert_xor, implicit_multiplication_application, parse_expr, standard_transformations,
    )

    s = _latex_to_text(text)
    s = re.sub(r"^\s*[A-Za-z]\w*\s*=\s*(?=[^=]*$)", "", s) if strip_assignment and s.count("=") == 1 and _is_assignment(s) else s
    transforms = standard_transformations + (implicit_multiplication_application, convert_xor)
    try:
        if s.count("=") == 1:
            lhs, rhs = s.split("=")
            return parse_expr(lhs, transformations=transforms) - parse_expr(rhs, transformations=transforms)
        return parse_expr(s, transformations=transforms)
    except Exception:  # sympy raises many error types for bad input
        return None


def _is_assignment(s: str) -> bool:
    """'x = 5' is an answer value, '2x + 3 = 7' is an equation."""
    lhs = s.split("=")[0].strip()
    return bool(re.fullmatch(r"[A-Za-z]\w*", lhs))


def _samples(expr_a, expr_b):
    symbols = sorted(expr_a.free_symbols | expr_b.free_symbols, key=str)
    rng = random.Random(7)
    for _ in range(SAMPLES):
        yield {s: rng.uniform(0.5, 2.5) for s in symbols}


def _numeric(expr, point) -> complex | None:
    try:
        value = complex(expr.evalf(subs=point))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return value if value == value else None  # NaN check


def equivalent(a: str, b: str) -> bool | None:
    ea, eb = parse(a), parse(b)
    if ea is None or eb is None:
        return None
    try:
        if not ea.free_symbols and not eb.free_symbols:
            return abs(complex(ea.evalf()) - complex(eb.evalf())) < TOLERANCE * max(1, abs(complex(eb.evalf())))
        checked = 0
        for point in _samples(ea, eb):
            va, vb = _numeric(ea, point), _numeric(eb, point)
            if va is None or vb is None:
                continue
            checked += 1
            if abs(va - vb) > TOLERANCE * max(1, abs(vb)):
                return False
        return True if checked else None
    except Exception:
        return None


def same_equation(a, b) -> bool | None:
    """Two equations (as lhs - rhs expressions) have the same solutions if one is a nonzero
    constant multiple of the other: 2x + 3 = 7, 2x = 4 and x = 2 all match."""
    if a is None or b is None:
        return None
    ratio = None
    checked = 0
    for point in _samples(a, b):
        va, vb = _numeric(a, point), _numeric(b, point)
        if va is None or vb is None:
            continue
        if abs(vb) < TOLERANCE:
            if abs(va) > TOLERANCE:
                return False
            continue
        r = va / vb
        if abs(r) < TOLERANCE:
            return False
        if ratio is None:
            ratio = r
        elif abs(r - ratio) > TOLERANCE * max(1, abs(ratio)):
            return False
        checked += 1
    return True if checked else None


SOLVE_SYSTEM = (
    "You solve math problems step by step for a student. Return ONLY valid JSON, no markdown: "
    '{"steps":[{"explanation":"what this step does, one sentence","expression":"the math after this step"}],'
    '"final_answer":"the answer"}. '
    "Write every expression in plain math syntax a calculator understands, like 2*x + 3 = 7 or (x+1)^2, "
    "or in LaTeX. Keep one transformation per step. If the problem has no algebra, use an empty expression."
)


def verify_steps(steps: list[dict]) -> list[dict]:
    """Mark each step verified (follows from the previous one), mismatch, or unchecked."""
    out = []
    prev = None
    for step in steps:
        expr_text = str(step.get("expression") or "").strip()
        expr = parse(expr_text, strip_assignment=False) if expr_text else None
        status = "unchecked"
        if expr is not None and prev is not None:
            prev_eq, cur_eq = "=" in prev[0], "=" in expr_text
            if prev_eq and cur_eq:
                ok = same_equation(prev[1], expr)
            elif not prev_eq and not cur_eq:
                ok = equivalent(prev[0], expr_text)
            else:
                ok = None
            status = {True: "verified", False: "mismatch", None: "unchecked"}[ok]
        out.append({"explanation": str(step.get("explanation", "")).strip(), "expression": expr_text, "status": status})
        if expr is not None:
            prev = (expr_text, expr)
    return out


async def solve(problem: str) -> dict:
    from services.ai import _extract_json

    raw = await llm.complete([{"role": "user", "content": f"Problem: {problem}"}], system=SOLVE_SYSTEM,
                             json_mode=True, temperature=0)
    data = json.loads(_extract_json(raw))
    steps = [s for s in data.get("steps") or [] if isinstance(s, dict)]
    checked = verify_steps(steps)
    return {
        "problem": problem,
        "steps": checked,
        "final_answer": str(data.get("final_answer", "")).strip(),
        "verified": sum(1 for s in checked if s["status"] == "verified"),
        "mismatches": sum(1 for s in checked if s["status"] == "mismatch"),
    }
