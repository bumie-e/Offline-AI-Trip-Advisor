"""Deterministic checks that set a floor under the verdict.

This is the "optional rule check beside the model" from the README, decided as: yes. The model
writes the advice, but it may not be more relaxed than these rules, because a model that
under-warns on heavy rain over a rain-sensitive road is the failure that matters most.
"""

from dataclasses import dataclass

from trip_advisor.schemas.common import Confidence, Sensitivity
from trip_advisor.schemas.delta import DisruptionEvent, EventStatus, EventType
from trip_advisor.schemas.itinerary import Advice, Severity, TravelMode, Verdict

from .evidence import GenInput, weather_id

HEAVY_RAIN = 0.7
LIKELY_RAIN = 0.5

SEVERITY_ORDER = [Severity.NONE, Severity.ELEVATED, Severity.HIGH]
VERDICT_ORDER = [Verdict.GO, Verdict.GO_WITH_CHANGES, Verdict.NOT_ADVISED]
VERDICT_FOR = {
    Severity.NONE: Verdict.GO,
    Severity.ELEVATED: Verdict.GO_WITH_CHANGES,
    Severity.HIGH: Verdict.NOT_ADVISED,
}
_SENS = {Sensitivity.LOW: 0, Sensitivity.MEDIUM: 1, Sensitivity.HIGH: 2}


def max_severity(items: list[Advice]) -> Severity:
    return max((a.severity for a in items), key=SEVERITY_ORDER.index, default=Severity.NONE)


def more_cautious(a: Verdict, b: Verdict) -> Verdict:
    return max(a, b, key=VERDICT_ORDER.index)


@dataclass
class Assessment:
    advice: list[Advice]
    verdict: Verdict


def _alternatives(inp: GenInput, *, routes: bool) -> list[str]:
    alts = ["leave earlier in the day", "choose different dates"]
    if routes and inp.routes:
        alts += [f"alternative route: {r.label}" for r in inp.routes.routes if r.kind != "primary"][
            :2
        ]
    return alts


def _rain(inp: GenInput) -> list[Advice]:
    days = set(inp.trip_days)
    forecast = [w for w in inp.delta.weather if w.date in days]
    solid = [n for n in inp.road_notes if n.confidence != Confidence.LOW]
    notes = solid or inp.road_notes
    sens = max((_SENS[n.rain_sensitivity] for n in notes), default=0)
    heavy = [w for w in forecast if w.rain_probability >= HEAVY_RAIN]
    likely = [w for w in forecast if LIKELY_RAIN <= w.rain_probability < HEAVY_RAIN]
    sensitive = [n for n in notes if _SENS[n.rain_sensitivity] == sens and sens > 0]

    if heavy and sens == 2:
        severity, picked = Severity.HIGH, heavy
    elif heavy:
        severity, picked = Severity.ELEVATED, heavy
    elif likely and sens == 2:
        severity, picked = Severity.ELEVATED, likely
    else:
        return []
    if not solid and severity == Severity.HIGH:
        severity = Severity.ELEVATED  # weak evidence can raise a flag, never force "not advised"
    when = ", ".join(f"{w.date:%d %b} ({w.rain_probability:.0%})" for w in picked)
    why = (
        (
            " Stored road reports describe this route as sensitive to rain."
            if solid
            else " A low-confidence report suggests this route may be sensitive to rain."
        )
        if sensitive
        else " Road conditions in wet weather can be difficult in this region."
    )
    return [
        Advice(
            changed=True,
            severity=severity,
            advice=f"Rain is forecast during your trip: {when}.{why} "
            "Reports suggest allowing extra time or choosing other dates.",
            alternatives=_alternatives(inp, routes=True),
            cited_ids=[weather_id(w.date) for w in picked] + [n.id for n in sensitive],
        )
    ]


def _event_relevant(e: DisruptionEvent, inp: GenInput) -> bool:
    if e.status == EventStatus.ENDED:
        return False
    if "flights" in e.affects and not (
        inp.request.arrival_airport or inp.request.mode == TravelMode.FLIGHT
    ):
        return False
    days = inp.trip_days
    if e.start and e.start > days[-1]:
        return False
    return not (e.end and e.end < days[0])


def _plain(affects: list[str]) -> str:
    """'road:abeokuta' -> 'roads around Abeokuta', 'state:ogun' -> 'Ogun State'."""
    out = []
    for a in affects:
        kind, _, name = a.partition(":")
        name = name.replace("-", " ").title()
        out.append({"road": f"roads around {name}", "state": f"{name} State"}.get(kind, a))
    return ", ".join(out)


def _events(inp: GenInput) -> list[Advice]:
    out = []
    for e in inp.delta.events:
        if not _event_relevant(e, inp):
            continue
        what = {
            EventType.STRIKE: "A strike",
            EventType.FLIGHT_SUSPENSION: "Flight suspensions",
            EventType.HEAVY_RAIN: "Heavy rain or flooding",
            EventType.ROAD_CLOSURE: "A road closure",
            EventType.OTHER: "A disruption",
        }[e.type]
        state = "has been reported" if e.status == EventStatus.CONFIRMED else "has been threatened"
        timing = "" if e.start or e.end else " Timing is not known."
        out.append(
            Advice(
                changed=True,
                severity=Severity.ELEVATED,
                advice=f"{what} {state}, which could affect {_plain(e.affects)}.{timing} "
                "Check the latest news close to departure and keep plans flexible.",
                alternatives=["keep travel dates flexible"],
                cited_ids=[e.source_id],
            )
        )
    return out


def _thin_evidence(inp: GenInput) -> list[Advice]:
    solid = [n for n in inp.road_notes if n.confidence != Confidence.LOW]
    if solid:
        return []
    return [
        Advice(
            changed=False,
            severity=Severity.NONE,
            advice="Recent road reports for this route are thin or more than three months old, "
            "so confirm conditions locally or with a guide before leaving.",
            cited_ids=[n.id for n in inp.road_notes],
        )
    ]


def _forecast_gap(inp: GenInput) -> list[Advice]:
    days = set(inp.trip_days)
    if any(w.date in days for w in inp.delta.weather):
        return []
    return [
        Advice(
            changed=False,
            severity=Severity.NONE,
            advice="No weather forecast covers your travel dates yet, so rain has not been "
            "checked. Look again within about two weeks of departure.",
            cited_ids=[],
        )
    ]


def assess(inp: GenInput) -> Assessment:
    advice = [*_rain(inp), *_events(inp), *_thin_evidence(inp), *_forecast_gap(inp)]
    advice.sort(key=lambda a: SEVERITY_ORDER.index(a.severity), reverse=True)
    return Assessment(advice=advice, verdict=VERDICT_FOR[max_severity(advice)])
