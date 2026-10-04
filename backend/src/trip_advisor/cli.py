from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from trip_advisor.pipeline.collect.brightdata import BrightData
    from trip_advisor.pipeline.collect.http import Fetcher
    from trip_advisor.pipeline.collect.run import CollectResult

app = typer.Typer(help="Trip advisor backend commands.")


def _bright_data(fetcher: "Fetcher") -> "BrightData | None":
    from trip_advisor.config import settings
    from trip_advisor.pipeline.collect.brightdata import BrightData

    bd = BrightData(
        fetcher,
        settings.bright_data_api_key,
        unlocker_zone=settings.bright_data_unlocker_zone,
        serp_zone=settings.bright_data_serp_zone,
        max_requests=settings.bright_data_max_requests,
    )
    if not (bd.can_search or bd.can_fetch):
        typer.echo("Bright Data: no zones configured, skipping (set the zone names in .env).")
        return None
    typer.echo(
        f"Bright Data: serp={bd.can_search} unlocker={bd.can_fetch}, budget={bd.max_requests}"
    )
    return bd


@app.command()
def collect(site: str = typer.Argument("all", help="Site id, or 'all'")) -> None:
    """Collect routes, stops, guide text and recent road news, then report coverage."""
    from trip_advisor.pipeline.collect.http import Fetcher
    from trip_advisor.pipeline.collect.run import collect_site, preflight
    from trip_advisor.sites import list_sites, load_site, needs_geocoding

    fetcher = Fetcher()
    bd = _bright_data(fetcher)
    configs = [load_site(i) for i in (list_sites() if site == "all" else [site])]
    try:
        preflight(fetcher, geocoding=any(needs_geocoding(c) for c in configs))
    except ConnectionError as exc:
        typer.echo(f"Aborting, nothing written. {exc}", err=True)
        raise typer.Exit(1) from exc
    for config in configs:
        _report(config.id, collect_site(config, fetcher, bd=bd))
        if bd:
            typer.echo(f"  bright data requests used so far: {bd.used}/{bd.max_requests}")


@app.command()
def rescore(site: str = typer.Argument("all", help="Site id, or 'all'")) -> None:
    """Re-run selection and coverage on saved data (no network, no Bright Data cost)."""
    from trip_advisor.pipeline.collect.run import rescore_site
    from trip_advisor.sites import list_sites, load_site

    for site_id in list_sites() if site == "all" else [site]:
        _report(site_id, rescore_site(load_site(site_id)))


def _report(site_id: str, result: "CollectResult") -> None:
    cov = result.coverage
    typer.echo(f"\n== {site_id}: {'SUFFICIENT' if cov.sufficient else 'INSUFFICIENT'}")
    typer.echo(
        f"routes={cov.routes} alternatives={cov.alternatives} "
        f"towns={cov.towns_on_primary} fuel={cov.fuel_on_primary} guides={cov.guide_pages}"
    )
    if result.routes:
        for r in result.routes.routes:
            roads = ", ".join(r.roads) or "?"
            typer.echo(f"  {r.id}: {r.distance_km} km, ~{r.duration_min:.0f} min via {roads}")
    for c in cov.corridors:
        age = f"{c.age_days}d old" if c.age_days is not None else "none"
        typer.echo(f"  {c.corridor}: {c.fresh_items} fresh, newest report {c.newest} ({age})")
        if c.newest_title:
            typer.echo(f"    -> {c.newest_title}")
    for gap in cov.gaps:
        typer.echo(f"  gap: {gap}")


@app.command()
def structure(site: str = typer.Argument("all", help="Site id, or 'all'")) -> None:
    """Extract pack records from collected documents with the LLM (needs LLM_API_KEY)."""
    from trip_advisor.config import settings
    from trip_advisor.pipeline.structure.extractor import AnthropicExtractor
    from trip_advisor.pipeline.structure.run import structure_site, summary_line
    from trip_advisor.sites import list_sites, load_site

    if not settings.llm_api_key:
        typer.echo("LLM_API_KEY is not set in .env.", err=True)
        raise typer.Exit(1)
    extractor = AnthropicExtractor(settings.llm_api_key, settings.llm_model)
    for site_id in list_sites() if site == "all" else [site]:
        result = structure_site(load_site(site_id), extractor)
        typer.echo(f"{site_id}: {summary_line(result)}")
        typer.echo(f"  hand-check sample: data/structured/{site_id}/review.md")


@app.command()
def delta(
    site: str = typer.Argument("all", help="Site id, or 'all'"),
    days: int = typer.Option(14, help="Forecast window starting today (the API allows 16)"),
) -> None:
    """Build the weather + disruption delta for a site and write it to data/deltas/."""
    from datetime import UTC, datetime, timedelta

    from trip_advisor.pack.delta_builder import build_delta, write_delta
    from trip_advisor.pipeline.collect.http import Fetcher
    from trip_advisor.sites import list_sites, load_site

    fetcher = Fetcher()
    failed = False
    for site_id in list_sites() if site == "all" else [site]:
        today = datetime.now(UTC).date()
        result, errors = build_delta(
            load_site(site_id), fetcher, start=today, end=today + timedelta(days=days)
        )
        path = write_delta(result, site_id)
        typer.echo(
            f"{site_id}: {len(result.weather)} weather days, {len(result.events)} events -> {path}"
        )
        for err in errors:
            typer.echo(f"  gap: {err}", err=True)
        failed = failed or (not result.weather and not result.events)
    if failed:
        raise typer.Exit(1)


