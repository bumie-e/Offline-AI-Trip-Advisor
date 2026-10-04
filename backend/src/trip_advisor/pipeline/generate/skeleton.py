"""Itinerary stops from collected routes. No model involved, so it cannot invent places."""

from trip_advisor.pipeline.collect.towns import route_towns
from trip_advisor.schemas.itinerary import Stop, TravelMode

from .evidence import GenInput, route_id

VISIT_MINUTES = 120
FUEL_AFTER = 0.4  # suggest fuel once 40% of the drive is done
FACT_TOPICS = ("opening", "hours", "fee", "entry", "ticket")


def _duration_note(minutes: float) -> str:
    h, m = divmod(round(minutes), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _about_site(summary: str, site_name: str) -> bool:
    """A guide page about a town also lists nearby places (galleries, hotels). Their hours are
    not the site's hours, so only a fact that names the site may become a visit note."""
    return site_name.lower() in summary.lower()


def build_stops(inp: GenInput) -> tuple[list[Stop], list[Stop]]:
    site = inp.site
    route, routes = inp.primary, inp.routes
    facts = [
        f
        for f in inp.site_facts
        if any(t in f.topic.lower() for t in FACT_TOPICS) and _about_site(f.summary, site.name)
    ][:2]
    visit = Stop(
        order=1,
        title=f"Visit {site.name}",
        mode=TravelMode.WALK,
        duration_minutes=VISIT_MINUTES,
        notes=" ".join(f.summary for f in facts),
        cited_ids=[f.id for f in facts],
    )
    if route is None or routes is None:
        inp.notes.append("No collected route, so travel stops are missing.")
        return _number([visit]), []

    roads = ", ".join(route.roads[:4]) or "unnamed roads"
    drive = (
        f"About {route.distance_km:.0f} km, roughly {_duration_note(route.duration_min)} "
        f"without traffic, via {roads}. Allow extra time for traffic."
    )
    rid = route_id(site.id, route)
    start = Stop(
        order=1,
        title=f"Leave {routes.origin.name.split(',')[0]}",
        mode=inp.request.mode or TravelMode.ROAD,
        duration_minutes=round(route.duration_min),
        notes=drive,
        cited_ids=[rid],
    )
    fuel = next(
        (
            s
            for s in sorted(routes.stops, key=lambda s: s.km_from_start)
            if s.route_id == route.id and s.kind == "fuel"
            and s.km_from_start >= FUEL_AFTER * route.distance_km
        ),
        None,
    )  # fmt: skip
    towns = route_towns(routes.stops, route)
    along: list[tuple[float, Stop]] = [
        (
            t.km_from_start,
            Stop(
                order=1,
                title=f"Pass through {t.name}",
                mode=TravelMode.ROAD,
                duration_minutes=0,
                notes=f"About {t.km_from_start:.0f} km into the {route.distance_km:.0f} km drive.",
                cited_ids=[rid],
            ),
        )
        for t in towns
    ]
    if fuel:
        along.append(
            (
                fuel.km_from_start,
                Stop(
                    order=1,
                    title=f"Fuel and rest: {fuel.name}",
                    mode=TravelMode.ROAD,
                    duration_minutes=15,
                    notes=f"About {fuel.km_from_start:.0f} km into the drive. Fuel stops are "
                    "sparse in the map data, so fill up when you can.",
                    cited_ids=[rid],
                ),
            )
        )
    outbound = [start, *(s for _, s in sorted(along, key=lambda pair: pair[0])), visit]
    back_via = f" Via {', '.join(t.name for t in reversed(towns))}." if towns else ""
    back = [
        Stop(
            order=1,
            title=f"Leave {site.name}",
            mode=inp.request.mode or TravelMode.ROAD,
            duration_minutes=round(route.duration_min),
            notes="Same road in reverse." + back_via + " Start early enough to arrive before dark.",
            cited_ids=[rid],
        ),
        Stop(order=1, title=f"Arrive {routes.origin.name.split(',')[0]}", duration_minutes=0),
    ]
    return _number(outbound), _number(back)


def _number(stops: list[Stop]) -> list[Stop]:
    return [s.model_copy(update={"order": i}) for i, s in enumerate(stops, start=1)]
