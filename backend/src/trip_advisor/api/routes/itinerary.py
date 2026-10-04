from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from trip_advisor.api.deps import daily_cap, data_dir, model_name, now, optional_db_session, writer
from trip_advisor.api.limits import enforce_model_limit
from trip_advisor.pipeline.generate.writer import ItineraryWriter
from trip_advisor.schemas.itinerary import Itinerary, TripRequest
from trip_advisor.services.trips import TripError, build_trip

router = APIRouter(prefix="/itinerary", tags=["itinerary"])


@router.post("", response_model=Itinerary)
def create_itinerary(
    http: Request,
    request: TripRequest,
    ai: bool = True,
    base: Path = Depends(data_dir),
    model: ItineraryWriter | None = Depends(writer),
    session: Session | None = Depends(optional_db_session),
    at: datetime = Depends(now),
    name: str = Depends(model_name),
    cap: int = Depends(daily_cap),
) -> Itinerary:
    """Itinerary with verdict, summary and advice. The model writes the text unless `ai=false`,
    a daily cap is reached, or it fails; then the rule-based text is used. Nothing is stored
    except the (cached) result for identical requests."""
    if ai and model is not None:
        enforce_model_limit(session, http, at)
    try:
        trip = build_trip(
            request, base, writer=model if ai else None, model_name=name, session=session,
            now=at, daily_cap=cap,
        )  # fmt: skip
    except TripError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return trip.itinerary
