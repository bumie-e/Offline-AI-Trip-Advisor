"""Deduplicate records and flag stale, undated or low-confidence ones."""

import re
from datetime import date

from trip_advisor.pipeline.collect.freshness import cutoff
from trip_advisor.schemas.common import Confidence
from trip_advisor.schemas.pack import CostNote, PackRecord, RoadNote, SiteFact

from .models import Flag, FlagKind, Reason, Rejected

SIMILARITY = 0.6


def _key(r: PackRecord) -> tuple[str, str]:
    if isinstance(r, RoadNote):
        return r.type, r.route.lower()
    if isinstance(r, SiteFact):
        return r.type, r.topic.lower()
    if isinstance(r, CostNote):
        return r.type, r.item.lower()
    return r.type, ""


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= SIMILARITY


_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def dedupe(records: list[PackRecord]) -> tuple[list[PackRecord], list[Rejected]]:
    """Within a type+subject group, keep the newest, then most confident, of near-identical ones."""
    ordered = sorted(
        records,
        key=lambda r: (r.source.published or date.min, _RANK[r.confidence]),
        reverse=True,
    )
    kept: list[PackRecord] = []
    dropped: list[Rejected] = []
    for rec in ordered:
        twin = next(
            (k for k in kept if _key(k) == _key(rec) and similar(k.summary, rec.summary)), None
        )
        if twin:
            dropped.append(
                Rejected(doc_id=rec.id, reason=Reason.DUPLICATE, detail=f"duplicate of {twin.id}")
            )
        else:
            kept.append(rec)
    return kept, dropped


def flag_and_downgrade(
    records: list[PackRecord], today: date
) -> tuple[list[PackRecord], list[Flag]]:
    """Stale or undated road evidence is capped at low confidence, and everything is flagged."""
    floor = cutoff(today)
    out: list[PackRecord] = []
    flags: list[Flag] = []
    for rec in records:
        published = rec.source.published
        if published is None and isinstance(rec, RoadNote):  # guides are rarely dated
            flags.append(Flag(record_id=rec.id, kind=FlagKind.UNDATED))
        if isinstance(rec, RoadNote) and published is not None and published < floor:
            flags.append(
                Flag(record_id=rec.id, kind=FlagKind.STALE, detail=f"published {published}")
            )
        if isinstance(rec, RoadNote) and (published is None or published < floor):
            rec = rec.model_copy(update={"confidence": Confidence.LOW})
        if rec.confidence == Confidence.LOW:
            flags.append(Flag(record_id=rec.id, kind=FlagKind.LOW_CONFIDENCE))
        out.append(rec)
    return out, flags
