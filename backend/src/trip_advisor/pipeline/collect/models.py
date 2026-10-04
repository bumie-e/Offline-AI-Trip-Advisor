from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from trip_advisor.schemas.common import Strict


class DocKind(StrEnum):
    ROUTE_GUIDE = "route_guide"  # how-to-get-there text
    NEWS = "news"
    GOV_NOTICE = "gov_notice"


class RawDocument(Strict):
    """One collected item of text evidence. Facts are extracted later, not republished."""

    id: str
    site_id: str
    kind: DocKind
    source: str  # collector name: google_news, fmino, wikivoyage
    publisher: str
    url: str
    title: str
    published: date | None
    fetched_at: datetime
    text: str = ""
    license: str = ""
    corridor: str = ""
    query: str = ""


class Place(Strict):
    name: str
    lat: float
    lon: float
    matched: str = ""  # what OpenStreetMap resolved the query to, for eyeballing


class RoadSegment(Strict):
    """A stretch of one named road, in kilometres from the start of the route."""

    name: str  # "E1 Lagos-Ibadan Expressway"
    from_km: float
    to_km: float


class RouteOption(Strict):
    id: str  # "primary", "alt-1", or a configured variant id
    kind: Literal["primary", "alternative", "variant"]
    label: str
    distance_km: float
    duration_min: float  # free-flow estimate, no traffic or road condition
    roads: list[str]  # named roads over 3 km, in travel order
    geometry: list[tuple[float, float]]  # (lat, lon), simplified
    segments: list[RoadSegment] = Field(default_factory=list)  # which road, where on the route


class Stop(Strict):
    name: str
    kind: str  # city, town, fuel, hospital, police
    lat: float
    lon: float
    km_from_start: float
    route_id: str


class SiteRoutes(Strict):
    site_id: str
    origin: Place
    destination: Place
    routes: list[RouteOption]
    stops: list[Stop]
    collected_at: datetime


class CorridorEvidence(Strict):
    corridor: str
    selected: RawDocument | None  # newest fresh, relevant item
    others: list[RawDocument] = Field(default_factory=list)  # fresh, older
