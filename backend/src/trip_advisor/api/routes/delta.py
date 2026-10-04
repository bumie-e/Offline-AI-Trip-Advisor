import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from trip_advisor.api.deps import data_dir, optional_db_session, site_or_404
from trip_advisor.schemas.delta import Delta
from trip_advisor.services.deltas import latest_published
from trip_advisor.sites import SiteConfig

router = APIRouter(prefix="/delta", tags=["delta"])
log = logging.getLogger(__name__)


@router.get("/{site_id}", response_model=Delta)
def get_delta(
    site: SiteConfig = Depends(site_or_404),
    base: Path = Depends(data_dir),
    db: Session | None = Depends(optional_db_session),
) -> Delta:
    """Latest weather and disruption snapshot. A few KB; the device compares `generated_at`.

    A scheduled job publishes fresh deltas to the database. The delta bundled with the deploy is
    the fallback, and whichever is newer wins. A missing table or an unreachable database never
    breaks this endpoint.
    """
    candidates: list[Delta] = []
    file = base / "deltas" / f"{site.id}.json"
    if file.exists():
        candidates.append(Delta.model_validate_json(file.read_text()))
    if db is not None:
        try:
            if published := latest_published(db, site.id):
                candidates.append(published)
        except SQLAlchemyError:
            db.rollback()
            log.warning("published delta unavailable, using the bundled one", exc_info=True)
    if not candidates:
        raise HTTPException(404, f"No delta has been built for {site.id!r}")
    return max(candidates, key=lambda d: d.generated_at)
