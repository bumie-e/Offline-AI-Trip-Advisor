"""Collect routes, stops, guide text and recent road news for one site."""

import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from trip_advisor.schemas.common import Strict
from trip_advisor.sites import SiteConfig

from . import news, store, wikivoyage
from .brightdata import BrightData, BrightDataError, serp_docs
from .coverage import SiteCoverage, assess
from .enrich import enrich
from .freshness import cutoff, select_latest
from .geocode import resolve
from .http import Fetcher
from .models import CorridorEvidence, RawDocument, RouteOption, SiteRoutes
from .routing import dedupe, fetch_routes
from .stops import fetch_stops

# A failing source is recorded as a gap and must not stop the others.
COLLECT_ERRORS = (httpx.HTTPError, LookupError, ValueError, ET.ParseError, BrightDataError)


def collect_routes(
    site: SiteConfig, fetcher: Fetcher, now: datetime, warnings: list[str]
) -> SiteRoutes:
    origin = resolve(fetcher, site.origin)
    dest = resolve(fetcher, site.destination)
    routes = fetch_routes(fetcher, [origin, dest], label=f"{origin.name} to {site.name}")
    for variant in site.variants:
        via = [resolve(fetcher, v) for v in variant.via]
        found = fetch_routes(fetcher, [origin, *via, dest], label=variant.label, alternatives=False)
        if found:
            routes.append(found[0].model_copy(update={"id": variant.id, "kind": "variant"}))
    routes = _unique_ids(dedupe(routes))
    stops = [stop for r in routes for stop in fetch_stops(fetcher, r, warnings)]
    return SiteRoutes(
        site_id=site.id,
        origin=origin,
        destination=dest,
        routes=routes,
        stops=stops,
        collected_at=now,
    )


def _unique_ids(routes: list[RouteOption]) -> list[RouteOption]:
    seen: set[str] = set()
    for r in routes:
        assert r.id not in seen, r.id
        seen.add(r.id)
    return routes


def collect_evidence(
    site: SiteConfig,
    fetcher: Fetcher,
    now: datetime,
    errors: list[str],
    bd: BrightData | None = None,
) -> list[CorridorEvidence]:
    after = cutoff(now.date())
    evidence = []
    for corridor in site.corridors:
        docs: list[RawDocument] = []
        sid, cname = site.id, corridor.name
        for query in corridor.queries:
            try:
                docs.extend(
                    news.fetch_google_news(
                        fetcher, site_id=sid, corridor=cname, query=query, now=now
                    )
                )
            except COLLECT_ERRORS as exc:
                errors.append(f"google_news failed for {query!r}: {exc}")
            try:
                docs.extend(
                    news.fetch_fmino(
                        fetcher, site_id=sid, corridor=cname, query=query, now=now, after=after
                    )
                )
            except COLLECT_ERRORS as exc:
                errors.append(f"fmino failed for {query!r}: {exc}")
        if bd and bd.can_search:
            # Plain queries, plus one query restricted to the official FRSC site.
            for q in [*corridor.queries, f"{corridor.queries[0]} site:frsc.gov.ng"]:
                try:
                    items = bd.serp_news(q)
                    docs.extend(serp_docs(items, site_id=sid, corridor=cname, query=q, now=now))
                except COLLECT_ERRORS as exc:
                    errors.append(f"bright data serp failed for {q!r}: {exc}")
        if bd:
            docs = enrich(docs, bd, now.date(), errors)
        evidence.append(select_latest(docs, corridor, now.date()))
    return evidence


# Each group needs at least one reachable member.
HOST_GROUPS: dict[str, tuple[str, ...]] = {
    "geocoding": ("https://nominatim.openstreetmap.org/",),
    "routing": ("https://router.project-osrm.org/",),
    "stops": ("https://overpass-api.de/", "https://overpass.private.coffee/"),
    "news": ("https://news.google.com/",),
    "gov notices": ("https://fmino.gov.ng/",),
    "guides": ("https://en.wikivoyage.org/",),
}


