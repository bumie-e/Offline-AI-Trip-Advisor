"""Itinerary stops from collected routes. No model involved, so it cannot invent places."""

from trip_advisor.schemas.itinerary import Stop, TravelMode

from .evidence import GenInput, route_id

VISIT_MINUTES = 120
FUEL_AFTER = 0.4  # suggest fuel once 40% of the drive is done
FACT_TOPICS = ("opening", "hours", "fee", "entry", "ticket")


def _duration_note(minutes: float) -> str:
    h, m = divmod(round(minutes), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def build_stops(inp: GenInput) -> tuple[list[Stop], list[Stop]]:
    site = inp.site
    route, routes = inp.primary, inp.routes
    facts = [f for f in inp.site_facts if any(t in f.topic.lower() for t in FACT_TOPICS)][:2]
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
    outbound = [start]
    if fuel:
        outbound.append(
            Stop(
                order=1,
                title=f"Fuel and rest: {fuel.name}",
                mode=TravelMode.ROAD,
                duration_minutes=15,
                notes=f"About {fuel.km_from_start:.0f} km into the drive. Fuel stops are sparse "
                "in the map data, so fill up when you can.",
            )
        )
    outbound.append(visit)
    back = [
        Stop(
            order=1,
            title=f"Leave {site.name}",
            mode=inp.request.mode or TravelMode.ROAD,
            duration_minutes=round(route.duration_min),
            notes="Same road in reverse. Start early enough to arrive before dark.",
            cited_ids=[rid],
        ),
        Stop(order=1, title=f"Arrive {routes.origin.name.split(',')[0]}", duration_minutes=0),
    ]
    return _number(outbound), _number(back)


def _number(stops: list[Stop]) -> list[Stop]:
    return [s.model_copy(update={"order": i}) for i, s in enumerate(stops, start=1)]
