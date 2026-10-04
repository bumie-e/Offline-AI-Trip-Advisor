from datetime import UTC, date, datetime

import httpx

from trip_advisor.guardrails.checks import ViolationKind
from trip_advisor.pack.delta_builder import collect_event_docs, trip_places
from trip_advisor.pipeline.collect import store
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import RawDocument
from trip_advisor.pipeline.context.events import classify
from trip_advisor.pipeline.generate.evidence import route_id
from trip_advisor.pipeline.generate.rules import assess
from trip_advisor.pipeline.generate.run import merge
from trip_advisor.pipeline.generate.writer import StopNote, WriterOutput
from trip_advisor.schemas.delta import Delta, DisruptionEvent, EventStatus, EventType
from trip_advisor.schemas.itinerary import Advice, Severity, Verdict

from .test_generate import NOW, inp, routes
from .test_route_towns import stop

TRIP_PLACES = ["Abeokuta", "Olumo Rock", "Sagamu"]  # city, site, a town on the route


def doc(title: str, text: str = "") -> RawDocument:
    return RawDocument(
        id="d1", site_id="s", kind="news", source="google_news", publisher="Punch",
        url="https://news.example/story", title=title, published=date(2026, 10, 1),
        fetched_at=datetime(2026, 10, 3, tzinfo=UTC), text=text,
    )  # fmt: skip


def test_edible_oil_tanker_strike_is_not_a_fuel_or_general_strike():
    d = doc("Edible oil tanker drivers threaten nationwide strike, allege NUPENG interference")
    assert classify(d, TRIP_PLACES, "Abeokuta", "Ogun") is None


def test_real_fuel_tanker_strike_still_counts():
    ev = classify(doc("NUPENG begins nationwide strike, tanker drivers park"), TRIP_PLACES,
                  "Abeokuta", "Ogun")  # fmt: skip
    assert ev and ev.affects == ["fuel"]


def test_general_union_strike_still_counts_everywhere():
    ev = classify(doc("Nigerian workers commence nationwide strike today"), TRIP_PLACES,
                  "Abeokuta", "Ogun")  # fmt: skip
    assert ev and ev.type == EventType.STRIKE and ev.affects == ["flights", "roads"]


def test_flood_commentary_that_only_names_the_state_is_ignored():
    d = doc("Deforestation, waste dumping worsening flooding, says Ogun-Osun basin boss")
    assert classify(d, TRIP_PLACES, "Abeokuta", "Ogun") is None


def test_flood_in_a_town_on_the_route_counts():
    ev = classify(doc("Flood cuts off Sagamu, motorists stranded"), TRIP_PLACES, "Abeokuta", "Ogun")
    assert ev and ev.type == EventType.HEAVY_RAIN


def test_events_carry_their_source_for_auditing():
    ev = classify(doc("Flood hits Abeokuta, roads cut"), TRIP_PLACES, "Abeokuta", "Ogun")
    assert ev and ev.source is not None
    assert (ev.source.publisher, str(ev.source.url), ev.source.published) == (
        "Punch", "https://news.example/story", date(2026, 10, 1),
    )  # fmt: skip


def test_old_deltas_without_a_source_still_load():
    old = '{"generated_at": "2026-10-03T08:00:00Z", "events": [{"type": "strike", ' \
          '"status": "threatened", "affects": ["flights"], "source_id": "news-1"}]}'  # fmt: skip
    assert Delta.model_validate_json(old).events[0].source is None


def test_trip_places_are_the_destination_and_route_towns_not_the_state(tmp_path):
    from trip_advisor.sites import Endpoint, SiteConfig

    site = SiteConfig(
        id="olumo-rock", name="Olumo Rock", city="Abeokuta", state="Ogun",
        origin=Endpoint(query="a"), destination=Endpoint(query="b"), corridors=[],
    )  # fmt: skip
    assert trip_places(site, tmp_path) == ["Abeokuta", "Olumo Rock"]  # no routes saved yet

    r = routes()
    r.stops[:] = [stop("Sagamu", 54, "city", "primary"), stop("Total", 60, "fuel", "primary")]
    store.save(r, tmp_path / "olumo-rock" / "routes.json")
    places = trip_places(site, tmp_path)
    assert places == ["Abeokuta", "Olumo Rock", "Sagamu"] and "Ogun" not in places


