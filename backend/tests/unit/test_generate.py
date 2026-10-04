from datetime import UTC, date, datetime

import pytest

from trip_advisor.pipeline.collect.models import Place, RouteOption, SiteRoutes
from trip_advisor.pipeline.collect.models import Stop as MapStop
from trip_advisor.pipeline.generate.evidence import GenInput
from trip_advisor.pipeline.generate.rules import assess
from trip_advisor.pipeline.generate.run import generate_itinerary, merge
from trip_advisor.pipeline.generate.writer import StopNote, WriterOutput
from trip_advisor.schemas.common import Confidence, Sensitivity, Source
from trip_advisor.schemas.delta import (
    Delta,
    DisruptionEvent,
    EventStatus,
    EventType,
    WeatherEntry,
)
from trip_advisor.schemas.itinerary import Advice, Itinerary, Severity, TripRequest, Verdict
from trip_advisor.schemas.pack import RoadNote, SiteFact
from trip_advisor.sites import Endpoint, SiteConfig

NOW = datetime(2026, 10, 3, 9, tzinfo=UTC)
TRIP = date(2026, 10, 14)
SRC = Source(publisher="Punch", url="https://example.com/a", published=date(2026, 9, 20))


def note(sens=Sensitivity.HIGH, conf=Confidence.MEDIUM, id="road-note-1") -> RoadNote:
    return RoadNote(
        id=id, summary="Repairs under way, flooding reported.", source=SRC, confidence=conf,
        last_verified=date(2026, 10, 1), route="Lagos-Abeokuta Expressway", rain_sensitivity=sens,
    )  # fmt: skip


def rain(p: float, day=TRIP) -> WeatherEntry:
    return WeatherEntry(date=day, area="Abeokuta", rain_probability=p)


def routes() -> SiteRoutes:
    primary = RouteOption(
        id="primary", kind="primary", label="Lagos to Olumo Rock", distance_km=100, duration_min=105,
        roads=["Lagos-Abeokuta Expressway"], geometry=[(6.5, 3.3)],
    )  # fmt: skip
    alt = primary.model_copy(update={"id": "alt-1", "kind": "alternative", "label": "via Sagamu"})
    return SiteRoutes(
        site_id="olumo-rock",
        origin=Place(name="Murtala Muhammed Airport, Ikeja", lat=6.5, lon=3.3),
        destination=Place(name="Olumo Rock", lat=7.1, lon=3.3),
        routes=[primary, alt],
        stops=[MapStop(name="Total Sagamu", kind="fuel", lat=6.8, lon=3.6, km_from_start=60,
                       route_id="primary")],
        collected_at=NOW,
    )  # fmt: skip


def inp(records=None, weather=None, events=None, **req) -> GenInput:
    site = SiteConfig(
        id="olumo-rock", name="Olumo Rock", city="Abeokuta", state="Ogun",
        origin=Endpoint(query="a"), destination=Endpoint(query="b"), corridors=[],
    )  # fmt: skip
    request = TripRequest(
        site_id="olumo-rock", start_city="Lagos", arrival_airport="LOS", start_date=TRIP,
        end_date=TRIP, group_size=2,
    ).model_copy(update=req)  # fmt: skip
    return GenInput(
        site=site, request=request, routes=routes(), records=records or [],
        delta=Delta(generated_at=NOW, weather=weather or [], events=events or []),
        today=date(2026, 10, 3),
    )  # fmt: skip


def event(type_=EventType.STRIKE, status=EventStatus.CONFIRMED, affects=("roads",), **kw):
    return DisruptionEvent(
        type=type_, status=status, affects=list(affects), source_id="news-1", **kw
    )


def test_heavy_rain_on_sensitive_road_is_not_advised_and_cites_both():
    a = assess(inp([note()], [rain(0.85)]))
    assert a.verdict == Verdict.NOT_ADVISED
    assert set(a.advice[0].cited_ids) == {"weather-2026-10-14", "road-note-1"}


def test_heavy_rain_without_sensitive_note_is_go_with_changes():
    assert assess(inp([note(Sensitivity.LOW)], [rain(0.9)])).verdict == Verdict.GO_WITH_CHANGES


def test_moderate_rain_only_matters_on_a_high_sensitivity_road():
    assert assess(inp([note(Sensitivity.HIGH)], [rain(0.55)])).verdict == Verdict.GO_WITH_CHANGES
    assert assess(inp([note(Sensitivity.MEDIUM)], [rain(0.55)])).verdict == Verdict.GO


def test_rain_outside_trip_days_ignored():
    assert assess(inp([note()], [rain(0.95, day=date(2026, 10, 20))])).verdict == Verdict.GO


def test_flight_event_ignored_without_airport_but_counts_with_one():
    ev = event(EventType.FLIGHT_SUSPENSION, affects=("flights",))
    assert assess(inp([note()], [rain(0.1)], [ev], arrival_airport=None)).verdict == Verdict.GO
    assert assess(inp([note()], [rain(0.1)], [ev])).verdict == Verdict.GO_WITH_CHANGES


def test_ended_and_non_overlapping_events_ignored():
    ended = event(status=EventStatus.ENDED)
    later = event(start=date(2026, 11, 1))
    assert assess(inp([note()], [rain(0.1)], [ended, later])).verdict == Verdict.GO


