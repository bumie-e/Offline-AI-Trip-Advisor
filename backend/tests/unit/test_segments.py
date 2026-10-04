import httpx
import pytest

from trip_advisor.pipeline.collect import routing
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import Place, RoadSegment, RouteOption, SiteRoutes
from trip_advisor.pipeline.collect.segments import backfill_segments
from trip_advisor.sites import Endpoint, SiteConfig, Variant

from .test_collect import NOW


def step(name, km, ref=""):
    return {"name": name, "ref": ref, "distance": km * 1000}


def osrm(steps_per_route, distances):
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": d * 1000, "duration": d * 50,
                "geometry": {"coordinates": [[3.0, 6.0], [3.1, 6.1]]},
                "legs": [{"steps": steps},
                ],
            }
            for steps, d in zip(steps_per_route, distances, strict=True)
        ],
    }  # fmt: skip


def one_route(steps):
    return routing.parse_routes(
        osrm([steps], [sum(s["distance"] for s in steps) / 1000]), label="r"
    )[0]


def test_segments_give_each_road_a_kilometre_range():
    r = one_route(
        [
            step("Lagos-Ibadan Expressway", 30, "E1"),
            step("Sagamu road", 40),
            step("Ore road", 20, "F209"),
        ]
    )
    assert [(s.name, s.from_km, s.to_km) for s in r.segments] == [
        ("E1 Lagos-Ibadan Expressway", 0.0, 30.0), ("Sagamu road", 30.0, 70.0), ("F209 Ore road", 70.0, 90.0),
    ]  # fmt: skip


def test_consecutive_steps_on_one_road_become_one_segment():
    r = one_route([step("A", 10), step("A", 15), step("B", 20)])
    assert [(s.name, s.to_km) for s in r.segments] == [("A", 25.0), ("B", 45.0)]


def test_an_unnamed_bit_belongs_to_the_road_it_sits_on():
    r = one_route([step("A", 10), step("", 2), step("B", 20)])
    assert [(s.name, s.from_km, s.to_km) for s in r.segments] == [
        ("A", 0.0, 12.0),
        ("B", 12.0, 32.0),
    ]


def test_short_junction_bits_are_folded_into_the_road_before():
    r = one_route([step("A", 10), step("Slip road", 0.4), step("B", 20)])
    assert [s.name for s in r.segments] == ["A", "B"]
    assert r.segments[0].to_km == pytest.approx(10.4)


def test_road_at_finds_the_road_and_falls_back_to_the_nearest():
    r = one_route([step("A", 30), step("B", 40)])
    assert routing.road_at(r, 0) == "A" and routing.road_at(r, 29.9) == "A"
    assert routing.road_at(r, 31) == "B" and routing.road_at(r, 69.9) == "B"
    assert routing.road_at(r, 500) == "B"  # past the end: the last road


def test_road_at_is_none_when_segments_are_not_known():
    bare = RouteOption(id="primary", kind="primary", label="r", distance_km=10, duration_min=10,
                       roads=[], geometry=[])  # fmt: skip
    assert routing.road_at(bare, 5) is None


# ---- backfilling routes collected before segments existed ------------------------------------


def stored(distance=90.0) -> SiteRoutes:
    p = Place(name="p", lat=6.5, lon=3.3)
    route = RouteOption(id="primary", kind="primary", label="r", distance_km=distance,
                        duration_min=60, roads=["A"], geometry=[])  # fmt: skip
    alt = route.model_copy(update={"id": "via-x", "kind": "variant", "distance_km": 120.0})
    return SiteRoutes(site_id="s", origin=p, destination=p, routes=[route, alt], stops=[],
                      collected_at=NOW)  # fmt: skip


def a_site() -> SiteConfig:
    via = Endpoint(query="x", lat=6.8, lon=3.6)
    return SiteConfig(id="s", name="S", city="c", state="st", origin=Endpoint(query="a"),
                      destination=Endpoint(query="b"), corridors=[],
                      variants=[Variant(id="via-x", label="via x", via=[via])])  # fmt: skip


def osrm_fetcher(primary_km, variant_km):
    def handler(request: httpx.Request) -> httpx.Response:
        two_stops = request.url.path.count(";") == 1  # origin;destination, no waypoint
        steps = [step("A road", primary_km if two_stops else variant_km)]
        km = primary_km if two_stops else variant_km
        return httpx.Response(200, json=osrm([steps], [km]))

    return Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), intervals={})


def test_backfill_adds_segments_to_matching_routes_and_leaves_the_rest():
    routes, problems = backfill_segments(stored(), a_site(), osrm_fetcher(90.0, 120.0))
    assert not problems
    assert all(r.segments and r.segments[0].name == "A road" for r in routes.routes)
    assert routes.stops == [] and routes.routes[0].roads == ["A"]  # nothing else changed


def test_backfill_will_not_attach_segments_from_a_route_of_a_different_length():
    routes, problems = backfill_segments(stored(), a_site(), osrm_fetcher(150.0, 120.0))
    primary = next(r for r in routes.routes if r.id == "primary")
    assert primary.segments == [] and any("route primary" in p for p in problems)
    assert next(r for r in routes.routes if r.id == "via-x").segments  # the other one still matched


def test_a_segment_range_must_be_in_order():
    assert RoadSegment(name="A", from_km=0, to_km=5).to_km == 5
