"""Routes and alternatives from OSRM (OpenStreetMap data)."""

from typing import Any

from .geo import resample
from .http import Fetcher
from .models import Place, RouteOption

OSRM = "https://router.project-osrm.org/route/v1/driving"
MIN_ROAD_KM = 3.0
STORE_SPACING_KM = 1.0


def _roads(route: dict[str, Any]) -> list[str]:
    """Named roads covering at least MIN_ROAD_KM, in order of first appearance."""
    totals: dict[str, float] = {}
    for leg in route["legs"]:
        for step in leg["steps"]:
            name, ref = step.get("name", ""), step.get("ref", "")
            label = " ".join(p for p in (ref, name) if p).strip()
            if label:
                totals[label] = totals.get(label, 0.0) + step["distance"] / 1000
    return [label for label, km in totals.items() if km >= MIN_ROAD_KM]


def parse_routes(payload: dict[str, Any], *, label: str) -> list[RouteOption]:
    options = []
    for i, route in enumerate(payload.get("routes", [])):
        options.append(
            RouteOption(
                id="primary" if i == 0 else f"alt-{i}",
                kind="primary" if i == 0 else "alternative",
                label=label if i == 0 else f"{label} (alternative {i})",
                distance_km=round(route["distance"] / 1000, 1),
                duration_min=round(route["duration"] / 60),
                roads=_roads(route),
                geometry=resample(
                    [(lat, lon) for lon, lat in route["geometry"]["coordinates"]], STORE_SPACING_KM
                ),
            )
        )
    return options


def fetch_routes(
    fetcher: Fetcher, waypoints: list[Place], *, label: str, alternatives: bool = True
) -> list[RouteOption]:
    coords = ";".join(f"{p.lon},{p.lat}" for p in waypoints)
    resp = fetcher.get(
        f"{OSRM}/{coords}",
        params={
            "alternatives": "true" if alternatives else "false",
            "steps": "true",
            "overview": "full",
            "geometries": "geojson",
        },
    )
    payload = resp.json()
    if payload.get("code") != "Ok":
        raise LookupError(f"OSRM error for {label!r}: {payload.get('code')}")
    return parse_routes(payload, label=label)


def dedupe(options: list[RouteOption]) -> list[RouteOption]:
    """Drop routes that are effectively the same road (within 1% distance and same roads)."""
    kept: list[RouteOption] = []
    for opt in options:
        same = any(
            abs(opt.distance_km - k.distance_km) / max(k.distance_km, 1) < 0.01
            and opt.roads == k.roads
            for k in kept
        )
        if not same:
            kept.append(opt)
    return kept
