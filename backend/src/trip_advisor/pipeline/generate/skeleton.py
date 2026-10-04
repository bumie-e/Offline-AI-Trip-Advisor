"""Itinerary stops from collected routes. No model involved, so it cannot invent places."""

from trip_advisor.pipeline.collect.models import RouteOption
from trip_advisor.pipeline.collect.routing import road_at
from trip_advisor.pipeline.collect.towns import route_towns
from trip_advisor.schemas.itinerary import Stop, TravelMode

from .evidence import GenInput, route_id
from .stop_detail import (
    Entry,
    assign_road_images,
    comment_for,
    pick_site_image,
    road_for_stop,
    to_stop_image,
)

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
        return _number(
            _decorate(inp, [Entry(visit, "visit", 0.0, [site.city, site.name])], None)
        ), []

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
    along: list[Entry] = [
        Entry(
            Stop(
                order=1,
                title=f"Pass through {t.name}",
                mode=TravelMode.ROAD,
                duration_minutes=0,
                notes=f"About {t.km_from_start:.0f} km into the {route.distance_km:.0f} km drive.",
                cited_ids=[rid],
            ),
            "town",
            t.km_from_start,
            [t.name],
        )
        for t in towns
    ]
    if fuel:
        along.append(
            Entry(
                Stop(
                    order=1,
                    title=f"Fuel and rest: {fuel.name}",
                    mode=TravelMode.ROAD,
                    duration_minutes=15,
                    notes=f"About {fuel.km_from_start:.0f} km into the drive. Fuel stops are "
                    "sparse in the map data, so fill up when you can.",
                    cited_ids=[rid],
                ),
                "fuel",
                fuel.km_from_start,
                [],
            )
        )
    entries = [
        Entry(start, "start", 0.0, []),
        *sorted(along, key=lambda e: e.km),
        Entry(visit, "visit", route.distance_km, [site.city, site.name]),
    ]
    outbound = _decorate(inp, entries, route)
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


def _decorate(inp: GenInput, entries: list[Entry], route: RouteOption | None) -> list[Stop]:
    """Give each outbound stop the road it is on, one photo and a one-line comment."""
    notes = inp.road_notes
    segments = route.segments if route else []
    main = max(segments, key=lambda s: s.to_km - s.from_km).name if segments else None
    names: dict[int, str | None] = {}
    for i, e in enumerate(entries):
        if e.kind == "start":
            names[i] = main  # the road that carries most of the drive, not the airport slip road
        elif route is not None:
            names[i] = road_at(route, e.km)
        else:
            names[i] = None
    road_photos = assign_road_images(inp.images, entries, names) if route else {}
    site_photo = pick_site_image(inp.images)
    out: list[Stop] = []
    previous: float | None = None
    for i, e in enumerate(entries):
        road = road_for_stop(
            notes, road_name=names[i], places=e.places, km=e.km if route else None,
            previous_km=previous, today=inp.today,
        )  # fmt: skip
        image = (
            to_stop_image(site_photo, shows_this_stop=True)
            if e.kind == "visit" and site_photo
            else road_photos.get(i)
        )
        comment = comment_for(e, road, route) if route else ""
        out.append(e.stop.model_copy(update={"road": road, "image": image, "comment": comment}))
        previous = e.km
    return out


def _number(stops: list[Stop]) -> list[Stop]:
    return [s.model_copy(update={"order": i}) for i, s in enumerate(stops, start=1)]
