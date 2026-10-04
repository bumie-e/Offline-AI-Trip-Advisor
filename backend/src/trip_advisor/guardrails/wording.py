"""Advisory-wording check. The app informs; it never certifies a place or road as safe or unsafe."""

import re

# (pattern, why). Word boundaries keep "safety notes" and "safeguard" legal.
_BANNED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(un)?safe(ly)?\b", re.IGNORECASE), "safe/unsafe verdict"),
    (re.compile(r"\bdanger(ous)?\b", re.IGNORECASE), "danger verdict"),
    (re.compile(r"\bguarantee[sd]?\b", re.IGNORECASE), "guarantee"),
    (re.compile(r"\b(risk[- ]free|no risk|zero risk)\b", re.IGNORECASE), "no-risk claim"),
    (re.compile(r"\b(definitely|certainly|without (a )?doubt|for sure)\b", re.IGNORECASE), "false certainty"),
    (re.compile(r"\b(you )?(must not|mustn't|should never|do not) (travel|go|visit)\b", re.IGNORECASE),
     "command not to travel"),
]  # fmt: skip


def wording_problems(text: str) -> list[str]:
    return [why for pattern, why in _BANNED if pattern.search(text)]
