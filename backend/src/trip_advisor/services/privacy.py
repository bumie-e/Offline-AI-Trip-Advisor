"""Minimal personal-data handling for reports. Collect less, keep it coarse, expire it."""

import re

COORD_DECIMALS = 2  # about 1 km: enough to place a report on a road, not at a doorstep

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
REDACTED = "[removed]"


def round_coord(value: float | None) -> float | None:
    return None if value is None else round(value, COORD_DECIMALS)


def redact(text: str) -> str:
    """Strip phone numbers, emails and links that people sometimes type into free-text notes."""
    for pattern in (_EMAIL, _URL, _PHONE):
        text = pattern.sub(REDACTED, text)
    return text.strip()
