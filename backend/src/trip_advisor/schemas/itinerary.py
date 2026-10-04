from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from .common import Strict


class Verdict(StrEnum):
    GO = "go"
    GO_WITH_CHANGES = "go_with_changes"
    NOT_ADVISED = "not_advised"


class Severity(StrEnum):
    NONE = "none"
    ELEVATED = "elevated"
    HIGH = "high"


class TravelMode(StrEnum):
    ROAD = "road"
    TRAIN = "train"
    FLIGHT = "flight"
    WALK = "walk"


class TripRequest(Strict):
    """Stage 2, 'Plan my visit'."""

    site_id: str
    start_city: str
    arrival_airport: str | None = None
    start_date: date
    end_date: date
    group_size: int = Field(ge=1, le=50)
    budget_ngn: int | None = Field(default=None, ge=0)
    mode: TravelMode | None = None


class Stop(Strict):
    order: int = Field(ge=1)
    title: str
    mode: TravelMode | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    notes: str = ""
    cited_ids: list[str] = Field(default_factory=list)


class Advice(Strict):
    """Structured model output, also produced on-device. Checked by guardrails."""

    changed: bool
    severity: Severity
    advice: str
    alternatives: list[str] = Field(default_factory=list)
    cited_ids: list[str]


class Itinerary(Strict):
    site_id: str
    generated_at: datetime
    request: TripRequest
    verdict: Verdict
    summary: str = ""  # the overall picture in two or three sentences
    verdict_reasons: list[Advice]
    stops: list[Stop]
    return_leg: list[Stop] = Field(default_factory=list)
