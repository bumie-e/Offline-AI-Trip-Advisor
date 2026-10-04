from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from .common import Confidence, Sensitivity, Source, Strict
from .delta import Delta
from .itinerary import Itinerary


class _Record(Strict):
    id: str
    summary: str
    source: Source
    confidence: Confidence
    last_verified: date


class RoadNote(_Record):
    type: Literal["road_note"] = "road_note"
    route: str
    rain_sensitivity: Sensitivity


class SiteFact(_Record):
    type: Literal["site_fact"] = "site_fact"
    topic: str  # e.g. "opening_hours", "entry_fee", "history"


class CostNote(_Record):
    type: Literal["cost_note"] = "cost_note"
    item: str
    amount_ngn_min: int | None = None
    amount_ngn_max: int | None = None


class Contact(_Record):
    type: Literal["contact"] = "contact"
    role: str  # "guide", "driver", ...
    name: str
    phone: str | None = None
    is_sample: bool = True  # samples until real contacts are secured


PackRecord = Annotated[
    RoadNote | SiteFact | CostNote | Contact,
    Field(discriminator="type"),
]


class Pack(Strict):
    """Downloaded once on Wi-Fi. Changes rarely."""

    site_id: str
    version: str
    generated_at: datetime
    records: list[PackRecord]


class TripPack(Strict):
    """What a traveller downloads for a planned trip: the pack plus the advice already written.

    The itinerary was generated from the pack, the weather and the news in `delta`. The device
    keeps all three so it can compare a later delta against the one the advice was based on.
    """

    pack: Pack
    delta: Delta  # the weather and news the advice was based on
    itinerary: Itinerary  # verdict, summary, reasons and stops
    advice_source: Literal["model", "rules"]  # who wrote the advice text