def _reachable(fetcher: Fetcher, url: str) -> bool:
    try:
        fetcher.client.head(url, timeout=15)
    except httpx.TransportError:
        return False
    return True  # any HTTP response means the host is up, even a refusal


def preflight(fetcher: Fetcher, *, geocoding: bool = True) -> None:
    """Fail fast if a source is unreachable, rather than writing a run full of failures."""
    down = [
        group
        for group, urls in HOST_GROUPS.items()
        if (geocoding or group != "geocoding") and not any(_reachable(fetcher, u) for u in urls)
    ]
    if down:
        raise ConnectionError("Unreachable: " + ", ".join(down))


class CollectResult(Strict):
    coverage: SiteCoverage
    routes: SiteRoutes | None


def collect_site(
    site: SiteConfig,
    fetcher: Fetcher,
    *,
    today: date | None = None,
    out_dir: Path = store.RAW_DIR,
    bd: BrightData | None = None,
) -> CollectResult:
    now = datetime.now(UTC)
    today = today or now.date()
    errors: list[str] = []
    base = store.site_dir(site.id, out_dir)

    routes: SiteRoutes | None = None
    try:
        routes = collect_routes(site, fetcher, now, errors)
        store.save(routes, base / "routes.json")
    except COLLECT_ERRORS as exc:
        errors.append(f"route collection failed: {exc}")

    guides: list[RawDocument] = []
    for title in site.wikivoyage_pages:
        try:
            doc = wikivoyage.fetch_page(fetcher, site.id, title)
        except COLLECT_ERRORS as exc:
            errors.append(f"wikivoyage failed for {title!r}: {exc}")
            continue
        if doc:
            guides.append(doc)
            store.save(doc, base / "guides" / f"{doc.id}.json")

    evidence = collect_evidence(site, fetcher, now, errors, bd)
    for ev in evidence:
        for doc in [ev.selected, *ev.others]:
            if doc:
                store.save(doc, base / "evidence" / f"{doc.id}.json")
        store.save(ev, base / "selected" / f"{_slug(ev.corridor)}.json")

    primary = {c.name for c in site.corridors if c.primary}
    coverage = assess(site.id, routes, guides, evidence, primary, today, errors)
    store.save(coverage, base / "coverage.json")
    return CollectResult(coverage=coverage, routes=routes)


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")


def rescore_site(
    site: SiteConfig, *, today: date | None = None, out_dir: Path = store.RAW_DIR
) -> CollectResult:
    """Re-run selection and coverage on saved data. No network, no Bright Data cost."""
    today = today or datetime.now(UTC).date()
    base = store.site_dir(site.id, out_dir)
    routes_file = base / "routes.json"
    routes = (
        SiteRoutes.model_validate_json(routes_file.read_text()) if routes_file.exists() else None
    )
    docs = [
        RawDocument.model_validate_json(f.read_text()) for f in (base / "evidence").glob("*.json")
    ]
    guides = [
        RawDocument.model_validate_json(f.read_text()) for f in (base / "guides").glob("*.json")
    ]
    evidence = [
        select_latest([d for d in docs if d.corridor == c.name], c, today) for c in site.corridors
    ]
    for ev in evidence:
        store.save(ev, base / "selected" / f"{_slug(ev.corridor)}.json")
    primary = {c.name for c in site.corridors if c.primary}
    # Carry over the original run's failures, so a rescore never looks cleaner than the run was.
    previous = base / "coverage.json"
    run_errors = (
        SiteCoverage.model_validate_json(previous.read_text()).run_errors
        if previous.exists()
        else []
    )
    coverage = assess(site.id, routes, guides, evidence, primary, today, run_errors)
    store.save(coverage, previous)
    return CollectResult(coverage=coverage, routes=routes)
