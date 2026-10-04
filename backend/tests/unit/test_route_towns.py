from trip_advisor.pipeline.collect.models import RouteOption
from trip_advisor.pipeline.collect.models import Stop as MapStop
from trip_advisor.pipeline.collect.towns import MAX_TOWNS, route_towns
from trip_advisor.pipeline.generate.run import generate_itinerary

from .test_generate import NOW, inp


def route(km: float = 268.0) -> RouteOption:
    return RouteOption(
        id="primary", kind="primary", label="r", distance_km=km, duration_min=200,
        roads=["Lagos-Ibadan Expressway"], geometry=[(6.5, 3.3)],
    )  # fmt: skip


def stop(name: str, km: float, kind: str = "town", route_id: str = "primary") -> MapStop:
    return MapStop(name=name, kind=kind, lat=6.5, lon=3.3, km_from_start=km, route_id=route_id)


def names(stops: list[MapStop]) -> list[str]:
    return [s.name for s in stops]


def test_nearby_suburbs_collapse_to_the_city():
    # Seven suburbs within 3 km of Ijebu-Ode must give one stop, and it should be the city.
    cluster = [stop(n, 85.6 + i * 0.4) for i, n in enumerate("ABCDEFG")]
    cluster.append(stop("Ijebu-Ode", 88.0, "city"))
    assert names(route_towns(cluster, route())) == ["Ijebu-Ode"]


def test_cluster_without_a_city_uses_the_middle_town():
    got = route_towns([stop("Ibafo", 21.5), stop("Mowe", 25.4), stop("Redeem", 27.0)], route())
    assert names(got) == ["Mowe"]


def test_towns_at_the_start_and_destination_are_skipped():
    stops = [stop("Ikeja", 2.8, "city"), stop("Sagamu", 54.4, "city"), stop("Idanre", 262.0)]
    assert names(route_towns(stops, route())) == ["Sagamu"]


def test_only_towns_on_this_route_and_only_towns_not_amenities():
    stops = [
        stop("Sagamu", 54, "city"), stop("Elsewhere", 90, route_id="alt-1"),
        stop("Total", 60, "fuel"), stop("LASUTH", 40, "hospital"),
    ]  # fmt: skip
    assert names(route_towns(stops, route())) == ["Sagamu"]


def test_result_is_ordered_by_distance_whatever_the_input_order():
    stops = [stop("Ore", 197, "city"), stop("Sagamu", 54, "city"), stop("Ijebu-Ode", 88, "city")]
    assert names(route_towns(stops, route())) == ["Sagamu", "Ijebu-Ode", "Ore"]


def test_many_towns_are_capped_and_spread_evenly():
    stops = [stop(f"T{i}", 15 + i * 25, "city") for i in range(10)]  # 10 well-separated towns
    got = route_towns(stops, route(km=300))
    assert len(got) == MAX_TOWNS
    assert got[0].name == "T0" and got[-1].name == "T9"


def test_no_towns_gives_empty_list():
    assert route_towns([], route()) == []


def test_itinerary_lists_towns_and_fuel_in_driving_order_and_return_via():
    i = inp()
    assert i.routes is not None
    i.routes.stops[:] = [
        stop("Ore", 70, "city"), stop("Sagamu", 30, "city"), stop("Total Sagamu", 60, "fuel"),
    ]  # fmt: skip
    it = generate_itinerary(i, now=NOW)
    titles = [s.title for s in it.stops]
    assert titles == [
        "Leave Murtala Muhammed Airport", "Pass through Sagamu",
        "Fuel and rest: Total Sagamu", "Pass through Ore", "Visit Olumo Rock",
    ]  # fmt: skip
    assert [s.order for s in it.stops] == [1, 2, 3, 4, 5]
    assert "Via Ore, Sagamu." in it.return_leg[0].notes
    town_stop = it.stops[1]
    assert town_stop.cited_ids and town_stop.notes.startswith("About 30 km into the 100 km drive")


def test_visit_notes_only_use_facts_that_name_the_site():
    from datetime import date

    from trip_advisor.schemas.common import Confidence
    from trip_advisor.schemas.pack import SiteFact

    from .test_generate import SRC

    def fact(id_: str, summary: str) -> SiteFact:
        return SiteFact(
            id=id_, summary=summary, source=SRC, confidence=Confidence.MEDIUM,
            last_verified=date(2026, 10, 1), topic="Opening hours",
        )  # fmt: skip

    gallery = fact("g", "Genesis Art Gallery is open from 8 AM to 5 PM.")
    site = fact("s", "Olumo Rock is open Monday to Saturday from 9AM to 7PM.")
    it = generate_itinerary(inp([gallery, site]), now=NOW)
    visit = next(s for s in it.stops if s.title.startswith("Visit"))
    assert visit.cited_ids == ["s"] and "Genesis" not in visit.notes


def test_visit_has_no_hours_when_no_fact_names_the_site():
    from datetime import date

    from trip_advisor.schemas.common import Confidence
    from trip_advisor.schemas.pack import SiteFact

    from .test_generate import SRC

    gallery = SiteFact(
        id="g", summary="Genesis Art Gallery is open from 8 AM to 5 PM.", source=SRC,
        confidence=Confidence.MEDIUM, last_verified=date(2026, 10, 1), topic="Opening hours",
    )  # fmt: skip
    it = generate_itinerary(inp([gallery]), now=NOW)
    visit = next(s for s in it.stops if s.title.startswith("Visit"))
    assert visit.notes == "" and visit.cited_ids == []


def test_every_generated_stop_with_a_note_cites_something():
    i = inp()
    assert i.routes is not None
    i.routes.stops[:] = [stop("Sagamu", 30, "city"), stop("Total Sagamu", 60, "fuel")]
    it = generate_itinerary(i, now=NOW)
    for s in [*it.stops, *it.return_leg]:
        if s.notes:
            assert s.cited_ids, f"{s.title!r} has a note but cites nothing"
