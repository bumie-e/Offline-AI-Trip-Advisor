"""The plain-text overall summary, used when the model's summary is missing or fails a check."""

from trip_advisor.schemas.itinerary import Advice, Severity, Verdict

from .evidence import GenInput

_PHRASE = {
    Verdict.GO: "No issues flagged",
    Verdict.GO_WITH_CHANGES: "Go, with changes",
    Verdict.NOT_ADVISED: "Not advised",
}


def _dates(inp: GenInput) -> str:
    a, b = inp.request.start_date, inp.request.end_date
    return f"{a:%d %b}" if a == b else f"{a:%d %b} to {b:%d %b}"


def template_summary(inp: GenInput, verdict: Verdict, reasons: list[Advice]) -> str:
    head = f"{_PHRASE[verdict]} for {inp.site.name} on {_dates(inp)}."
    live = [r for r in reasons if r.severity != Severity.NONE]
    if not live:
        return f"{head} The stored weather and news show nothing to change; confirm conditions locally."
    first = live[0].advice.split(". ")[0].rstrip(".")
    more = f" and {len(live) - 1} more" if len(live) > 1 else ""
    return f"{head} {len(live)} thing{'s' if len(live) > 1 else ''} to watch, starting with: {first}{more and ' (' + more.strip() + ')'}."
