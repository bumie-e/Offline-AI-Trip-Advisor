"""Generate an itinerary: skeleton from routes, rules as a floor, model for the prose."""

import logging
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from trip_advisor.guardrails.checks import (
    Violation,
    ViolationKind,
    check_text,
    guard_advice,
    guard_note,
)
from trip_advisor.pipeline.collect import store as raw_store
from trip_advisor.pipeline.collect.models import SiteRoutes
from trip_advisor.schemas.delta import Delta
from trip_advisor.schemas.itinerary import Advice, Itinerary, Severity, Stop, TripRequest
from trip_advisor.schemas.pack import PackRecord
from trip_advisor.sites import SiteConfig

from .evidence import GenInput
from .rules import SEVERITY_ORDER, Assessment, assess, max_severity, more_cautious
from .skeleton import build_stops
from .summary import template_summary
from .writer import ItineraryWriter, StopNote, WriterOutput

ITINERARIES_DIR = Path("data/itineraries")
log = logging.getLogger(__name__)


def _outline(outbound: list[Stop], back: list[Stop]) -> str:
    rows = [f"{s.order}. {s.title}" for s in outbound]
    return (
        "Outbound:\n"
        + "\n".join(rows)
        + "\nReturn:\n"
        + "\n".join(f"{s.order}. {s.title}" for s in back)
    )


def _apply_notes(stops: list[Stop], notes: list[StopNote]) -> list[Stop]:
    by_order = {n.order: n for n in notes}
    out = []
    for s in stops:
        n = by_order.get(s.order)
        if n:
            ids = [i for i in n.cited_ids if i not in s.cited_ids]
            s = s.model_copy(
                update={"notes": f"{s.notes} {n.note}".strip(), "cited_ids": [*s.cited_ids, *ids]}
            )
        out.append(s)
    return out


def _rank(severity: Severity) -> int:
    return SEVERITY_ORDER.index(severity)


@dataclass
class Merged:
    reasons: list[Advice]
    notes: list[StopNote]
    summary: str  # empty when the model's summary cannot be used
    model_text_used: bool  # False when the rule text replaced the model's reasons


def merge(
    inp: GenInput,
    findings: Assessment,
    written: WriterOutput | None,
    violations: list[Violation] | None = None,
) -> Merged:
    """Guard the model's reasons, notes and summary; use them only if they do not under-warn."""
    if written is None:
        return Merged(findings.advice, [], "", False)
    seen = violations if violations is not None else []
    catalog = inp.catalog()
    reasons: list[Advice] = []
    any_replaced = False
    for i, reason in enumerate(written.verdict_reasons, start=1):
        guarded = guard_advice(reason, catalog)
        seen += [replace(v, where=f"reason {i}") for v in guarded.violations]
        any_replaced = any_replaced or guarded.replaced
        reasons.append(guarded.advice)
    notes: list[StopNote] = []
    for note in written.stop_notes:
        ok, found = guard_note(note.note, note.cited_ids, catalog)
        if not note.cited_ids:  # a note nothing backs up cannot be checked, so it is dropped
            ok, found = False, [*found, Violation(ViolationKind.UNCITED, note.note[:60])]
        seen += [replace(v, where=f"stop {note.order}") for v in found]
        if ok:
            notes.append(note)
    # One failed line means the model is not trusted for this itinerary: the rule text is a
    # better template than a generic sentence, because it is specific and already cited.
    if (
        any_replaced
        or not reasons
        or _rank(max_severity(reasons)) < _rank(max_severity(findings.advice))
    ):
        return Merged(findings.advice, notes, "", False)
    # The summary may only lean on what the reasons cite, so its figures are checked against that.
    cited = sorted({i for r in reasons for i in r.cited_ids})
    summary = written.summary.strip()
    found = check_text(summary, cited, catalog) if summary else []
    seen += [replace(v, where="summary") for v in found]
    return Merged(reasons, notes, "" if found else summary, True)


def generate_itinerary(
    inp: GenInput,
    writer: ItineraryWriter | None = None,
    *,
    now: datetime | None = None,
    violations: list[Violation] | None = None,
) -> Itinerary:
    return generate_with_meta(inp, writer, now=now, violations=violations)[0]


def generate_with_meta(
    inp: GenInput,
    writer: ItineraryWriter | None = None,
    *,
    now: datetime | None = None,
    violations: list[Violation] | None = None,
) -> tuple[Itinerary, bool]:
    """The itinerary, and whether the model's text made it into it."""
    findings = assess(inp)
    outbound, back = build_stops(inp)
    written = None
    if writer:
        try:
            written = writer.write(inp, findings, _outline(outbound, back))
        except Exception as exc:  # noqa: BLE001 - a model outage must not break the trip plan
            log.warning("itinerary writer failed, using rule text: %s", exc)
    merged = merge(inp, findings, written, violations)
    verdict = findings.verdict
    if written is not None and merged.model_text_used:
        verdict = more_cautious(verdict, written.verdict)
    summary = merged.summary or template_summary(inp, verdict, merged.reasons)
    itinerary = Itinerary(
        site_id=inp.site.id,
        generated_at=now or datetime.now(UTC),
        request=inp.request,
        verdict=verdict,
        summary=summary,
        verdict_reasons=merged.reasons,
        stops=_apply_notes(outbound, merged.notes),
        return_leg=back,
    )
    return itinerary, merged.model_text_used


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


def load_serving_input(
    site: SiteConfig,
    request: TripRequest,
    *,
    packs_dir: Path = Path("data/packs"),
    deltas_dir: Path = Path("data/deltas"),
    today: date | None = None,
) -> GenInput:
    """Like `load_input`, but from the built pack, which is all the deployed API carries."""
    from trip_advisor.schemas.pack import Pack

    notes: list[str] = []
    base = packs_dir / site.id
    pack_file, routes_file = base / "pack.json", base / "routes.json"
    records = Pack.model_validate_json(pack_file.read_text()).records if pack_file.exists() else []
    if not pack_file.exists():
        notes.append(f"no pack for {site.id}")
    routes = (
        SiteRoutes.model_validate_json(routes_file.read_text()) if routes_file.exists() else None
    )
    delta_file = deltas_dir / f"{site.id}.json"
    delta = (
        Delta.model_validate_json(delta_file.read_text())
        if delta_file.exists()
        else Delta(generated_at=datetime.now(UTC))
    )
    return GenInput(
        site=site,
        request=request,
        routes=routes,
        records=records,
        delta=delta,
        today=today or datetime.now(UTC).date(),
        notes=notes,
    )
