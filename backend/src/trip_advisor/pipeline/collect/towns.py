"""Which towns a route passes through, thinned to the ones worth naming."""

from .models import RouteOption
from .models import Stop as MapStop

EDGE_KM = 10  # skip towns this close to the start (airport suburb) or to the destination
TOWN_GAP_KM = 20  # towns closer together than this count as one stop
MAX_TOWNS = 6


def route_towns(stops: list[MapStop], route: RouteOption) -> list[MapStop]:
    """Towns worth naming on the drive: one per cluster (a city if there is one), in order."""
    towns = sorted(
        (
            s
            for s in stops
            if s.route_id == route.id
            and s.kind in ("city", "town")
            and EDGE_KM <= s.km_from_start <= route.distance_km - EDGE_KM
        ),
        key=lambda s: s.km_from_start,
    )
    clusters: list[list[MapStop]] = []
    for town in towns:
        if clusters and town.km_from_start - clusters[-1][-1].km_from_start < TOWN_GAP_KM:
            clusters[-1].append(town)
        else:
            clusters.append([town])
    picked = [next((t for t in c if t.kind == "city"), c[len(c) // 2]) for c in clusters]
    if len(picked) > MAX_TOWNS:  # keep an even spread along the route
        step = (len(picked) - 1) / (MAX_TOWNS - 1)
        picked = [picked[round(i * step)] for i in range(MAX_TOWNS)]
    return picked
