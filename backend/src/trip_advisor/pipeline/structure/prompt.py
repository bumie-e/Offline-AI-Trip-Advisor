from anthropic.types import ToolParam

from trip_advisor.pipeline.collect.models import DocKind, RawDocument

from .models import ExtractionResult

TOOL_NAME = "record_facts"

SYSTEM = """You extract structured travel facts about a Nigerian heritage site from one source \
document. You are not a writer: you copy facts, you do not add any.

Rules:
- Use ONLY what the document says. If it says nothing useful, return an empty list.
- Every record needs a `quote`: a verbatim span copied from the document that supports it.
- `summary` is one short factual sentence in your own words. Use advisory wording such as \
"reports suggest". Never say a road or place is safe or unsafe.
- Record types:
  - road_note: the condition of a road or route (repairs, closures, flooding, potholes, diversions). \
Always set both `route` (e.g. "Lagos-Abeokuta Expressway") and `rain_sensitivity` \
(low/medium/high): high if the text links the problem to rain, flooding or erosion; low if it \
describes dry-weather problems such as traffic or repairs only; medium if it does not say.
  - site_fact: opening hours, entry fees, history, what to see, facilities. Set `topic`.
  - cost_note: a price. Set `item` and amounts in naira. Amounts must appear in the quote.
- `confidence`: high only for explicit, specific statements by an official or primary source; \
medium for clear news reports; low for vague, old, second-hand or headline-only statements.
- Do not extract phone numbers, names of private people, or opinions.
- Ignore anything that is not about the site or the roads leading to it."""


def user_message(doc: RawDocument, site_name: str) -> str:
    kind = {
        DocKind.ROUTE_GUIDE: "travel guide",
        DocKind.NEWS: "news item",
        DocKind.GOV_NOTICE: "government notice",
    }[doc.kind]
    return (
        f"Site: {site_name}\nDocument type: {kind}\nPublisher: {doc.publisher}\n"
        f"Published: {doc.published or 'unknown'}\nTitle: {doc.title}\n\n"
        f"<document>\n{doc.text}\n</document>"
    )


def tool_definition() -> ToolParam:
    return {
        "name": TOOL_NAME,
        "description": "Record the facts found in the document.",
        "input_schema": ExtractionResult.model_json_schema(),
    }
