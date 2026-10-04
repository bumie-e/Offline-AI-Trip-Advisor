"""Turn untrusted LLM output into schema-valid pack records, or a recorded rejection."""

import hashlib
import re
from datetime import date
from typing import Any

from pydantic import HttpUrl, TypeAdapter, ValidationError

from trip_advisor.pipeline.collect.models import RawDocument
from trip_advisor.schemas.common import Confidence, Sensitivity, Source
from trip_advisor.schemas.pack import CostNote, PackRecord, RoadNote, SiteFact

from .models import Extracted, Reason, Rejected

_URL = TypeAdapter(HttpUrl)


def _squash(text: str) -> str:
    return (
        re.sub(r"\s+", " ", text.replace("’", "'").replace("“", '"').replace("”", '"'))
        .strip()
        .lower()
    )


# The model sometimes "extracts" a remark about the document instead of a fact from it.
_META = re.compile(
    r"^(the|this) (document|text|article|passage|page|guide|source)\b"
    r"|\b(does not|doesn't|did not|no) (contain|mention|provide|include|specific information)"
    r"|\bnot (mentioned|specified|available)\b",
    re.IGNORECASE,
)


def normalize_route(name: str) -> str:
    """One spelling per road: ASCII hyphens, tidy spacing, Title Case, no '(detail)' suffix."""
    name = re.sub(r"[\u2010-\u2015\u2212]", "-", name)  # en/em dashes and minus signs
    name = re.sub(r"\([^)]*\)", " ", name)  # "(Kara Bridge)" is detail, not the road
    name = re.sub(r"\s*-\s*", "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return re.sub(r"(^|[\s-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), name)


def quote_in_source(quote: str, text: str) -> bool:
    return _squash(quote) in _squash(text)


def _amounts_in(quote: str) -> set[int]:
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", quote) if n.replace(",", "")}


def record_id(kind: str, site_id: str, doc_id: str, summary: str) -> str:
    digest = hashlib.sha1(f"{doc_id}|{_squash(summary)}".encode()).hexdigest()[:10]
    return f"{kind.replace('_', '-')}-{site_id}-{digest}"


def build_record(
    raw: dict[str, Any], doc: RawDocument, today: date
) -> tuple[PackRecord, Extracted] | Rejected:
    def reject(reason: Reason, detail: str = "") -> Rejected:
        return Rejected(doc_id=doc.id, reason=reason, detail=detail, raw=raw)

    try:
        item = Extracted.model_validate(raw)
    except ValidationError as exc:
        return reject(Reason.MALFORMED, str(exc.errors()[0]["msg"]) + str(exc.errors()[0]["loc"]))
    if _META.search(item.summary):
        return reject(Reason.NO_CONTENT, item.summary[:80])
    if not quote_in_source(item.quote, doc.text):
        return reject(Reason.QUOTE_NOT_IN_SOURCE)

    try:
        source = Source(
            publisher=doc.publisher, url=_URL.validate_python(doc.url), published=doc.published
        )
    except ValidationError:
        return reject(Reason.MALFORMED, f"bad source url {doc.url!r}")
    common: dict[str, Any] = {
        "id": record_id(item.type, doc.site_id, doc.id, item.summary),
        "summary": item.summary,
        "source": source,
        "confidence": item.confidence,
        "last_verified": today,
    }
    record: PackRecord
    if item.type == "road_note":
        if not item.route:
            return reject(Reason.MISSING_FIELD, "route")
        # Missing sensitivity is a model omission, not a reason to drop real evidence. Store the
        # middle value; the caller caps confidence and flags it.
        record = RoadNote.model_validate(
            {
                **common,
                "route": normalize_route(item.route),
                "rain_sensitivity": item.rain_sensitivity or Sensitivity.MEDIUM,
            }
        )
    elif item.type == "site_fact":
        if not item.topic:
            return reject(Reason.MISSING_FIELD, "topic")
        record = SiteFact.model_validate({**common, "topic": item.topic})
    else:
        if not item.item:
            return reject(Reason.MISSING_FIELD, "item")
        amounts = [a for a in (item.amount_ngn_min, item.amount_ngn_max) if a is not None]
        if not amounts:
            return reject(Reason.MISSING_FIELD, "amount")
        if not set(amounts) <= _amounts_in(item.quote):
            return reject(Reason.AMOUNT_NOT_IN_QUOTE, str(amounts))
        record = CostNote.model_validate(
            {
                **common,
                "item": item.item,
                "amount_ngn_min": item.amount_ngn_min,
                "amount_ngn_max": item.amount_ngn_max,
            }
        )
    return record, item


def cap_confidence(record: PackRecord, ceiling: Confidence) -> PackRecord:
    order = [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]
    if order.index(record.confidence) <= order.index(ceiling):
        return record
    return record.model_copy(update={"confidence": ceiling})
