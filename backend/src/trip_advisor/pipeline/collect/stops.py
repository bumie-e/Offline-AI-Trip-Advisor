"""Stops along a route from OpenStreetMap (Overpass)."""

from typing import Any

import httpx

from .geo import Point, haversine_km, locate_on_route, resample
from .http import Fetcher
from .models import RouteOption, Stop

__all__ = ["fetch_stops", "haversine_km", "parse_stops"]

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
PLACE_RADIUS_M = 3000
AMENITY_RADIUS_M = 500
POINTS_PER_QUERY = 50
QUERY_SPACING_KM = 1.5
AMENITIES = "fuel|hospital|police"


def _chunks(points: list[Point], size: int) -> list[list[Point]]:
    """Overlapping chunks so each Overpass query stays small."""
    step = size - 1
    return [points[i : i + size] for i in range(0, max(len(points) - 1, 1), step)]


def _poly(points: list[Point]) -> str:
    return ",".join(f"{lat:.5f},{lon:.5f}" for lat, lon in points)


def build_queries(route: RouteOption) -> list[str]:
    queries = []
    for chunk in _chunks(resample(route.geometry, QUERY_SPACING_KM), POINTS_PER_QUERY):
        poly = _poly(chunk)
        queries.append(
            f'[out:json][timeout:90];node["place"~"^(city|town)$"]["name"]'
            f"(around:{PLACE_RADIUS_M},{poly});out tags center;"
        )
        queries.append(
            f'[out:json][timeout:90];nwr["amenity"~"^({AMENITIES})$"]["name"]'
            f"(around:{AMENITY_RADIUS_M},{poly});out tags center;"
        )
    return queries


def parse_stops(elements: list[dict[str, Any]], route: RouteOption) -> list[Stop]:
    seen: set[tuple[str, str]] = set()
    stops: list[Stop] = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        kind = tags.get("place") or tags.get("amenity")
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not (name and kind and lat is not None and lon is not None):
            continue
        if (name, kind) in seen:
            continue
        seen.add((name, kind))
        stops.append(
            Stop(
                name=name,
                kind=kind,
                lat=lat,
                lon=lon,
                km_from_start=round(locate_on_route((lat, lon), route.geometry), 1),
                route_id=route.id,
            )
        )
    return sorted(stops, key=lambda s: s.km_from_start)


def _run_query(fetcher: Fetcher, query: str, attempts: int = 2) -> list[dict[str, Any]] | None:
    """Try each Overpass server in turn. None means every server failed or timed out.

    Overpass reports query timeouts as HTTP 200 with a 'remark', so check for that too.
    """
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(attempts):
            try:
                data = fetcher.post(endpoint, data={"data": query}).json()
            except httpx.HTTPError:
                break  # Fetcher already retried this server; move to the next one
            if "runtime error" not in data.get("remark", ""):
                return list(data.get("elements", []))
            fetcher.pause(10.0 * (attempt + 1))
    return None


def fetch_stops(fetcher: Fetcher, route: RouteOption, warnings: list[str]) -> list[Stop]:
    elements: list[dict[str, Any]] = []
    for i, query in enumerate(build_queries(route)):
        found = _run_query(fetcher, query)
        if found is None:
            warnings.append(f"stops incomplete on route {route.id}: Overpass query {i} failed")
        else:
            elements.extend(found)
    return parse_stops(elements, route)
