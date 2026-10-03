from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from .common import Strict


class RoadCondition(StrEnum):
    CLEAR = "clear"
    SLOW = "slow"
    DIFFICULT = "difficult"
    IMPASSABLE = "impassable"


class SiteStatus(StrEnum):
    OPEN = "open"
    LIMITED = "limited"
    CLOSED = "closed"


class _Report(Strict):
    # Queued offline, so the client generates the id and timestamp.
    # No user identity. Location is coarse (rounded) to limit personal data.
    id: UUID
    reported_at: datetime
    site_id: str
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    note: str = Field(default="", max_length=500)


class RoadReport(_Report):
    route_id: str
    condition: RoadCondition


class SiteStatusReport(_Report):
    status: SiteStatus


class AdviceRating(Strict):
    id: UUID
    rated_at: datetime
    site_id: str
    helpful: bool
    comment: str = Field(default="", max_length=500)
