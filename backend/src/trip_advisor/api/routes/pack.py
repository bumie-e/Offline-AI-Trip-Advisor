from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from trip_advisor.api.deps import (
    daily_cap,
    data_dir,
    model_name,
    now,
    optional_db_session,
    site_or_404,
    writer,
)
from trip_advisor.api.limits import enforce_model_limit
from trip_advisor.pipeline.generate.writer import ItineraryWriter
from trip_advisor.schemas.itinerary import TripRequest
from trip_advisor.schemas.pack import Pack, TripPack
from trip_advisor.services.trips import TripError, build_trip
from trip_advisor.sites import SiteConfig

router = APIRouter(prefix="/pack", tags=["pack"])


@router.get("/{site_id}", response_model=Pack)
def get_pack(
    request: Request,
    site: SiteConfig = Depends(site_or_404),
    base: Path = Depends(data_dir),
) -> Response:
    """The offline pack. The version is the ETag, so an unchanged pack costs a 304."""
    file = base / "packs" / site.id / "pack.json"
    if not file.exists():
        raise HTTPException(404, f"No pack has been built for {site.id!r}")
    raw = file.read_text()
    version = Pack.model_validate_json(raw).version
    etag = f'"{version}"'
    headers = {"ETag": etag, "X-Pack-Version": version, "Cache-Control": "public, max-age=3600"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=raw, media_type="application/json", headers=headers)


@router.post("/{site_id}", response_model=TripPack)
def download_trip_pack(
    http: Request,
    trip: TripRequest,
    site: SiteConfig = Depends(site_or_404),
    ai: bool = True,
    base: Path = Depends(data_dir),
    model: ItineraryWriter | None = Depends(writer),
    session: Session | None = Depends(optional_db_session),
    at: datetime = Depends(now),
    name: str = Depends(model_name),
    cap: int = Depends(daily_cap),
) -> TripPack:
    """The download for a planned trip: the pack, the weather and news it was based on, and the
    itinerary with the model's summary and advice already written. The device keeps all of it."""
    if trip.site_id != site.id:
        raise HTTPException(422, "site_id in the body does not match the URL")
    if ai and model is not None:
        enforce_model_limit(session, http, at)
    try:
        return build_trip(
            trip, base, writer=model if ai else None, model_name=name, session=session,
            now=at, daily_cap=cap,
        )  # fmt: skip
    except TripError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
