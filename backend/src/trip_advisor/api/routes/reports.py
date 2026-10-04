from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from trip_advisor.api.deps import data_dir, db_session, now
from trip_advisor.schemas.api import Receipt
from trip_advisor.schemas.reports import AdviceRating, RoadReport, SiteStatusReport
from trip_advisor.services import reports as svc
from trip_advisor.sites import list_sites

router = APIRouter(prefix="/reports", tags=["reports"])
Batch = Body(max_length=svc.MAX_BATCH)


def _known_sites(base: Path) -> set[str]:
    return set(list_sites(base / "sites"))


def _check_sites(site_ids: set[str], base: Path) -> None:
    if unknown := site_ids - _known_sites(base):
        raise HTTPException(404, f"Unknown place(s): {', '.join(sorted(unknown))}")


def _route_ids(site_id: str, base: Path) -> set[str] | None:
    from trip_advisor.pipeline.collect.models import SiteRoutes

    file = base / "packs" / site_id / "routes.json"
    if not file.exists():
        return None  # cannot validate; accept rather than lose the report
    return {r.id for r in SiteRoutes.model_validate_json(file.read_text()).routes}


@router.post("/road", response_model=Receipt)
def road_reports(
    reports: Annotated[list[RoadReport], Batch],
    db: Session = Depends(db_session),
    base: Path = Depends(data_dir),
    at: datetime = Depends(now),
) -> Receipt:
    """Sync queued road reports. Safe to retry: reports already stored come back as duplicates."""
    _check_sites({r.site_id for r in reports}, base)
    result = Receipt()
    for site_id in {r.site_id for r in reports}:
        part = svc.save_road_reports(
            db,
            [r for r in reports if r.site_id == site_id],
            route_ids=_route_ids(site_id, base),
            now=at,
        )
        result.accepted += part.accepted
        result.duplicates += part.duplicates
        result.rejected += part.rejected
    return result


@router.post("/site-status", response_model=Receipt)
def site_reports(
    reports: Annotated[list[SiteStatusReport], Batch],
    db: Session = Depends(db_session),
    base: Path = Depends(data_dir),
    at: datetime = Depends(now),
) -> Receipt:
    _check_sites({r.site_id for r in reports}, base)
    return svc.save_site_reports(db, reports, now=at)


@router.post("/ratings", response_model=Receipt)
def ratings(
    items: Annotated[list[AdviceRating], Batch],
    db: Session = Depends(db_session),
    base: Path = Depends(data_dir),
    at: datetime = Depends(now),
) -> Receipt:
    _check_sites({r.site_id for r in items}, base)
    return svc.save_ratings(db, items, now=at)
