from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from trip_advisor.api.deps import data_dir, site_or_404
from trip_advisor.schemas.delta import Delta
from trip_advisor.sites import SiteConfig

router = APIRouter(prefix="/delta", tags=["delta"])


@router.get("/{site_id}", response_model=Delta)
def get_delta(site: SiteConfig = Depends(site_or_404), base: Path = Depends(data_dir)) -> Delta:
    """Latest weather and disruption snapshot. A few KB; the device compares `generated_at`."""
    file = base / "deltas" / f"{site.id}.json"
    if not file.exists():
        raise HTTPException(404, f"No delta has been built for {site.id!r}")
    return Delta.model_validate_json(file.read_text())
