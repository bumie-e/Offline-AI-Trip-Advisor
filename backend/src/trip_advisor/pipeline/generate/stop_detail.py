"""What the stop screen shows: the road at each stop, one photo, and a one-line comment.

Everything here is chosen from collected data by fixed rules. Nothing is written by a model, so
nothing can be invented; the model only adds advice afterwards, and must cite evidence for it.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from trip_advisor.pipeline.collect.freshness import cutoff
from trip_advisor.pipeline.collect.models import RouteOption
from trip_advisor.schemas.common import Confidence
from trip_advisor.schemas.itinerary import Stop, StopImage, StopRoad
from trip_advisor.schemas.pack import ImageRecord, RoadNote

NO_REPORT = "No road report from the last 3 months for this stretch."
MAX_EVIDENCE = 3
COMMENT_CHARS = 130
_RANK = {Confidence.HIGH: 2, Confidence.MEDIUM: 1, Confidence.LOW: 0}
# Words that say what kind of place a name is, not which place. They must not make unrelated
# things match ("road" is in nearly every road name).
_GENERIC = {
    "road", "roads", "expressway", "highway", "street", "avenue", "way", "state", "federal",
    "nigeria", "junction", "along", "near", "off", "the", "and", "city", "town", "view",
}  # fmt: skip


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3} - _GENERIC


def _word_in(text: str, name: str) -> bool:
    return bool(re.search(rf"\b{re.escape(name.lower())}\b", text.lower()))


Scope = Literal["here", "road", "corridor"]
_SCOPE_RANK = {"here": 2, "road": 1, "corridor": 0}


def _named_at(text: str, place: str) -> bool:
    """The place is named as a place. "Lagos-Ore-Benin" does not count as naming Ore, because
    there the place is glued into the name of a road."""
    pattern = rf"(?<![\w\-–/]){re.escape(place.lower())}(?!\w)(?![-–/]\w)"
    return bool(re.search(pattern, text.lower()))


def note_scope(note: RoadNote, road_name: str | None, places: list[str]) -> Scope | None:
    """How a road report applies to a stop, or None when it does not.

    Names differ between sources (the news says Lagos-Ore-Benin, the map says Benin-Sagamu), so a
    town in the report's road name still links it, but only as "corridor": the report is about the
    whole road, not necessarily this spot. A road match needs the report's road to sit inside this
    road's name, or share two place words with it.
    """
    if any(_named_at(note.summary, p) for p in places if p):
        return "here"
    if road_name:
        mine, theirs = tokens(note.route), tokens(road_name)
        if mine and (mine <= theirs or len(mine & theirs) >= 2):
            return "road"
    text = f"{note.route} {note.summary}"
    if any(_word_in(text, p) for p in places if p):
        return "corridor"
    return None


def note_applies(note: RoadNote, road_name: str | None, places: list[str]) -> bool:
    return note_scope(note, road_name, places) is not None


def road_for_stop(
    notes: list[RoadNote],
    *,
    road_name: str | None,
    places: list[str],
    km: float | None,
    previous_km: float | None,
    today: date,
) -> StopRoad:
    """The nature of the road at a stop, from the best report of the last 3 months.

    Best means: the most specific to this stop, then the newest, then the most confident.
    """
    floor = cutoff(today)
    found: list[tuple[Scope, RoadNote]] = []
    for n in notes:
        if not (n.source.published and floor <= n.source.published <= today):
            continue
        if scope := note_scope(n, road_name, places):
            found.append((scope, n))
    found.sort(
        key=lambda f: (_SCOPE_RANK[f[0]], f[1].source.published, _RANK[f[1].confidence]),
        reverse=True,
    )
    since = None if km is None or previous_km is None else round(km - previous_km, 1)
    if not found:
        return StopRoad(
            name=road_name, km_from_start=km, km_since_previous_stop=since, condition=NO_REPORT
        )
    scope, best = found[0]
    assert best.source.published is not None
    return StopRoad(
        name=road_name,
        km_from_start=km,
        km_since_previous_stop=since,
        condition=best.summary,
        has_recent_report=True,
        scope=scope,
        confidence=best.confidence,
        report_age_days=(today - best.source.published).days,
        evidence_ids=[n.id for _, n in found[:MAX_EVIDENCE]],
    )


def to_stop_image(rec: ImageRecord, *, shows_this_stop: bool) -> StopImage:
    return StopImage(
        id=rec.id,
        path=rec.path,
        caption=rec.summary,
        credit=rec.credit,
        license=rec.license,
        width=rec.width,
        height=rec.height,
        shows_this_stop=shows_this_stop,
    )


def pick_site_image(images: list[ImageRecord]) -> ImageRecord | None:
    """The photo of the heritage site itself: the most certain one, then the first collected."""
    site = [i for i in images if i.kind == "site"]
    return max(site, key=lambda i: _RANK[i.confidence], default=None) if site else None


@dataclass
class Entry:
    stop: Stop
    kind: str  # start, town, fuel, visit
    km: float
    places: list[str]  # names the stop is known by, for matching reports and photos


def assign_road_images(
    images: list[ImageRecord], entries: list[Entry], road_names: dict[int, str | None]
) -> dict[int, StopImage]:
    """One road photo per stop, never the same photo twice.

    A photo goes first to the stop whose town its caption names, or whose road it names with at
    least two words. Stops left over get an
    unused photo marked as an example of a road in the area, not of that exact spot. Road photos
    are searched for near the destination, so examples go to the stops closest to it first. Fewer
    photos than stops simply leaves some stops without one.
    """
    photos = [i for i in images if i.kind == "road"]
    road_stops = [i for i, e in enumerate(entries) if e.kind != "visit"]
    scored = []
    for p_idx, photo in enumerate(photos):
        cap = tokens(photo.summary)
        for i in road_stops:
            town_hits = len(cap & {t for place in entries[i].places for t in tokens(place)})
            road_hits = len(cap & tokens(road_names.get(i) or ""))
            # One shared word is not enough: "Abeokuta-Ijebu expressway" is not the
            # Lagos-Abeokuta expressway. Naming the stop's town, or two words of its road, is.
            if town_hits >= 1 or road_hits >= 2:
                scored.append((-(town_hits * 3 + road_hits), i, p_idx))
    chosen: dict[int, StopImage] = {}
    used: set[int] = set()
    for _, i, p_idx in sorted(scored):
        if i not in chosen and p_idx not in used:
            chosen[i] = to_stop_image(photos[p_idx], shows_this_stop=True)
            used.add(p_idx)
    spare = (photos[p] for p in range(len(photos)) if p not in used)
    for i in reversed(road_stops):  # nearest the destination first
        if i not in chosen and (example := next(spare, None)):
            chosen[i] = to_stop_image(example, shows_this_stop=False)
    return chosen


def short(text: str, limit: int = COMMENT_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def comment_for(entry: Entry, road: StopRoad, route: RouteOption) -> str:
    """The line under the stop's name in the list."""
    if entry.kind == "start":
        mins = round(route.duration_min)
        hours = f"{mins // 60} h {mins % 60:02d} min" if mins >= 60 else f"{mins} min"
        return f"{route.distance_km:.0f} km, about {hours} without traffic."
    if entry.kind == "visit":
        return "Your destination."
    where = f"{entry.km:.0f} km in" + (f" on {road.name}" if road.name else "")
    if not road.has_recent_report:
        return short(f"{where} · no recent road report")
    sure = f" ({road.confidence} confidence)" if road.confidence else ""
    return short(f"{where} · road report {road.report_age_days} days old{sure}")
