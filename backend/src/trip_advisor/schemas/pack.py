from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from .common import Confidence, Sensitivity, Source, Strict
from .delta import Delta
from .itinerary import Itinerary
from .routes import PackRoutes


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


class ImageRecord(_Record):
    """A photo of the site or of a road on the way. The file itself is fetched from `path`.

    `summary` is the caption. Free licences still require credit, so `credit` is ready to show.
    """

    type: Literal["image"] = "image"
    kind: Literal["site", "road"]
    path: str  # e.g. /images/olumo-rock/img-olumo-rock-ab12cd34ef.jpg
    mime: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    size_bytes: int = Field(ge=1)
    credit: str  # "Photo: <author>, CC BY-SA 4.0, via Wikimedia Commons"
    license: str
    license_url: str | None = None


PackRecord = Annotated[
    RoadNote | SiteFact | CostNote | Contact | ImageRecord,
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
    routes: PackRoutes | None = None  # what the `route-...` citations in the itinerary point to
    advice_source: Literal["model", "rules"]  # who wrote the advice text
