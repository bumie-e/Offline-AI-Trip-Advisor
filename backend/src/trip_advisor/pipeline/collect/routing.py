"""Routes and alternatives from OSRM (OpenStreetMap data)."""

from typing import Any

from .geo import resample
from .http import Fetcher
from .models import Place, RoadSegment, RouteOption

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


MIN_SEGMENT_KM = 1.5  # shorter bits (slip roads, junctions) are folded into the road before them


def _segments(route: dict[str, Any]) -> list[RoadSegment]:
    """Consecutive stretches of one named road, with kilometre ranges along the route."""
    runs: list[list[Any]] = []  # [label, from_km, to_km]
    km = 0.0
    for leg in route["legs"]:
        for step in leg["steps"]:
            name, ref = step.get("name", ""), step.get("ref", "")
            label = " ".join(p for p in (ref, name) if p).strip()
            end = km + step["distance"] / 1000
            if not label and runs:
                runs[-1][2] = end  # an unnamed bit belongs to the road it sits on
            elif label and runs and runs[-1][0] == label:
                runs[-1][2] = end
            elif label:
                runs.append([label, km, end])
            km = end
    merged: list[list[Any]] = []
    for run in runs:
        if merged and (run[2] - run[1] < MIN_SEGMENT_KM or merged[-1][0] == run[0]):
            merged[-1][2] = run[2]
        else:
            merged.append(run)
    return [RoadSegment(name=n, from_km=round(a, 1), to_km=round(b, 1)) for n, a, b in merged]


def road_at(route: RouteOption, km: float) -> str | None:
    """The named road at this distance along the route, or None when segments are not known."""
    for seg in route.segments:
        if seg.from_km <= km <= seg.to_km:
            return seg.name
    if route.segments:  # past the last or before the first: the nearest one
        return min(
            route.segments, key=lambda sg: min(abs(sg.from_km - km), abs(sg.to_km - km))
        ).name
    return None


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
                segments=_segments(route),
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
