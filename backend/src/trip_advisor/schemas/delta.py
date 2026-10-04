from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from .common import Source, Strict


class EventType(StrEnum):
    STRIKE = "strike"
    FLIGHT_SUSPENSION = "flight_suspension"
    HEAVY_RAIN = "heavy_rain"
    ROAD_CLOSURE = "road_closure"
    OTHER = "other"


class EventStatus(StrEnum):
    THREATENED = "threatened"
    CONFIRMED = "confirmed"
    ENDED = "ended"


class WeatherEntry(Strict):
    date: date
    area: str
    rain_probability: float = Field(ge=0, le=1)


class DisruptionEvent(Strict):
    type: EventType
    status: EventStatus
    affects: list[str]  # e.g. ["flights"], ["road:lagos-abeokuta"]
    start: date | None = None
    end: date | None = None
    source_id: str
    source: Source | None = None  # the story behind the event, so it can be audited


class Delta(Strict):
    """A few KB of weather and news. Roads are not re-collected here."""

    generated_at: datetime
    weather: list[WeatherEntry] = Field(default_factory=list)
    events: list[DisruptionEvent] = Field(default_factory=list)