@app.command()
def generate(
    site: str = typer.Argument(..., help="Site id"),
    start: str = typer.Option("", help="Trip start date, YYYY-MM-DD (default: in 7 days)"),
    end: str = typer.Option("", help="Trip end date (default: the start date)"),
    start_city: str = typer.Option("Lagos"),
    airport: str = typer.Option("LOS", help="Arrival airport code, or '' for none"),
    group: int = typer.Option(2),
    no_llm: bool = typer.Option(False, help="Rules and templates only, no API call"),
) -> None:
    """Generate an itinerary with verdict from saved routes, records and delta."""
    from datetime import UTC, date, datetime, timedelta

    from trip_advisor.config import settings
    from trip_advisor.pipeline.generate.run import (
        ITINERARIES_DIR,
        generate_itinerary,
        load_input,
    )
    from trip_advisor.pipeline.generate.writer import AnthropicWriter
    from trip_advisor.schemas.itinerary import TripRequest
    from trip_advisor.sites import load_site

    first = date.fromisoformat(start) if start else datetime.now(UTC).date() + timedelta(days=7)
    request = TripRequest(
        site_id=site,
        start_city=start_city,
        arrival_airport=airport or None,
        start_date=first,
        end_date=date.fromisoformat(end) if end else first,
        group_size=group,
    )
    inp = load_input(load_site(site), request)
    for note in inp.notes:
        typer.echo(f"note: {note}", err=True)
    writer = None
    if not no_llm and settings.llm_api_key:
        writer = AnthropicWriter(settings.llm_api_key, settings.generation_model)
    elif not no_llm:
        typer.echo("note: LLM_API_KEY not set, using rules and templates only", err=True)
    violations: list = []  # type: ignore[type-arg]
    itinerary = generate_itinerary(inp, writer, violations=violations)
    from trip_advisor.pipeline.collect.store import save

    path = save(itinerary, ITINERARIES_DIR / f"{site}.json")
    typer.echo(f"{site}: {itinerary.verdict} ({len(itinerary.verdict_reasons)} reasons) -> {path}")
    for v in violations:
        typer.echo(f"  guardrail: {v.where}: {v.kind} ({v.detail})", err=True)
    for reason in itinerary.verdict_reasons:
        typer.echo(f"  [{reason.severity}] {reason.advice}")


@app.command()
def build_pack(site: str = typer.Argument("all", help="Site id, or 'all'")) -> None:
    """Build the versioned offline pack (and slim routes) from structured records."""
    from trip_advisor.pack.builder import build_pack as build
    from trip_advisor.pack.builder import write_pack
    from trip_advisor.pipeline.collect import store
    from trip_advisor.pipeline.collect.models import SiteRoutes
    from trip_advisor.pipeline.structure.models import StructuredSite
    from trip_advisor.sites import list_sites

    failed = False
    for site_id in list_sites() if site == "all" else [site]:
        structured_file = Path("data/structured") / site_id / "structured.json"
        if not structured_file.exists():
            typer.echo(
                f"{site_id}: no structured records, run `structure {site_id}` first", err=True
            )
            failed = True
            continue
        pack, report = build(StructuredSite.model_validate_json(structured_file.read_text()))
        routes_file = store.site_dir(site_id) / "routes.json"
        routes = (
            SiteRoutes.model_validate_json(routes_file.read_text())
            if routes_file.exists()
            else None
        )
        write_pack(pack, routes)
        typer.echo(
            f"{site_id}: pack {report.version}, {report.size_bytes / 1000:.1f} KB, "
            f"{report.kept} records (dropped {report.dropped_stale} stale, "
            f"{report.dropped_for_size} for size)"
        )
    if failed:
        raise typer.Exit(1)


@app.command()
def purge_reports(
    days: int = typer.Option(365, help="Delete reports received before this many days ago"),
) -> None:
    """Delete old reports and ratings (data retention)."""
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from trip_advisor.db.session import DatabaseNotConfigured, get_engine
    from trip_advisor.services.reports import purge_older_than

    try:
        with Session(get_engine()) as session:
            removed = purge_older_than(session, days, now=datetime.now(UTC))
    except DatabaseNotConfigured as exc:
        typer.echo(f"{exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"removed {removed} rows older than {days} days")


@app.command()
def export_schemas(out: Path = Path("data/schemas")) -> None:
    """Write JSON Schema files for the pack, delta, advice and reports."""
    from trip_advisor.schemas.export import export_schemas as export

    for path in export(out):
        typer.echo(path)


if __name__ == "__main__":
    app()
