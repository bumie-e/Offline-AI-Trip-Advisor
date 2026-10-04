"""Build the offline pack for a site from structured records. Versioned and size-capped."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from trip_advisor.pipeline.collect import store
from trip_advisor.pipeline.collect.freshness import cutoff
from trip_advisor.pipeline.collect.models import SiteRoutes
from trip_advisor.pipeline.structure.models import StructuredSite
from trip_advisor.schemas.common import Confidence
from trip_advisor.schemas.pack import ImageRecord, Pack, PackRecord, RoadNote

PACKS_DIR = Path("data/packs")
MAX_PACK_BYTES = 100_000  # downloaded once on Wi-Fi, but still stored on a phone
_RANK = {Confidence.HIGH: 2, Confidence.MEDIUM: 1, Confidence.LOW: 0}


@dataclass
class BuildReport:
    version: str
    size_bytes: int
    kept: int
    dropped_stale: int
    dropped_for_size: int


def _stale(rec: PackRecord, today: date) -> bool:
    """Old or undated road evidence misleads more than it helps, so it stays out of the pack."""
    if not isinstance(rec, RoadNote):
        return False
    published = rec.source.published
    return published is None or published < cutoff(today)


def _priority(rec: PackRecord) -> tuple[int, int, int]:
    # Site facts first (small, stable), then the most confident and newest road evidence.
    is_road = isinstance(rec, RoadNote)
    return (
        1 if is_road else 0,
        -_RANK[rec.confidence],
        -(rec.source.published or date.min).toordinal(),  # newest first
    )


def version_for(records: list[PackRecord], today: date) -> str:
    """Same content gives the same version, so a device can skip an unchanged download."""
    body = json.dumps([r.model_dump(mode="json") for r in records], sort_keys=True)
    return f"{today:%Y.%m.%d}+{hashlib.sha256(body.encode()).hexdigest()[:8]}"


def build_pack(
    structured: StructuredSite,
    *,
    today: date | None = None,
    now: datetime | None = None,
    images: Sequence[ImageRecord] = (),
) -> tuple[Pack, BuildReport]:
    """Images are small records (the files are fetched separately), so they ride in the pack."""
    now = now or datetime.now(UTC)
    today = today or now.date()
    fresh = [r for r in [*structured.records, *images] if not _stale(r, today)]
    ranked = sorted(fresh, key=_priority)

    def pack_of(records: list[PackRecord]) -> Pack:
        return Pack(
            site_id=structured.site_id,
            version=version_for(records, today),
            generated_at=now,
            records=records,
        )

    kept = ranked
    while len(kept) > 1 and len(pack_of(kept).model_dump_json().encode()) > MAX_PACK_BYTES:
        kept = kept[:-1]  # drop the lowest priority first
    pack = pack_of(kept)
    return pack, BuildReport(
        version=pack.version,
        size_bytes=len(pack.model_dump_json().encode()),
        kept=len(kept),
        dropped_stale=len(structured.records) + len(images) - len(fresh),
        dropped_for_size=len(fresh) - len(kept),
    )


def slim_routes(routes: SiteRoutes) -> SiteRoutes:
    """Route shapes are for maps, not for advice. Dropping them keeps the pack download small."""
    return routes.model_copy(
        update={"routes": [r.model_copy(update={"geometry": []}) for r in routes.routes]}
    )


def write_pack(
    pack: Pack, routes: SiteRoutes | None, out_dir: Path = PACKS_DIR
) -> tuple[Path, Path | None]:
    base = out_dir / pack.site_id
    pack_path = store.save(pack, base / "pack.json")
    routes_path = store.save(slim_routes(routes), base / "routes.json") if routes else None
    return pack_path, routes_path
