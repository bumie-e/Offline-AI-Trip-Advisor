"""Build the downloadable trip pack: pack + delta + the itinerary and advice written for it.

The model writes the advice, so each call costs money and takes seconds. Three controls:
identical requests are served from a cache, a daily cap stops runaway use, and any failure
falls back to the rule-based text, so a traveller always gets an answer.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from trip_advisor.db.models import ItineraryCacheRow
from trip_advisor.pack.routes import to_pack_routes
from trip_advisor.pipeline.generate.run import generate_with_meta, load_serving_input
from trip_advisor.pipeline.generate.writer import ItineraryWriter
from trip_advisor.schemas.delta import Delta
from trip_advisor.schemas.itinerary import Itinerary, TripRequest
from trip_advisor.schemas.pack import Pack, TripPack
from trip_advisor.sites import list_sites, load_site

log = logging.getLogger(__name__)
MAX_TRIP_DAYS = 14


class TripError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def check_request(request: TripRequest, base: Path) -> None:
    if request.site_id not in list_sites(base / "sites"):
        raise TripError(404, f"Unknown place {request.site_id!r}")
    if request.end_date < request.start_date:
        raise TripError(422, "end_date is before start_date")
    if request.end_date - request.start_date > timedelta(days=MAX_TRIP_DAYS):
        raise TripError(422, f"Trips longer than {MAX_TRIP_DAYS} days are not supported")
    if not (base / "packs" / request.site_id / "pack.json").exists():
        raise TripError(404, f"No pack has been built for {request.site_id!r}")


def cache_key(request: TripRequest, pack: Pack, delta: Delta, model: str, today: datetime) -> str:
    """Everything that shapes the advice. A new pack, delta, model or day gives a new key."""
    parts = [
        request.model_dump_json(),
        pack.version,
        delta.generated_at.isoformat(),
        model,
        today.date().isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass
class _Gate:
    """Whether the model may be called right now, and a cached answer if there is one."""

    allowed: bool
    cached: Itinerary | None = None


def _gate(session: Session | None, key: str, now: datetime, cap: int) -> _Gate:
    if session is None:  # no database (local development): no cache and no cap to enforce
        return _Gate(True)
    try:
        row = session.get(ItineraryCacheRow, key)
        if row:
            return _Gate(False, Itinerary.model_validate_json(row.payload))
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        used = session.scalar(
            select(func.count())
            .select_from(ItineraryCacheRow)
            .where(ItineraryCacheRow.created_at >= start)
        )
        return _Gate((used or 0) < cap)
    except SQLAlchemyError as exc:
        # Cannot check the cache or the cap, so do not spend money: use the rule text.
        log.error("cache unavailable, model skipped: %s", exc)
        session.rollback()
        return _Gate(False)


def _store(session: Session, key: str, itinerary: Itinerary, now: datetime) -> None:
    try:
        session.add(
            ItineraryCacheRow(
                key=key,
                site_id=itinerary.site_id,
                payload=itinerary.model_dump_json(),
                created_at=now,
            )
        )
        session.commit()
    except SQLAlchemyError as exc:  # a lost race or an outage: the result is still returned
        log.warning("could not cache itinerary: %s", exc)
        session.rollback()


def build_trip(
    request: TripRequest,
    base: Path,
    *,
    writer: ItineraryWriter | None,
    model_name: str,
    session: Session | None,
    now: datetime,
    daily_cap: int,
) -> TripPack:
    check_request(request, base)
    inp = load_serving_input(
        load_site(request.site_id, base / "sites"),
        request,
        packs_dir=base / "packs",
        deltas_dir=base / "deltas",
        today=now.date(),
    )
    pack = Pack.model_validate_json((base / "packs" / request.site_id / "pack.json").read_text())

    itinerary: Itinerary | None = None
    used_model = False
    if writer is not None:
        key = cache_key(request, pack, inp.delta, model_name, now)
        gate = _gate(session, key, now, daily_cap)
        if gate.cached is not None:
            itinerary, used_model = gate.cached, True
        elif gate.allowed:
            itinerary, used_model = generate_with_meta(inp, writer, now=now)
            if used_model and session is not None:
                _store(session, key, itinerary, now)
    if itinerary is None:
        itinerary, _ = generate_with_meta(inp, None, now=now)
    source: Literal["model", "rules"] = "model" if used_model else "rules"
    routes = to_pack_routes(inp.routes) if inp.routes else None
    return TripPack(
        pack=pack, delta=inp.delta, itinerary=itinerary, routes=routes, advice_source=source
    )
