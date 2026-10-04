"""Generate an itinerary: skeleton from routes, rules as a floor, model for the prose."""

from datetime import UTC, date, datetime
from pathlib import Path

from trip_advisor.pipeline.collect import store as raw_store
from trip_advisor.pipeline.collect.models import SiteRoutes
from trip_advisor.schemas.delta import Delta
from trip_advisor.schemas.itinerary import Advice, Itinerary, Stop, TripRequest
from trip_advisor.schemas.pack import PackRecord
from trip_advisor.sites import SiteConfig

from .evidence import GenInput
from .rules import SEVERITY_ORDER, Assessment, assess, max_severity, more_cautious
from .skeleton import build_stops
from .writer import ItineraryWriter, StopNote, WriterOutput

ITINERARIES_DIR = Path("data/itineraries")


def _outline(outbound: list[Stop], back: list[Stop]) -> str:
    rows = [f"{s.order}. {s.title}" for s in outbound]
    return (
        "Outbound:\n"
        + "\n".join(rows)
        + "\nReturn:\n"
        + "\n".join(f"{s.order}. {s.title}" for s in back)
    )


def _uses_only_known_ids(items: list[Advice], known: set[str]) -> bool:
    return all(set(a.cited_ids) <= known for a in items)


def _apply_notes(stops: list[Stop], notes: list[StopNote]) -> list[Stop]:
    by_order = {n.order: n.note for n in notes}
    out = []
    for s in stops:
        extra = by_order.get(s.order)
        out.append(s.model_copy(update={"notes": f"{s.notes} {extra}".strip()}) if extra else s)
    return out


def merge(
    inp: GenInput, findings: Assessment, written: WriterOutput | None
) -> tuple[list[Advice], list[StopNote]]:
    """Use the model's reasons only if they cite known IDs and do not under-warn the rules."""
    if written is None:
        return findings.advice, []
    ok = _uses_only_known_ids(written.verdict_reasons, inp.known_ids()) and bool(
        written.verdict_reasons
    )
    covers = ok and SEVERITY_ORDER.index(max_severity(written.verdict_reasons)) >= (
        SEVERITY_ORDER.index(max_severity(findings.advice))
    )
    return (written.verdict_reasons if ok and covers else findings.advice), written.stop_notes


def generate_itinerary(
    inp: GenInput, writer: ItineraryWriter | None = None, *, now: datetime | None = None
) -> Itinerary:
    findings = assess(inp)
    outbound, back = build_stops(inp)
    written = writer.write(inp, findings, _outline(outbound, back)) if writer else None
    reasons, notes = merge(inp, findings, written)
    verdict = findings.verdict
    if written is not None:
        verdict = more_cautious(verdict, written.verdict)
    return Itinerary(
        site_id=inp.site.id,
        generated_at=now or datetime.now(UTC),
        request=inp.request,
        verdict=verdict,
        verdict_reasons=reasons,
        stops=_apply_notes(outbound, notes),
        return_leg=back,
    )


def load_input(
    site: SiteConfig,
    request: TripRequest,
    *,
    today: date | None = None,
    raw_dir: Path = raw_store.RAW_DIR,
    structured_dir: Path = Path("data/structured"),
    deltas_dir: Path = Path("data/deltas"),
) -> GenInput:
    """Read the saved outputs of the collect, structure and context phases."""
    notes: list[str] = []
    routes_file = raw_store.site_dir(site.id, raw_dir) / "routes.json"
    routes = (
        SiteRoutes.model_validate_json(routes_file.read_text()) if routes_file.exists() else None
    )
    if routes is None:
        notes.append(f"no routes for {site.id}: run `collect {site.id}`")

    records: list[PackRecord] = []
    structured = structured_dir / site.id / "structured.json"
    if structured.exists():
        from trip_advisor.pipeline.structure.models import StructuredSite

        records = StructuredSite.model_validate_json(structured.read_text()).records
    else:
        notes.append(f"no records for {site.id}: run `structure {site.id}`")

    delta_file = deltas_dir / f"{site.id}.json"
    if delta_file.exists():
        delta = Delta.model_validate_json(delta_file.read_text())
    else:
        delta = Delta(generated_at=datetime.now(UTC))
        notes.append(f"no delta for {site.id}: run `delta {site.id}`")
    return GenInput(
        site=site,
        request=request,
        routes=routes,
        records=records,
        delta=delta,
        today=today or datetime.now(UTC).date(),
        notes=notes,
    )
