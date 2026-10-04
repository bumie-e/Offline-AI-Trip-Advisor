"""Add per-road kilometre ranges to routes that were collected before they were recorded."""

from trip_advisor.sites import SiteConfig

from .geocode import resolve
from .http import Fetcher
from .models import SiteRoutes
from .routing import fetch_routes

DISTANCE_TOLERANCE = 0.03  # a fresh route this close in length is taken to be the same road


def backfill_segments(
    routes: SiteRoutes, site: SiteConfig, fetcher: Fetcher
) -> tuple[SiteRoutes, list[str]]:
    """Re-ask OSRM for each route and copy the road segments onto the stored one.

    Only OSRM is queried, so the stops, news and photos already collected are untouched. A
    stored route with no close match is left as it was, and the reason is returned.
    """
    problems: list[str] = []
    fresh = {r.id: r for r in fetch_routes(fetcher, [routes.origin, routes.destination], label="x")}
    for variant in site.variants:
        via = [resolve(fetcher, v) for v in variant.via]
        found = fetch_routes(
            fetcher, [routes.origin, *via, routes.destination], label=variant.label,
            alternatives=False,
        )  # fmt: skip
        if found:
            fresh[variant.id] = found[0]
    updated = []
    for route in routes.routes:
        new = fresh.get(route.id)
        close = new is not None and (
            abs(new.distance_km - route.distance_km) / max(route.distance_km, 1)
            <= DISTANCE_TOLERANCE
        )
        if new is not None and close:
            updated.append(route.model_copy(update={"segments": new.segments}))
        else:
            problems.append(f"route {route.id}: no close match among the fresh routes, left as is")
            updated.append(route)
    return routes.model_copy(update={"routes": updated}), problems
