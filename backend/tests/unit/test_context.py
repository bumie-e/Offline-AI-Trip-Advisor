from datetime import UTC, date, datetime

import httpx
import pytest

from trip_advisor.pack.delta_builder import MAX_DELTA_BYTES, DeltaTooLarge, build_delta
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import DocKind, RawDocument
from trip_advisor.pipeline.context.events import build_events, classify
from trip_advisor.pipeline.context.weather import clamp_range, parse_forecast
from trip_advisor.schemas.delta import Delta, EventStatus, EventType
from trip_advisor.sites import Endpoint, SiteConfig

TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
PLACES = ["Abeokuta", "Olumo Rock", "Ogun"]


def doc(title, id="d1", published=date(2026, 10, 1), text="") -> RawDocument:
    return RawDocument(
        id=id, site_id="olumo-rock", kind=DocKind.NEWS, source="google_news", publisher="P",
        url=f"https://e.com/{id}", title=title, published=published, fetched_at=NOW, text=text,
    )  # fmt: skip


def test_parse_forecast_converts_percent_and_skips_nulls():
    data = {"daily": {"time": ["2026-10-04", "2026-10-05", "2026-10-06"],
                      "precipitation_probability_max": [80, 0, None]}}  # fmt: skip
    got = parse_forecast(data, "Abeokuta")
    assert [(w.date.isoformat(), w.rain_probability) for w in got] == [
        ("2026-10-04", 0.8), ("2026-10-05", 0.0),
    ]  # fmt: skip


def test_clamp_range_limits_to_16_days():
    assert clamp_range(date(2026, 9, 1), date(2026, 12, 1), TODAY) == (TODAY, date(2026, 10, 18))
    start, end = clamp_range(date(2026, 12, 1), date(2026, 12, 5), TODAY)
    assert start > end


@pytest.mark.parametrize(
    ("title", "kind", "status", "affects"),
    [
        ("Air Peace suspends Lagos-Abuja flights", EventType.FLIGHT_SUSPENSION,
         EventStatus.CONFIRMED, ["flights"]),
        ("Aviation unions threaten strike at airports", EventType.STRIKE,
         EventStatus.THREATENED, ["flights"]),
        ("NUPENG begins nationwide strike, tanker drivers park", EventType.STRIKE,
         EventStatus.CONFIRMED, ["fuel"]),
        ("NLC calls off nationwide strike", EventType.STRIKE, EventStatus.ENDED,
         ["flights", "roads"]),
        ("Ogun teachers begin indefinite strike", EventType.STRIKE,
         EventStatus.CONFIRMED, ["state:ogun"]),
        ("Health workers threaten nationwide strike", EventType.STRIKE,
         EventStatus.THREATENED, ["flights", "roads"]),
        ("Workers begin 3-day warning strike nationwide", EventType.STRIKE,
         EventStatus.CONFIRMED, ["flights", "roads"]),
        ("Workers threaten nationwide strike if petrol price stays", EventType.STRIKE,
         EventStatus.THREATENED, ["flights", "roads"]),
        ("Unions ground Air Peace flights in Lagos, Abuja", EventType.FLIGHT_SUSPENSION,
         EventStatus.CONFIRMED, ["flights"]),
        ("Flood hits Abeokuta, roads cut", EventType.HEAVY_RAIN, EventStatus.THREATENED,
         ["road:abeokuta"]),
    ],
)  # fmt: skip
def test_classify(title, kind, status, affects):
    ev = classify(doc(title), PLACES, "Abeokuta", "Ogun")
    assert ev and (ev.type, ev.status, ev.affects) == (kind, status, affects)
    assert ev.source_id == "news-d1"


@pytest.mark.parametrize(
    "title",
    [
        "Governor opens new market",
        "Flood hits Kano",
        "NLC declares indefinite strike in Delta over death in secretariat",
        "Ondo unions threaten strike at teaching hospital",
        "Teachers begin strike over promotion",
        "Air Peace suspends Benin flights over runway closure",
        "Lecturers extended their holiday",
    ],
)
def test_irrelevant_or_local_items_ignored(title):
    assert classify(doc(title), PLACES, "Abeokuta", "Ogun") is None


def test_extended_is_not_ended():
    ev = classify(doc("Nationwide strike extended by labour"), PLACES, "Abeokuta", "Ogun")
    assert ev and ev.status != EventStatus.ENDED


def test_build_events_drops_old_dedupes_and_puts_ended_last():
    docs = [
        doc("NLC calls off nationwide strike", "a"),
        doc("Workers threaten nationwide strike", "e", published=date(2026, 9, 25)),
        doc("NUPENG begins nationwide strike", "b", published=date(2026, 9, 30)),
        doc("NUPENG begins nationwide strike", "b", published=date(2026, 9, 30)),
        doc("Nationwide strike begins", "c", published=date(2026, 8, 1)),
        doc("Airline suspends Lagos flights", "d", published=date(2026, 10, 2)),
    ]
    events = build_events(docs, place_terms=PLACES, area="Abeokuta", today=TODAY)
    # One per story: the older "threaten" item is superseded by the newer "calls off".
    assert [e.source_id for e in events] == ["news-d", "news-b", "news-a"]
    assert events[-1].status == EventStatus.ENDED


SITE = SiteConfig(
    id="olumo-rock", name="Olumo Rock", city="Abeokuta", state="Ogun",
    origin=Endpoint(query="a"), destination=Endpoint(query="b", lat=7.16, lon=3.34), corridors=[],
)  # fmt: skip

WEATHER = {"daily": {"time": ["2026-10-04"], "precipitation_probability_max": [90]}}
RSS = """<rss><channel><item><title>Nationwide strike begins - Punch</title>
<link>https://news.example/1</link><pubDate>Thu, 01 Oct 2026 08:00:00 GMT</pubDate>
<source>Punch</source></item></channel></rss>"""


def fetcher(handler) -> Fetcher:
    return Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), intervals={}, retries=1)


def ok_handler(request: httpx.Request) -> httpx.Response:
    if "open-meteo" in request.url.host:
        return httpx.Response(200, json=WEATHER)
    return httpx.Response(200, text=RSS)


def test_build_delta_end_to_end_and_validates():
    delta, errors = build_delta(SITE, fetcher(ok_handler), now=NOW)
    assert not errors
    assert delta.weather[0].rain_probability == 0.9
    assert [e.type for e in delta.events] == [EventType.STRIKE]  # same item from many queries
    Delta.model_validate_json(delta.model_dump_json())


def test_failed_weather_is_a_gap_not_a_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        if "open-meteo" in request.url.host:
            return httpx.Response(500)
        return httpx.Response(200, text=RSS)

    delta, errors = build_delta(SITE, fetcher(handler), now=NOW)
    assert delta.weather == [] and delta.events
    assert any("weather failed" in e for e in errors)


def test_oversized_delta_rejected(monkeypatch):
    monkeypatch.setattr("trip_advisor.pack.delta_builder.MAX_DELTA_BYTES", 50)
    assert MAX_DELTA_BYTES > 50
    with pytest.raises(DeltaTooLarge):
        build_delta(SITE, fetcher(ok_handler), now=NOW)
