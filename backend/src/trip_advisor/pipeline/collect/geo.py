from itertools import pairwise
from math import asin, cos, radians, sin, sqrt

Point = tuple[float, float]  # (lat, lon)


def haversine_km(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def resample(points: list[Point], spacing_km: float) -> list[Point]:
    """Keep points at least `spacing_km` apart, always keeping the first and last."""
    if len(points) <= 2:
        return points
    kept = [points[0]]
    for p in points[1:-1]:
        if haversine_km(kept[-1], p) >= spacing_km:
            kept.append(p)
    kept.append(points[-1])
    return kept


def locate_on_route(point: Point, geometry: list[Point]) -> float:
    """Kilometres from route start to the point's projection onto the route line."""
    best_km, best_dist, travelled = 0.0, float("inf"), 0.0
    for a, b in pairwise(geometry):
        seg = haversine_km(a, b)
        # Project in a local flat frame (fine at segment scale).
        k = cos(radians(a[0]))
        ax, ay, bx, by = a[1] * k, a[0], b[1] * k, b[0]
        px, py = point[1] * k, point[0]
        dx, dy = bx - ax, by - ay
        t = (
            0.0
            if dx == dy == 0
            else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        )
        proj = (ay + t * dy, (ax + t * dx) / k)
        dist = haversine_km(point, proj)
        if dist < best_dist:
            best_dist, best_km = dist, travelled + t * seg
        travelled += seg
    return best_km
