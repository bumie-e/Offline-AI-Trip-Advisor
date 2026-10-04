from datetime import UTC, date, datetime

import httpx
import pytest

from trip_advisor.pipeline.collect import coverage, routing, stops
from trip_advisor.pipeline.collect.freshness import cutoff, is_relevant, select_latest
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import (
    DocKind,
    Place,
    RawDocument,
    RouteOption,
    SiteRoutes,
    Stop,
)
from trip_advisor.pipeline.collect.news import parse_fmino, parse_google_rss
from trip_advisor.sites import Corridor, list_sites, load_site, needs_geocoding

TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
CORRIDOR = Corridor(
    name="Lagos-Abeokuta Expressway", queries=["q"], match_terms=["Abeokuta"], primary=True
)

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Lagos govt announces closure of Lagos-Abeokuta Expressway - Punch</title>
<link>https://news.example/a</link><pubDate>Mon, 13 Jul 2026 07:00:00 GMT</pubDate>
<source url="https://punch.example">Punch</source><description>&lt;a&gt;Repair work&lt;/a&gt;</description></item>
<item><title></title><link>https://news.example/empty</link></item>
</channel></rss>"""


def doc(id_: str, published: date | None, title: str, kind: DocKind = DocKind.NEWS) -> RawDocument:
    return RawDocument(
        id=id_,
        site_id="s",
        kind=kind,
        source="x",
        publisher="p",
        url=f"https://x/{id_}",
        title=title,
        published=published,
        fetched_at=NOW,
    )


def test_cutoff_is_three_calendar_months_back():
    assert cutoff(date(2026, 10, 3)) == date(2026, 7, 3)
    assert cutoff(date(2026, 1, 15)) == date(2025, 10, 15)


def test_cutoff_clamps_day_to_month_length():
    assert cutoff(date(2026, 5, 31)) == date(2026, 2, 28)


def test_old_items_are_excluded_and_newest_wins():
    docs = [
        doc("old", date(2026, 6, 1), "Abeokuta road closure"),
        doc("mid", date(2026, 8, 1), "Abeokuta road repair"),
        doc("new", date(2026, 9, 20), "Abeokuta road flood"),
    ]
    ev = select_latest(docs, CORRIDOR, TODAY)
    assert ev.selected and ev.selected.id == "new"
    assert [d.id for d in ev.others] == ["mid"]


def test_condition_word_only_in_snippet_of_unrelated_story_is_not_strong():
    political = doc(
        "pol", date(2026, 9, 20), "Ondo will not disappoint Tinubu in 2027, Abeokuta group"
    )
    political = political.model_copy(
        update={"text": "He praised the road construction and repairs."}
    )
    roadwork = doc("rw", date(2026, 9, 1), "Abeokuta expressway works worsen traffic")
    roadwork = roadwork.model_copy(update={"text": "Lane closure and repair work continues."})
    ev = select_latest([political, roadwork], CORRIDOR, TODAY)
    assert ev.selected and ev.selected.id == "rw"  # older, but a real road report
    assert [d.id for d in ev.others] == ["pol"]


def test_flood_relief_story_is_not_a_road_report_but_flood_blocking_traffic_is():
    relief = doc("relief", date(2026, 9, 4), "NEMA distributes relief to Abeokuta flood victims")
    blocked = doc("blocked", date(2026, 8, 20), "Abeokuta flood disrupts movement of commuters")
    ev = select_latest([relief, blocked], CORRIDOR, TODAY)
    assert ev.selected and ev.selected.id == "blocked"


def test_protest_blocking_the_road_is_a_road_report():
    docs = [
        doc("protest", date(2026, 7, 28), "Gridlock as students block Lagos-Abeokuta Expressway")
    ]
    ev = select_latest(docs, CORRIDOR, TODAY)
    assert ev.selected and ev.selected.id == "protest"


def test_traffic_only_items_are_never_selected():
    docs = [
        doc("op-ed", date(2026, 9, 29), "Rail: solution to Abeokuta expressway gridlock"),
        doc("repair", date(2026, 8, 1), "Abeokuta expressway repair begins"),
    ]
    ev = select_latest(docs, CORRIDOR, TODAY)
    assert ev.selected and ev.selected.id == "repair"  # older, but a real condition
    assert [d.id for d in ev.others] == ["op-ed"]


def test_only_traffic_items_means_no_selected_report_and_a_gap():
    docs = [doc("jam", date(2026, 9, 1), "Gridlock builds on Abeokuta road")]
    ev = select_latest(docs, CORRIDOR, TODAY)
    assert ev.selected is None and len(ev.others) == 1
    cov = coverage.assess("s", make_routes(2, 3, 1), [], [ev], {CORRIDOR.name}, TODAY, [])
    assert not cov.sufficient
    assert any("1 traffic-only items" in g for g in cov.gaps)


def test_undated_future_and_irrelevant_items_are_excluded():
    docs = [
        doc("undated", None, "Abeokuta road closure"),
        doc("future", date(2026, 11, 1), "Abeokuta road closure"),
        doc("offtopic", date(2026, 9, 1), "Abeokuta fashion week"),
        doc("wrongplace", date(2026, 9, 1), "Ibadan road closure"),
    ]
    assert select_latest(docs, CORRIDOR, TODAY).selected is None


def test_gov_notice_wins_same_day_tie():
    docs = [
        doc("n", date(2026, 9, 1), "Abeokuta road repair"),
        doc("g", date(2026, 9, 1), "Abeokuta road repair", DocKind.GOV_NOTICE),
    ]
    ev = select_latest(docs, CORRIDOR, TODAY)
    assert ev.selected and ev.selected.id == "g"


def test_duplicate_ids_collapse():
    docs = [doc("a", date(2026, 9, 1), "Abeokuta road repair")] * 2
    ev = select_latest(docs, CORRIDOR, TODAY)
    assert ev.selected and ev.others == []


def test_relevance_normalises_dashes():
    c = Corridor(name="c", queries=[], match_terms=["Lagos-Ibadan"])
    assert is_relevant(doc("a", TODAY, "Lagos–Ibadan expressway gridlock"), c)


def test_parse_google_rss_extracts_date_publisher_and_strips_suffix():
    docs = parse_google_rss(RSS, site_id="s", corridor="c", query="q", fetched_at=NOW)
    assert len(docs) == 1  # item with empty title is skipped
    d = docs[0]
    assert d.published == date(2026, 7, 13)
    assert d.publisher == "Punch"
    assert d.title == "Lagos govt announces closure of Lagos-Abeokuta Expressway"
    assert d.text == "Repair work"


def test_parse_fmino():
    posts = [
        {
            "date": "2026-09-25T11:57:37",
            "link": "https://fmino.gov.ng/x/",
            "title": {"rendered": "Works Minister inspects Abeokuta road"},
            "excerpt": {"rendered": "<p>Repairs begin</p>"},
        }
    ]
    d = parse_fmino(posts, site_id="s", corridor="c", query="q", fetched_at=NOW)[0]
    assert d.kind == DocKind.GOV_NOTICE and d.published == date(2026, 9, 25)
    assert d.text == "Repairs begin"


OSRM = {
    "code": "Ok",
    "routes": [
        {
            "distance": 100000,
            "duration": 6000,
            "geometry": {"coordinates": [[3.0, 6.0], [3.1, 6.1]]},
            "legs": [
                {
                    "steps": [
                        {"name": "Lagos-Abeokuta Expressway", "ref": "A5", "distance": 80000},
                        {"name": "Side street", "ref": "", "distance": 500},
                    ]
                }
            ],
        },
        {
            "distance": 110000,
            "duration": 6600,
            "geometry": {"coordinates": [[3.0, 6.0], [3.2, 6.0]]},
            "legs": [{"steps": [{"name": "Other Road", "ref": "", "distance": 90000}]}],
        },
    ],
}


def test_parse_routes_flips_lonlat_and_names_roads():
    primary, alt = routing.parse_routes(OSRM, label="Lagos to X")
    assert primary.id == "primary" and alt.id == "alt-1" and alt.kind == "alternative"
    assert primary.geometry[0] == (6.0, 3.0)
    assert primary.roads == ["A5 Lagos-Abeokuta Expressway"]  # short side street dropped
    assert primary.distance_km == 100.0 and primary.duration_min == 100


def test_dedupe_drops_identical_roads():
    a, b = routing.parse_routes(OSRM, label="x")
    assert len(routing.dedupe([a, a.model_copy(update={"id": "dup"}), b])) == 2


def make_route(geometry: list[tuple[float, float]]) -> RouteOption:
    return RouteOption(
        id="primary",
        kind="primary",
        label="r",
        distance_km=1,
        duration_min=1,
        roads=[],
        geometry=geometry,
    )


def test_stops_are_ordered_by_distance_along_route_and_deduped():
    route = make_route([(6.0, 3.0), (6.5, 3.0), (7.0, 3.0)])
    elements = [
        {"lat": 6.9, "lon": 3.01, "tags": {"name": "Far", "place": "town"}},
        {"lat": 6.5, "lon": 3.0, "tags": {"name": "Mid", "amenity": "fuel"}},
        {"center": {"lat": 6.5, "lon": 3.0}, "tags": {"name": "Mid", "amenity": "fuel"}},
        {"lat": 6.0, "lon": 3.0, "tags": {"amenity": "fuel"}},  # unnamed, skipped
    ]
    result = stops.parse_stops(elements, route)
    assert [s.name for s in result] == ["Mid", "Far"]
    assert result[0].km_from_start == pytest.approx(55.6, abs=0.5)


def test_stop_km_is_projected_onto_segment_not_snapped_to_vertex():
    # Route is one long segment; a stop halfway along must sit near the midpoint.
    route = make_route([(6.0, 3.0), (7.0, 3.0)])
    result = stops.parse_stops(
        [{"lat": 6.5, "lon": 3.0, "tags": {"name": "M", "place": "town"}}], route
    )
    assert result[0].km_from_start == pytest.approx(55.6, abs=0.5)


def test_long_routes_are_split_into_overlapping_queries():
    geometry = [(6.0 + i * 0.02, 3.0) for i in range(300)]  # ~660 km at 2.2 km steps
    queries = stops.build_queries(make_route(geometry))
    assert len(queries) > 2 and len(queries) % 2 == 0


def test_resample_keeps_endpoints_and_spacing():
    from trip_advisor.pipeline.collect.geo import resample

    pts = [(6.0 + i * 0.001, 3.0) for i in range(1000)]
    out = resample(pts, 1.0)
    assert out[0] == pts[0] and out[-1] == pts[-1] and len(out) < 200


def test_haversine_known_distance():
    assert stops.haversine_km((0, 0), (0, 1)) == pytest.approx(111.2, abs=0.5)


def test_overpass_query_uses_route_polyline():
    q = stops.build_queries(make_route([(6.0, 3.0), (7.0, 3.0)]))
    assert len(q) == 2 and "6.00000,3.00000,7.00000,3.00000" in q[0]


def test_overpass_timeout_remark_is_retried_then_reported():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"elements": [], "remark": "runtime error: timed out"})

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    warnings: list[str] = []
    result = stops.fetch_stops(fetcher, make_route([(6.0, 3.0), (7.0, 3.0)]), warnings)
    assert result == [] and len(calls) == 8  # 2 queries x 2 servers x 2 attempts
    assert len(warnings) == 2 and "incomplete" in warnings[0]


def test_overpass_falls_back_to_mirror_when_primary_errors():
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "overpass-api.de":
            return httpx.Response(504)
        return httpx.Response(
            200,
            json={"elements": [{"lat": 6.5, "lon": 3.0, "tags": {"name": "Mid", "place": "town"}}]},
        )

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    warnings: list[str] = []
    result = stops.fetch_stops(fetcher, make_route([(6.0, 3.0), (7.0, 3.0)]), warnings)
    assert [s.name for s in result] == ["Mid"] and warnings == []
    assert "overpass.private.coffee" in hosts


def test_overpass_total_failure_is_a_warning_not_a_crash():
    fetcher = Fetcher(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(504))),
        sleep=lambda _: None,
    )
    warnings: list[str] = []
    assert stops.fetch_stops(fetcher, make_route([(6.0, 3.0), (7.0, 3.0)]), warnings) == []
    assert len(warnings) == 2


def test_fetcher_retries_on_429_then_succeeds():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429 if len(calls) < 3 else 200, json={"ok": True})

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    assert fetcher.get("https://example.com/x").json() == {"ok": True}
    assert len(calls) == 3


def test_fetcher_gives_up_after_retries():
    fetcher = Fetcher(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))),
        sleep=lambda _: None,
    )
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.get("https://example.com/x")


def make_routes(n_routes: int, towns: int, fuel: int) -> SiteRoutes:
    route = make_route([(6.0, 3.0), (7.0, 3.0)])
    all_routes = [route.model_copy(update={"id": "primary" if i == 0 else f"alt-{i}"})
                  for i in range(n_routes)]  # fmt: skip
    place = Place(name="p", lat=6, lon=3)
    stop_list = [Stop(name=f"t{i}", kind="town", lat=6, lon=3, km_from_start=i, route_id="primary")
                 for i in range(towns)]  # fmt: skip
    stop_list += [Stop(name=f"f{i}", kind="fuel", lat=6, lon=3, km_from_start=i, route_id="primary")
                  for i in range(fuel)]  # fmt: skip
    return SiteRoutes(site_id="s", origin=place, destination=place, routes=all_routes,
                      stops=stop_list, collected_at=NOW)  # fmt: skip


def assess(routes: SiteRoutes | None, fresh: bool):
    ev = select_latest(
        [doc("a", date(2026, 9, 1), "Abeokuta road repair")] if fresh else [], CORRIDOR, TODAY
    )
    return coverage.assess("s", routes, [], [ev], {CORRIDOR.name}, TODAY, [])


def test_coverage_sufficient_when_all_requirements_met():
    cov = assess(make_routes(2, 3, 1), fresh=True)
    assert cov.sufficient and cov.gaps == []
    assert cov.corridors[0].age_days == 32


def test_coverage_insufficient_without_fresh_primary_road_state():
    cov = assess(make_routes(2, 3, 1), fresh=False)
    assert not cov.sufficient
    assert any("primary corridor" in g for g in cov.gaps)


def test_coverage_flags_missing_alternative_and_stops():
    cov = assess(make_routes(1, 1, 0), fresh=True)
    assert not cov.sufficient
    assert {"no alternative road found", "no fuel stop on the primary route"} <= set(cov.gaps)


def test_coverage_with_no_routes():
    assert "no route found" in assess(None, fresh=True).gaps


def test_preflight_reports_unreachable_hosts():
    from trip_advisor.pipeline.collect.run import preflight

    def handler(request: httpx.Request) -> httpx.Response:
        if "overpass" in request.url.host or "nominatim" in request.url.host:
            raise httpx.ConnectError("dns")
        return httpx.Response(403)  # reachable, even if it refuses us

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ConnectionError, match="stops"):
        preflight(fetcher)


def test_geocode_restricts_to_nigeria_in_english():
    from trip_advisor.pipeline.collect.geocode import geocode

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=[{"lat": "7.1", "lon": "3.3", "type": "rock"}])

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)))
    geocode(fetcher, "Olumo Rock, Abeokuta")
    assert seen["countrycodes"] == "ng" and seen["accept-language"] == "en"


def test_pinned_endpoints_skip_geocoding():
    from trip_advisor.pipeline.collect.geocode import resolve
    from trip_advisor.sites import Endpoint

    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call the network")

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(boom)))
    place = resolve(fetcher, Endpoint(query="Olumo Rock, Abeokuta", lat=7.1, lon=3.3))
    assert (place.lat, place.lon, place.matched) == (7.1, 3.3, "pinned")


def test_preflight_can_skip_nominatim():
    from trip_advisor.pipeline.collect.run import preflight

    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            raise httpx.ConnectError("down")
        return httpx.Response(200)

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)))
    preflight(fetcher, geocoding=False)  # no error
    with pytest.raises(ConnectionError, match="geocoding"):
        preflight(fetcher)


def test_preflight_accepts_one_reachable_overpass_mirror():
    from trip_advisor.pipeline.collect.run import preflight

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "overpass-api.de":
            raise httpx.ConnectError("down")
        return httpx.Response(200)

    preflight(Fetcher(httpx.Client(transport=httpx.MockTransport(handler))))


def test_rescore_keeps_the_original_runs_errors(tmp_path):
    from trip_advisor.pipeline.collect import store
    from trip_advisor.pipeline.collect.run import rescore_site
    from trip_advisor.sites import SiteConfig

    site = SiteConfig.model_validate({
        "id": "s", "name": "S", "city": "c", "state": "st",
        "origin": {"query": "o"}, "destination": {"query": "d"},
        "corridors": [{"name": "C", "queries": ["q"], "match_terms": ["x"], "primary": True}],
    })  # fmt: skip
    first = coverage.assess("s", None, [], [], {"C"}, TODAY, ["serp failed for 'q'"])
    store.save(first, tmp_path / "s" / "coverage.json")
    again = rescore_site(site, today=TODAY, out_dir=tmp_path)
    assert "serp failed for 'q'" in again.coverage.gaps
    assert again.coverage.run_errors == ["serp failed for 'q'"]


def test_all_site_configs_load():
    sites = list_sites()
    assert {"olumo-rock", "osun-osogbo", "idanre-hills"} <= set(sites)
    for site_id in sites:
        site = load_site(site_id)
        assert sum(c.primary for c in site.corridors) == 1
        assert not needs_geocoding(site)  # all points pinned
