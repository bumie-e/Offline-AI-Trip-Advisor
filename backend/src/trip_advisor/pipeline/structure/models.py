from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field

from trip_advisor.schemas.common import Confidence, Sensitivity, Strict
from trip_advisor.schemas.pack import PackRecord


class Extracted(Strict):
    """One record as the LLM proposes it. Untrusted until validated."""

    type: Literal["road_note", "site_fact", "cost_note"]
    summary: str = Field(min_length=10, max_length=400)
    quote: str = Field(min_length=10)  # verbatim span from the source text that supports it
    confidence: Confidence
    route: str | None = None  # road_note
    rain_sensitivity: Sensitivity | None = None  # road_note
    topic: str | None = None  # site_fact, e.g. opening_hours, entry_fee, history
    item: str | None = None  # cost_note
    amount_ngn_min: int | None = Field(default=None, ge=0)
    amount_ngn_max: int | None = Field(default=None, ge=0)


class ExtractionResult(Strict):
    records: list[Extracted]


class Reason(StrEnum):
    MALFORMED = "malformed"
    QUOTE_NOT_IN_SOURCE = "quote_not_in_source"
    AMOUNT_NOT_IN_QUOTE = "amount_not_in_quote"
    MISSING_FIELD = "missing_field"
    NO_CONTENT = "no_content"  # a statement about the document, not a fact from it
    DUPLICATE = "duplicate"
    EXTRACTOR_ERROR = "extractor_error"


class Rejected(Strict):
    doc_id: str
    reason: Reason
    detail: str = ""
    raw: dict[str, object] | None = None


class FlagKind(StrEnum):
    STALE = "stale"  # road evidence older than the recency window
    UNDATED = "undated"
    LOW_CONFIDENCE = "low_confidence"
    ASSUMED_SENSITIVITY = (
        "assumed_sensitivity"  # text did not say; stored as medium, low confidence
    )
    GUIDE_CAPPED = "guide_capped"  # crowd-sourced guide, confidence capped at medium
    HEADLINE_ONLY = "headline_only"  # source text was only a headline, so confidence is capped


class Flag(Strict):
    record_id: str
    kind: FlagKind
    detail: str = ""


class StructuredSite(Strict):
    site_id: str
    structured_on: date
    records: list[PackRecord]
    flags: list[Flag]
    rejected: list[Rejected]
    docs_processed: int
