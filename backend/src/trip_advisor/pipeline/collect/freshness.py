"""Recency window and 'newest wins' selection for road-state evidence."""

import calendar
from datetime import date

from trip_advisor.sites import Corridor

from .models import CorridorEvidence, DocKind, RawDocument

WINDOW_MONTHS = 3

# Physical or official road conditions. Only these can be the selected report.
STRONG_TERMS = (
    "closure", "closed", "shut", "diversion", "rehabilitat", "reconstruct", "repair",
    "construction", "pothole", "bad road", "deplorable", "failed section", "flood",
    "collapse", "palliative", "impassable", "washed", "block", "protest", "barricade",
)  # fmt: skip
ROAD_NOUNS = ("road", "expressway", "highway", "bridge", "route", "flyover", "interchange")
TRAVEL_WORDS = ("motorist", "commuter", "traffic", "movement", "travel", "driver", "vehicle")
# Traffic-only mentions (protests, congestion, opinion pieces). Kept as secondary evidence.
WEAK_TERMS = ("gridlock",)
CONDITION_TERMS = STRONG_TERMS + WEAK_TERMS


def cutoff(today: date, months: int = WINDOW_MONTHS) -> date:
    """The date `months` calendar months before today (day clamped to month length)."""
    month_index = today.year * 12 + today.month - 1 - months
    year, month = divmod(month_index, 12)
    day = min(today.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def _norm(text: str) -> str:
    return text.lower().replace("–", "-").replace("—", "-")


def is_relevant(doc: RawDocument, corridor: Corridor) -> bool:
    haystack = _norm(f"{doc.title} {doc.text}")
    mentions = any(_norm(t) in haystack for t in corridor.match_terms)
    condition = any(t in haystack for t in CONDITION_TERMS)
    return mentions and condition


def is_strong(doc: RawDocument) -> bool:
    """A real road-condition report, not a passing mention in an unrelated story.

    A condition word in the title counts if the item also has road or travel context
    (so flood-relief or political stories fall out). One only in the snippet counts
    only if the title itself names a road, bridge, route and so on.
    """
    title = _norm(doc.title)
    text = _norm(f"{doc.title} {doc.text}")
    if any(t in title for t in STRONG_TERMS):
        return any(t in text for t in ROAD_NOUNS + TRAVEL_WORDS)
    return any(t in title for t in ROAD_NOUNS) and any(t in text for t in STRONG_TERMS)


def is_fresh(doc: RawDocument, today: date) -> bool:
    return doc.published is not None and cutoff(today) <= doc.published <= today


def select_latest(docs: list[RawDocument], corridor: Corridor, today: date) -> CorridorEvidence:
    """Newest fresh item that describes a real road condition wins. Gov notices win ties.

    Fresh items that only mention traffic are kept in `others`, never selected.
    """
    usable = {d.id: d for d in docs if is_fresh(d, today) and is_relevant(d, corridor)}.values()
    ranked = sorted(
        usable,
        key=lambda d: (d.published or date.min, d.kind == DocKind.GOV_NOTICE),
        reverse=True,
    )
    selected = next((d for d in ranked if is_strong(d)), None)
    return CorridorEvidence(
        corridor=corridor.name,
        selected=selected,
        others=[d for d in ranked if d is not selected],
    )
