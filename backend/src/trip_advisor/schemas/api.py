"""Response shapes that belong to the API rather than to the pack, delta or itinerary."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from .common import Strict


class PlaceSummary(Strict):
    id: str
    name: str
    city: str
    state: str
    pack_version: str | None = None  # None until a pack has been built
    pack_bytes: int | None = None
    pack_generated_at: datetime | None = None


class Rejection(Strict):
    id: UUID
    reason: str


class Receipt(Strict):
    """Result of syncing a batch of queued reports. Safe to retry: ids are idempotent."""

    accepted: list[UUID] = Field(default_factory=list)
    duplicates: list[UUID] = Field(default_factory=list)  # already stored, nothing to retry
    rejected: list[Rejection] = Field(default_factory=list)  # will never be accepted as sent