def test_thin_evidence_and_missing_forecast_are_noted_but_do_not_change_verdict():
    a = assess(inp([note(conf=Confidence.LOW)], []))
    assert a.verdict == Verdict.GO
    assert len(a.advice) == 2 and all(x.severity == Severity.NONE for x in a.advice)


def test_advice_never_uses_safe_unsafe_language():
    a = assess(inp([note()], [rain(0.9)], [event()]))
    text = " ".join(x.advice.lower() for x in a.advice)
    assert "unsafe" not in text and " safe" not in text


def test_skeleton_has_outbound_fuel_visit_and_return():
    facts = SiteFact(
        id="fact-1", summary="Entry fee is reported at N2,500.", source=SRC,
        confidence=Confidence.MEDIUM, last_verified=date(2026, 10, 1), topic="entry_fee",
    )  # fmt: skip
    it = generate_itinerary(inp([note(), facts], [rain(0.1)]), now=NOW)
    assert [s.order for s in it.stops] == [1, 2, 3]
    assert it.stops[0].title == "Leave Murtala Muhammed Airport"
    assert it.stops[1].title.startswith("Fuel and rest")
    assert it.stops[2].cited_ids == ["fact-1"]
    assert [s.order for s in it.return_leg] == [1, 2]
    Itinerary.model_validate_json(it.model_dump_json())


def test_missing_routes_still_produces_a_visit_stop():
    i = inp([note()], [rain(0.1)])
    i.routes = None
    it = generate_itinerary(i, now=NOW)
    assert [s.title for s in it.stops] == ["Visit Olumo Rock"] and i.notes


class FakeWriter:
    def __init__(self, out: WriterOutput | None) -> None:
        self.out = out

    def write(self, inp, findings, outline):
        return self.out


def written(verdict, severity, cited, text="Reports suggest rain may slow the drive."):
    return WriterOutput(
        verdict=verdict,
        verdict_reasons=[Advice(changed=True, severity=severity, advice=text, cited_ids=cited)],
        stop_notes=[StopNote(order=1, note="Leave before 7am.")],
    )


def test_model_prose_used_when_valid_and_not_weaker_than_rules():
    out = written(Verdict.NOT_ADVISED, Severity.HIGH, ["weather-2026-10-14"])
    it = generate_itinerary(inp([note()], [rain(0.9)]), FakeWriter(out), now=NOW)
    assert it.verdict_reasons[0].advice.startswith("Reports suggest rain")
    assert it.stops[0].notes.endswith("Leave before 7am.")


def test_model_cannot_relax_the_verdict():
    out = written(Verdict.GO, Severity.NONE, ["weather-2026-10-14"])
    it = generate_itinerary(inp([note()], [rain(0.9)]), FakeWriter(out), now=NOW)
    assert it.verdict == Verdict.NOT_ADVISED
    assert it.verdict_reasons[0].severity == Severity.HIGH  # rule text replaced the weak reasons


def test_model_citing_unknown_id_falls_back_to_rule_text():
    out = written(Verdict.NOT_ADVISED, Severity.HIGH, ["road-note-999"])
    i = inp([note()], [rain(0.9)])
    reasons, _ = merge(i, assess(i), out)
    assert reasons == assess(i).advice


def test_model_can_be_more_cautious_than_rules():
    out = written(Verdict.NOT_ADVISED, Severity.HIGH, ["road-note-1"])
    it = generate_itinerary(inp([note()], [rain(0.1)]), FakeWriter(out), now=NOW)
    assert it.verdict == Verdict.NOT_ADVISED


def test_writer_returning_nothing_falls_back_to_rules():
    it = generate_itinerary(inp([note()], [rain(0.9)]), FakeWriter(None), now=NOW)
    assert it.verdict == Verdict.NOT_ADVISED


@pytest.mark.parametrize("n", [0, 1])
def test_trip_days_inclusive(n):
    from datetime import timedelta

    i = inp(end_date=TRIP + timedelta(days=n))
    assert len(i.trip_days) == n + 1


def test_low_confidence_note_cannot_force_not_advised():
    a = assess(inp([note(conf=Confidence.LOW)], [rain(0.95)]))
    assert a.verdict == Verdict.GO_WITH_CHANGES
    assert "low-confidence" in a.advice[0].advice


def test_anthropic_writer_parses_tool_output_and_does_not_force_tool_choice():
    from types import SimpleNamespace

    from trip_advisor.pipeline.generate.writer import TOOL_NAME, AnthropicWriter

    seen = {}
    payload = written(
        Verdict.GO_WITH_CHANGES, Severity.ELEVATED, ["weather-2026-10-14"]
    ).model_dump(mode="json")

    def create(**kw):
        seen.update(kw)
        block = SimpleNamespace(type="tool_use", name=TOOL_NAME, input=payload)
        return SimpleNamespace(content=[SimpleNamespace(type="text"), block])

    writer = AnthropicWriter("key")
    writer._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    i = inp([note()], [rain(0.9)])
    out = writer.write(i, assess(i), "outline")
    assert out and out.verdict == Verdict.GO_WITH_CHANGES
    assert seen["tool_choice"] == {"type": "auto"}  # newer models reject a forced tool
    assert "weather-2026-10-14" in seen["messages"][0]["content"]
