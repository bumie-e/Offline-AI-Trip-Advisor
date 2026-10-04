"""Store queued reports and ratings. Idempotent by client-generated id, so retries are safe."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trip_advisor.db.models import (
    AdviceRatingRow,
    Base,
    RoadReportRow,
    SiteStatusReportRow,
)
from trip_advisor.schemas.api import Receipt, Rejection
from trip_advisor.schemas.reports import AdviceRating, RoadReport, SiteStatusReport

from .privacy import redact, round_coord

MAX_BATCH = 50
MAX_AGE = timedelta(days=30)  # a queued report older than this is no longer evidence
MAX_FUTURE = timedelta(days=1)  # allows for a phone with a wrong clock
RETENTION_DAYS = 365


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _time_problem(when: datetime, now: datetime) -> str | None:
    when = _utc(when)
    if when > now + MAX_FUTURE:
        return "timestamp is in the future"
    if when < now - MAX_AGE:
        return "report is older than 30 days"
    return None


def _ingest[R: (RoadReport, SiteStatusReport, AdviceRating)](
    session: Session,
    items: Sequence[R],
    row_type: type[Base],
    *,
    check: Callable[[R], str | None],
    to_row: Callable[[R], Any],
) -> Receipt:
    receipt = Receipt()
    existing = set(
        session.scalars(
            select(row_type.id).where(row_type.id.in_([i.id for i in items]))  # type: ignore[attr-defined]
        )
    )
    seen: set[UUID] = set()
    for item in items:
        if item.id in existing or item.id in seen:
            receipt.duplicates.append(item.id)
            continue
        if problem := check(item):
            receipt.rejected.append(Rejection(id=item.id, reason=problem))
            continue
        try:
            with session.begin_nested():  # a lost race on the id must not undo the whole batch
                session.add(to_row(item))
        except IntegrityError:
            receipt.duplicates.append(item.id)
            continue
        seen.add(item.id)
        receipt.accepted.append(item.id)
    session.commit()
    return receipt


def save_road_reports(
    session: Session, reports: Sequence[RoadReport], *, route_ids: set[str] | None, now: datetime
) -> Receipt:
    def check(r: RoadReport) -> str | None:
        if route_ids is not None and r.route_id not in route_ids:
            return f"unknown route {r.route_id!r}"
        return _time_problem(r.reported_at, now)

    def to_row(r: RoadReport) -> RoadReportRow:
        return RoadReportRow(
            id=r.id, site_id=r.site_id, reported_at=_utc(r.reported_at), route_id=r.route_id,
            condition=r.condition.value, lat=round_coord(r.lat), lon=round_coord(r.lon),
            note=redact(r.note), received_at=now,
        )  # fmt: skip

    return _ingest(session, reports, RoadReportRow, check=check, to_row=to_row)


def save_site_reports(
    session: Session, reports: Sequence[SiteStatusReport], *, now: datetime
) -> Receipt:
    def to_row(r: SiteStatusReport) -> SiteStatusReportRow:
        return SiteStatusReportRow(
            id=r.id, site_id=r.site_id, reported_at=_utc(r.reported_at), status=r.status.value,
            lat=round_coord(r.lat), lon=round_coord(r.lon), note=redact(r.note), received_at=now,
        )  # fmt: skip

    return _ingest(
        session, reports, SiteStatusReportRow,
        check=lambda r: _time_problem(r.reported_at, now), to_row=to_row,
    )  # fmt: skip


def save_ratings(session: Session, ratings: Sequence[AdviceRating], *, now: datetime) -> Receipt:
    def to_row(r: AdviceRating) -> AdviceRatingRow:
        return AdviceRatingRow(
            id=r.id, site_id=r.site_id, rated_at=_utc(r.rated_at), helpful=r.helpful,
            comment=redact(r.comment), received_at=now,
        )  # fmt: skip

    return _ingest(
        session, ratings, AdviceRatingRow,
        check=lambda r: _time_problem(r.rated_at, now), to_row=to_row,
    )  # fmt: skip


def purge_older_than(session: Session, days: int = RETENTION_DAYS, *, now: datetime) -> int:
    """Delete rows received before the cutoff. Returns the number removed."""
    cutoff = now - timedelta(days=days)
    removed = 0
    for row_type in (RoadReportRow, SiteStatusReportRow, AdviceRatingRow):
        removed += session.execute(delete(row_type).where(row_type.received_at < cutoff)).rowcount  # type: ignore[attr-defined]
    session.commit()
    return removed
