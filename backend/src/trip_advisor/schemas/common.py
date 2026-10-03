from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl


class Strict(BaseModel):
    """Base for all contract models: unknown fields are errors."""

    model_config = ConfigDict(extra="forbid")


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Sensitivity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Source(Strict):
    publisher: str
    url: HttpUrl
    published: date | None = None
