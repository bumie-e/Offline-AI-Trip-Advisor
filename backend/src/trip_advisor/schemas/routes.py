"""Routes as the app receives them: what advice cites, without the map geometry.

Stops cite a route by `cite_id` (`route-<site>-<route>`), so the device needs these to show
what a citation points to. Road shapes are left out: the app gives no turn-by-turn navigation
and the shapes would dominate the download.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Strict


class PackRoute(Strict):
    cite_id: str  # the ID that itinerary stops and advice use to cite this route
    id: str  # "primary", "alt-1", or a configured variant id
    kind: Literal["primary", "alternative", "variant"]
    label: str
    distance_km: float
    duration_min: float  # free-flow estimate: no traffic, no road condition
    roads: list[str]  # named roads over 3 km, in travel order


class PackStop(Strict):
    """A town, fuel station, hospital or police station beside a route."""

    name: str
    kind: str  # city, town, fuel, hospital, police
    lat: float
    lon: float
    km_from_start: float
    route_id: str  # the `id` of the route it lies on, not the cite_id


class PackPlace(Strict):
    name: str
    lat: float
    lon: float


class PackRoutes(Strict):
    origin: PackPlace
    destination: PackPlace
    routes: list[PackRoute] = Field(default_factory=list)
    stops: list[PackStop] = Field(default_factory=list)
    collected_at: datetime
