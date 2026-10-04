"""Store and read the newest published delta per site."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from trip_advisor.db.models import PublishedDeltaRow
from trip_advisor.schemas.delta import Delta


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def publish_delta(session: Session, site_id: str, delta: Delta, *, now: datetime) -> bool:
    """Store the delta unless a newer or equal one is already there. True when stored."""
    row = session.get(PublishedDeltaRow, site_id)
    if row is not None and _utc(row.generated_at) >= _utc(delta.generated_at):
        return False  # never move backwards, e.g. a slow job finishing after a newer one
    payload = delta.model_dump_json()
    if row is None:
        session.add(
            PublishedDeltaRow(
                site_id=site_id, generated_at=delta.generated_at, payload=payload, updated_at=now
            )
        )
    else:
        row.generated_at, row.payload, row.updated_at = delta.generated_at, payload, now
    session.commit()
    return True


def latest_published(session: Session, site_id: str) -> Delta | None:
    row = session.get(PublishedDeltaRow, site_id)
    return Delta.model_validate_json(row.payload) if row else None
