"""Deduplicate records and flag stale, undated or low-confidence ones."""

import re
from datetime import date

from trip_advisor.pipeline.collect.freshness import cutoff
from trip_advisor.schemas.common import Confidence
from trip_advisor.schemas.pack import CostNote, PackRecord, RoadNote, SiteFact

from .models import Flag, FlagKind, Reason, Rejected

SIMILARITY = 0.5
_FILLER = {
    "the", "a", "an", "of", "on", "in", "at", "to", "for", "and", "or", "is", "are", "was", "has",
    "have", "been", "by", "with", "from", "that", "this", "it", "as", "be", "its", "their",
    "report", "reports", "reported", "suggest", "suggests", "indicate", "indicates", "caused",
    "causing", "road", "roads", "expressway", "highway", "state", "news", "according",
}  # fmt: skip


def _subject(r: PackRecord) -> str:
    if isinstance(r, RoadNote):
        return r.route
    if isinstance(r, SiteFact):
        return r.topic
    if isinstance(r, CostNote):
        return r.item
    return ""


def _key(r: PackRecord) -> str:
    return r.type


def _tokens(text: str) -> set[str]:
    out = set()
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if t not in _FILLER:
            out.add("construct" if t.startswith(("construct", "reconstruct")) else t)
    return out


def similar(a: PackRecord, b: PackRecord) -> bool:
    """Same kind of record and the same event: summaries overlap once the road's own name,
    the topic and filler words are set aside, so differently-worded reports of one event merge."""
    if _key(a) != _key(b):
        return False
    sa, sb = _tokens(_subject(a)), _tokens(_subject(b))
    if sa and sb and not (sa & sb):
        return False  # different roads (or topics) are different records
    subject = sa | sb
    ta, tb = _tokens(a.summary) - subject, _tokens(b.summary) - subject
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
        twin = next((k for k in kept if similar(k, rec)), None)
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
