"""Structure collected documents of one site into pack records, ready for the pack builder."""

import json
import random
from datetime import UTC, date, datetime
from pathlib import Path

from trip_advisor.pipeline.collect import store as raw_store
from trip_advisor.pipeline.collect.models import DocKind, RawDocument
from trip_advisor.schemas.common import Confidence
from trip_advisor.schemas.pack import PackRecord, RoadNote
from trip_advisor.sites import SiteConfig

from .extractor import Extractor
from .models import Flag, FlagKind, Reason, Rejected, StructuredSite
from .refine import dedupe, flag_and_downgrade
from .validate import build_record, cap_confidence

STRUCTURED_DIR = Path("data/structured")
HEADLINE_MAX_CHARS = 200  # collected news is title + publisher until a page is fetched
SAMPLE_SIZE = 10


def load_docs(site_id: str, raw_dir: Path = raw_store.RAW_DIR) -> list[RawDocument]:
    base = raw_store.site_dir(site_id, raw_dir)
    files = [*sorted((base / "guides").glob("*.json")), *sorted((base / "evidence").glob("*.json"))]
    return [RawDocument.model_validate_json(f.read_text()) for f in files]


def structure_docs(
    site: SiteConfig, docs: list[RawDocument], extractor: Extractor, today: date
) -> StructuredSite:
    records: list[PackRecord] = []
    rejected: list[Rejected] = []
    flags: list[Flag] = []
    for doc in docs:
        try:
            proposed = extractor.extract(doc, site.name)
        except Exception as exc:  # noqa: BLE001 - one bad document must not stop the run
            rejected.append(Rejected(doc_id=doc.id, reason=Reason.EXTRACTOR_ERROR, detail=str(exc)))
            continue
        headline_only = len(doc.text) <= HEADLINE_MAX_CHARS
        for raw in proposed:
            built = build_record(raw, doc, today)
            if isinstance(built, Rejected):
                rejected.append(built)
                continue
            record, item = built
            if isinstance(record, RoadNote) and item.rain_sensitivity is None:
                record = cap_confidence(record, Confidence.LOW)
                flags.append(Flag(record_id=record.id, kind=FlagKind.ASSUMED_SENSITIVITY))
            if doc.kind == DocKind.ROUTE_GUIDE:  # crowd-sourced: never "high"
                capped = cap_confidence(record, Confidence.MEDIUM)
                if capped is not record:
                    flags.append(Flag(record_id=record.id, kind=FlagKind.GUIDE_CAPPED))
                record = capped
            if headline_only:
                capped = cap_confidence(record, Confidence.LOW)
                if capped is not record:
                    flags.append(Flag(record_id=record.id, kind=FlagKind.HEADLINE_ONLY))
                record = capped
            records.append(record)
    records, dups = dedupe(records)
    records, more_flags = flag_and_downgrade(records, today)
    live = {r.id for r in records}
    return StructuredSite(
        site_id=site.id,
        structured_on=today,
        records=records,
        flags=[f for f in [*flags, *more_flags] if f.record_id in live],
        rejected=[*rejected, *dups],
        docs_processed=len(docs),
    )


def structure_site(
    site: SiteConfig,
    extractor: Extractor,
    *,
    today: date | None = None,
    raw_dir: Path = raw_store.RAW_DIR,
    out_dir: Path = STRUCTURED_DIR,
) -> StructuredSite:
    today = today or datetime.now(UTC).date()
    result = structure_docs(site, load_docs(site.id, raw_dir), extractor, today)
    base = out_dir / site.id
    raw_store.save(result, base / "structured.json")
    write_review_sample(result, base / "review.md")
    return result


def write_review_sample(result: StructuredSite, path: Path, seed: int = 0) -> None:
    """A random sample laid out for hand-checking against the source, not for the app."""
    rng = random.Random(seed)
    picks = rng.sample(result.records, min(SAMPLE_SIZE, len(result.records)))
    lines = [f"# Hand-check: {result.site_id} ({len(picks)} of {len(result.records)} records)", ""]
    for r in picks:
        lines += [
            f"## {r.id} [{r.type}, {r.confidence}]",
            f"- summary: {r.summary}",
            f"- source: {r.source.publisher}, {r.source.published}, {r.source.url}",
            "- [ ] supported by the source   [ ] wording is advisory   [ ] confidence fair",
            "",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def summary_line(result: StructuredSite) -> str:
    reasons: dict[str, int] = {}
    for rej in result.rejected:
        reasons[rej.reason] = reasons.get(rej.reason, 0) + 1
    return (
        f"docs={result.docs_processed} records={len(result.records)} "
        f"flags={len(result.flags)} rejected={json.dumps(reasons)}"
    )
