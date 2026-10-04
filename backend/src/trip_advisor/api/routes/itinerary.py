from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from trip_advisor.api.deps import data_dir, now, writer
from trip_advisor.pipeline.generate.run import generate_itinerary, load_serving_input
from trip_advisor.pipeline.generate.writer import ItineraryWriter
from trip_advisor.schemas.itinerary import Itinerary, TripRequest
from trip_advisor.sites import list_sites, load_site

router = APIRouter(prefix="/itinerary", tags=["itinerary"])
MAX_TRIP_DAYS = 14


@router.post("", response_model=Itinerary)
def create_itinerary(
    request: TripRequest,
    ai: bool = False,
    base: Path = Depends(data_dir),
    model: ItineraryWriter | None = Depends(writer),
) -> Itinerary:
    """Build an itinerary from the stored pack and delta. The request itself is not stored."""
    if request.site_id not in list_sites(base / "sites"):
        raise HTTPException(404, f"Unknown place {request.site_id!r}")
    if request.end_date < request.start_date:
        raise HTTPException(422, "end_date is before start_date")
    if request.end_date - request.start_date > timedelta(days=MAX_TRIP_DAYS):
        raise HTTPException(422, f"Trips longer than {MAX_TRIP_DAYS} days are not supported")
    if not (base / "packs" / request.site_id / "pack.json").exists():
        raise HTTPException(404, f"No pack has been built for {request.site_id!r}")
    inp = load_serving_input(
        load_site(request.site_id, base / "sites"),
        request,
        packs_dir=base / "packs",
        deltas_dir=base / "deltas",
        today=now().date(),
    )
    return generate_itinerary(inp, model if ai else None)