def test_local_flood_queries_cover_route_towns():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, text="<rss><channel></channel></rss>")

    from trip_advisor.sites import Endpoint, SiteConfig

    site = SiteConfig(
        id="olumo-rock", name="Olumo Rock", city="Abeokuta", state="Ogun",
        origin=Endpoint(query="a"), destination=Endpoint(query="b"), corridors=[],
    )  # fmt: skip
    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), intervals={})
    collect_event_docs(site, fetcher, NOW, [], ["Abeokuta", "Olumo Rock", "Sagamu"])
    joined = " | ".join(seen)
    assert "Abeokuta flood" in joined and "Sagamu flood" in joined and "Ogun" not in joined


def written_with(note: StopNote) -> WriterOutput:
    return WriterOutput(
        verdict=Verdict.GO_WITH_CHANGES,
        verdict_reasons=[Advice(changed=True, severity=Severity.ELEVATED,
                                advice="Reports suggest rain may slow the drive.",
                                cited_ids=["weather-2026-10-14"])],
        stop_notes=[note],
    )  # fmt: skip


def test_uncited_stop_note_is_dropped_and_reported():
    i = inp(weather=[])
    from .test_generate import rain

    i = inp(weather=[rain(0.9)])
    seen: list = []
    _, notes = merge(i, assess(i), written_with(StopNote(order=1, note="Leave before 7am.")), seen)
    assert notes == []
    assert any(v.kind == ViolationKind.UNCITED and v.where == "stop 1" for v in seen)


def test_cited_stop_note_is_kept():
    i = inp()
    rid = route_id("olumo-rock", routes().routes[0])
    note = StopNote(order=1, note="Leave before 7am.", cited_ids=[rid])
    _, notes = merge(i, assess(i), written_with(note), [])
    assert notes == [note]


def test_stop_note_citing_an_unknown_id_is_dropped():
    note = StopNote(order=1, note="Leave before 7am.", cited_ids=["made-up-id"])
    seen: list = []
    _, notes = merge(inp(), assess(inp()), written_with(note), seen)
    assert notes == [] and any(v.kind == ViolationKind.UNKNOWN_ID for v in seen)


def test_source_adds_event_text_for_the_writer_and_catalog():
    ev = classify(doc("Flood hits Abeokuta, roads cut"), TRIP_PLACES, "Abeokuta", "Ogun")
    assert ev
    i = inp(events=[ev])
    assert "Source: Punch, 2026-10-01" in i.render()
    fact = i.catalog().facts[ev.source_id]
    assert fact.publisher == "Punch" and fact.as_of == date(2026, 10, 1)


def test_event_without_source_falls_back_to_generic_label():
    ev = DisruptionEvent(type=EventType.STRIKE, status=EventStatus.THREATENED,
                         affects=["flights"], source_id="news-1")  # fmt: skip
    fact = inp(events=[ev]).catalog().facts["news-1"]
    assert fact.publisher == "News reports" and fact.as_of is None


def test_short_town_names_match_whole_words_only():
    # "Ore" is a real town on the Idanre route, but also sits inside "more" and "before".
    places = ["Idanre", "Idanre Hill", "Ore"]
    iowa = doc("Heavy rain brings more flooding to Iowa, with more to come before the weekend")
    assert classify(iowa, places, "Idanre", "Ondo") is None
    real = doc("Flood cuts the expressway at Ore, motorists stranded")
    ev = classify(real, places, "Idanre", "Ondo")
    assert ev and ev.type == EventType.HEAVY_RAIN
