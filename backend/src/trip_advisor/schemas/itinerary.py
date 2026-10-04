from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Confidence, Strict


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


class StopImage(Strict):
    """The one photo shown for a stop. The file is fetched from `path`."""

    id: str
    path: str  # e.g. /images/olumo-rock/img-olumo-rock-ab12cd34ef.jpg
    caption: str
    credit: str  # ready to show: author, licence, source
    license: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    # False when the caption does not name this place or road: it is an example of a road in the
    # area, and the app should label it that way instead of presenting it as this exact spot.
    shows_this_stop: bool = True


class StopRoad(Strict):
    """What a traveller sees on tapping a stop: the nature of the road there."""

    name: str | None = None  # the road at this point, e.g. "E1 Lagos-Ibadan Expressway"
    km_from_start: float | None = None
    km_since_previous_stop: float | None = None
    condition: str = ""  # one advisory sentence, or that there is no recent report
    has_recent_report: bool = False
    # How the report applies to this stop. "here": it names this place. "road": it is about this
    # road. "corridor": it is about a wider road that passes this stop, so it is not
    # necessarily true at this exact spot, and the app should word it that way.
    scope: Literal["here", "road", "corridor"] | None = None
    confidence: Confidence | None = None  # of the report behind `condition`
    report_age_days: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class Stop(Strict):
    order: int = Field(ge=1)
    title: str
    mode: TravelMode | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    notes: str = ""  # facts from the data: distance, hours, fuel
    cited_ids: list[str] = Field(default_factory=list)
    # What the stop screen shows. All optional, so older itineraries still load.
    comment: str = ""  # one line for the list of stops
    image: StopImage | None = None
    road: StopRoad | None = None
    advice: str = ""  # the model's advice for this stop, only ever backed by cited evidence


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
