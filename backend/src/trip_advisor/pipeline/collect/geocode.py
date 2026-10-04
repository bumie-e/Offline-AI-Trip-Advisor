from trip_advisor.sites import Endpoint

from .http import Fetcher
from .models import Place

NOMINATIM = "https://nominatim.openstreetmap.org/search"


def geocode(fetcher: Fetcher, query: str) -> Place:
    resp = fetcher.get(
        NOMINATIM,
        params={
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": "ng",  # sites are in Nigeria; never match abroad
            "accept-language": "en",  # clients send none, so results come back in local script
        },
    )
    hits = resp.json()
    if not hits:
        raise LookupError(f"No geocoding result for {query!r}")
    hit = hits[0]
    return Place(
        name=query.split(",")[0],
        lat=float(hit["lat"]),
        lon=float(hit["lon"]),
        matched=f"{hit.get('type', '')}: {hit.get('display_name', '')}",
    )


def resolve(fetcher: Fetcher, point: Endpoint) -> Place:
    """Use pinned coordinates when present, otherwise geocode the query."""
    if point.lat is not None and point.lon is not None:
        return Place(name=point.query.split(",")[0], lat=point.lat, lon=point.lon, matched="pinned")
    return geocode(fetcher, point.query)
