"""Build the few-KB delta: weather forecast plus recent disruption events for one site."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from trip_advisor.pipeline.collect import news, store
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import RawDocument, SiteRoutes
from trip_advisor.pipeline.collect.towns import route_towns
from trip_advisor.pipeline.context.events import LOCAL_QUERIES, NATIONAL_QUERIES, build_events
from trip_advisor.pipeline.context.weather import fetch_weather
from trip_advisor.schemas.delta import Delta
from trip_advisor.sites import SiteConfig

DELTAS_DIR = Path("data/deltas")
MAX_DELTA_BYTES = 6_000  # "a few KB": must stay small enough for a weak connection
DEFAULT_DAYS = 14


class DeltaTooLarge(RuntimeError):
    pass


PACKS_DIR = Path("data/packs")


def trip_places(
    site: SiteConfig, raw_dir: Path = store.RAW_DIR, packs_dir: Path = PACKS_DIR
) -> list[str]:
    """Places where a flood or heavy rain would affect this trip: the destination city and site,
    then the towns the primary route passes through. Not the whole state."""
    places = [site.city, site.name]
    # Raw collection output stays on the machine that collected it. The pack's slim copy travels
    # with the deploy, so a scheduled job on a fresh checkout can still find the route towns.
    routes_file = store.site_dir(site.id, raw_dir) / "routes.json"
    if not routes_file.exists():
        routes_file = packs_dir / site.id / "routes.json"
    if routes_file.exists():
        routes = SiteRoutes.model_validate_json(routes_file.read_text())
        primary = next((r for r in routes.routes if r.id == "primary"), None)
        if primary:
            places += [t.name for t in route_towns(routes.stops, primary)]
    return list(dict.fromkeys(places))


def collect_event_docs(
    site: SiteConfig,
    fetcher: Fetcher,
    now: datetime,
    errors: list[str],
    places: list[str] | None = None,
) -> list[RawDocument]:
    places = places if places is not None else [site.city]
    queries = [
        *NATIONAL_QUERIES,
        *(
            q.format(place=p)
            for p in dict.fromkeys([site.city, *places[2:]])
            for q in LOCAL_QUERIES
        ),
    ]
    docs: list[RawDocument] = []
    for q in queries:
        try:
            docs += news.fetch_google_news(
                fetcher, site_id=site.id, corridor="disruptions", query=q, now=now
            )
        except Exception as exc:  # noqa: BLE001 - one failing query must not stop the others
            errors.append(f"news failed for {q!r}: {exc}")
    return docs


def build_delta(
    site: SiteConfig,
    fetcher: Fetcher,
    *,
    start: date | None = None,
    end: date | None = None,
    now: datetime | None = None,
) -> tuple[Delta, list[str]]:
    """Returns the delta and any source errors. A failed source leaves a gap, not a crash."""
    now = now or datetime.now(UTC)
    today = now.date()
    start, end = start or today, end or today + timedelta(days=DEFAULT_DAYS)
    errors: list[str] = []

    weather = []
    if site.destination.pinned:
        assert site.destination.lat is not None and site.destination.lon is not None
        try:
            weather = fetch_weather(
                fetcher,
                lat=site.destination.lat,
                lon=site.destination.lon,
                area=site.city,
                start=start,
                end=end,
                today=today,
            )
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"weather failed: {exc}")
    else:
        errors.append("weather skipped: destination coordinates are not pinned")

    places = trip_places(site)
    docs = collect_event_docs(site, fetcher, now, errors, places)
    events = build_events(
        docs,
        place_terms=places,
        area=site.city,
        today=today,
        state=site.state,
    )
    delta = Delta(generated_at=now, weather=weather, events=events)
    size = len(delta.model_dump_json().encode())
    if size > MAX_DELTA_BYTES:
        raise DeltaTooLarge(f"delta is {size} bytes, limit {MAX_DELTA_BYTES}")
    return delta, errors


def write_delta(delta: Delta, site_id: str, out_dir: Path = DELTAS_DIR) -> Path:
    return store.save(delta, out_dir / f"{site_id}.json")
