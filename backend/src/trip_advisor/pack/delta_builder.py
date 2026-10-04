"""Build the few-KB delta: weather forecast plus recent disruption events for one site."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from trip_advisor.pipeline.collect import news, store
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import RawDocument
from trip_advisor.pipeline.context.events import LOCAL_QUERIES, NATIONAL_QUERIES, build_events
from trip_advisor.pipeline.context.weather import fetch_weather
from trip_advisor.schemas.delta import Delta
from trip_advisor.sites import SiteConfig

DELTAS_DIR = Path("data/deltas")
MAX_DELTA_BYTES = 6_000  # "a few KB": must stay small enough for a weak connection
DEFAULT_DAYS = 14


class DeltaTooLarge(RuntimeError):
    pass


def collect_event_docs(
    site: SiteConfig, fetcher: Fetcher, now: datetime, errors: list[str]
) -> list[RawDocument]:
    queries = [*NATIONAL_QUERIES, *(q.format(place=site.city) for q in LOCAL_QUERIES)]
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

    docs = collect_event_docs(site, fetcher, now, errors)
    events = build_events(
        docs,
        place_terms=[site.city, site.name, site.state],
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
