"""Turn recent news items into disruption events with plain keyword rules.

Rules, not an LLM: they run offline, are cheap, and every decision can be read and checked.
A missed event is a gap in the delta; a wrong one would mislead, so rules stay conservative.
"""

import re
from datetime import date, timedelta

from trip_advisor.pipeline.collect.models import RawDocument
from trip_advisor.schemas.delta import DisruptionEvent, EventStatus, EventType

RECENT_DAYS = 14
NATIONAL_QUERIES = [
    "NLC strike Nigeria",
    "NUPENG tanker drivers strike",
    "Nigeria flights suspended airlines",
    "Lagos airport aviation unions strike",
]
LOCAL_QUERIES = ["{place} flood", "{place} heavy rain road"]  # {place}: site city

_STRIKE = ("strike", "picket", "shutdown", "shut down", "sit-at-home", "ultimatum")
_FLIGHT = ("flight", "airline", "airport", "aviation", "air peace", "arik")
_SUSPEND = ("suspend", "cancel", "ground", "halt")
_WATER = ("flood", "heavy rain", "downpour", "rainstorm")
_FUEL_UNIONS = ("nupeng", "tanker", "petroleum")
_ROAD_UNIONS = ("nurtw", "transport workers", "road transport")
# A story only matters to a Lagos-arriving visitor if it is national or about Lagos.
_NATIONAL = ("nationwide", "national", "domestic flights", "unions", "lagos", "murtala")

_ENDED = ("called off", "calls off", "suspends strike", "suspended strike", "suspend strike",
          "suspends industrial", "suspended industrial", "ends strike", "end strike", "ended",
          "resume", "shelve", "normalcy")  # fmt: skip
_THREATENED = ("threaten", "ultimatum", "plans to", "warns", "warned", "to begin", "set to", "looms",
               "loom", "notice of", "deadline", "if ")  # fmt: skip
_CONFIRMED = ("begins", "begin ", "commence", "begun", "starts", "started", "on strike",
              "shuts", "ground", "grounded", "grounds", "cancels", "cancelled", "suspends",
              "suspended", "declares")  # fmt: skip


_ENDS_ACTION = re.compile(
    r"\b(suspend\w*|call\w* off|shelve\w*|end\w*|halt\w*)\b[^.,;:]{0,25}\b(strike|industrial action|picketing)"
)


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(t.strip())}", text) for t in terms)


def _status(text: str) -> EventStatus:
    # Order matters: "suspends strike" is an end, not a suspension of service.
    if _has(text, _ENDED) or _ENDS_ACTION.search(text):
        return EventStatus.ENDED
    if _has(text, _THREATENED):
        return EventStatus.THREATENED
    if _has(text, _CONFIRMED):
        return EventStatus.CONFIRMED
    return EventStatus.THREATENED  # unclear wording: the cautious, lower-certainty status


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def classify(
    doc: RawDocument, place_terms: list[str], area: str, state: str = ""
) -> DisruptionEvent | None:
    text = f"{doc.title} {doc.text}".lower()
    sid = f"news-{doc.id}"
    status = _status(text)

    def event(kind: EventType, affects: list[str]) -> DisruptionEvent:
        return DisruptionEvent(type=kind, status=status, affects=affects, source_id=sid)

    if _has(text, _FLIGHT) and _has(text, _SUSPEND + _STRIKE) and _has(text, _NATIONAL):
        kind = EventType.FLIGHT_SUSPENSION if _has(text, _SUSPEND) else EventType.STRIKE
        return event(kind, ["flights"])
    if _has(text, _STRIKE):
        # A strike counts if it is nationwide or in the destination's state, nothing else.
        nationwide = _has(text, ("nationwide", "national"))
        in_state = bool(state) and _has(text, (state.lower(),))
        if not (nationwide or in_state):
            return None
        if _has(text, _FUEL_UNIONS):
            return event(EventType.STRIKE, ["fuel"])
        if _has(text, _ROAD_UNIONS):
            return event(EventType.STRIKE, ["roads"])
        if nationwide:
            return event(EventType.STRIKE, ["flights", "roads"])
        return event(EventType.STRIKE, [f"state:{_slug(state)}"])
    if _has(text, _WATER) and any(t.lower() in text for t in place_terms):
        return event(EventType.HEAVY_RAIN, [f"road:{_slug(area)}"])
    return None


def build_events(
    docs: list[RawDocument],
    *,
    place_terms: list[str],
    area: str,
    today: date,
    state: str = "",
    limit: int = 12,
) -> list[DisruptionEvent]:
    """Recent news collapsed to one event per (type, affects). The newest article sets the status.

    Ended events come last, so a reader scanning the list meets live disruptions first.
    """
    floor = today - timedelta(days=RECENT_DAYS)
    fresh = sorted(
        {d.id: d for d in docs if d.published and floor <= d.published <= today}.values(),
        key=lambda d: d.published or date.min,
        reverse=True,
    )
    newest: dict[tuple[str, tuple[str, ...]], DisruptionEvent] = {}
    for d in fresh:
        if e := classify(d, place_terms, area, state):
            newest.setdefault((e.type, tuple(e.affects)), e)
    events = sorted(newest.values(), key=lambda e: e.status == EventStatus.ENDED)
    return events[:limit]
