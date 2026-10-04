from datetime import UTC, date, datetime, timedelta

import pytest

from trip_advisor.pipeline.collect.images import ImageManifest
from trip_advisor.pipeline.collect.models import Place, RoadSegment, RouteOption, SiteRoutes
from trip_advisor.pipeline.collect.models import Stop as MapStop
from trip_advisor.pipeline.generate import stop_detail as sd
from trip_advisor.pipeline.generate.evidence import GenInput, route_id
from trip_advisor.pipeline.generate.run import (
    _apply_notes,
    _outline,
    generate_itinerary,
    load_input,
)
from trip_advisor.pipeline.generate.skeleton import build_stops
from trip_advisor.pipeline.generate.writer import StopNote
from trip_advisor.schemas.common import Confidence, Source
from trip_advisor.schemas.delta import Delta
from trip_advisor.schemas.itinerary import Itinerary, Stop, TripRequest
from trip_advisor.schemas.pack import RoadNote
from trip_advisor.sites import Endpoint, SiteConfig

from .test_images import a_record

TODAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 9, tzinfo=UTC)


def note(route="Lagos-Ibadan Expressway", *, days=10, conf=Confidence.MEDIUM, id="rn-1",
         summary="Reports suggest repairs are slowing traffic.", published="auto"):  # fmt: skip
    when = TODAY - timedelta(days=days) if published == "auto" else published
    return RoadNote(
        id=id, summary=summary, route=route, rain_sensitivity="medium", confidence=conf,
        source=Source(publisher="Punch", url="https://example.com/a", published=when),
        last_verified=TODAY,
    )  # fmt: skip


# ---- matching reports to a stop -----------------------------------------------------------------


def test_tokens_drop_generic_and_short_words():
    assert sd.tokens("E1 Lagos-Ibadan Expressway Road") == {"lagos", "ibadan"}
    assert "state" not in sd.tokens("Ondo State")


def test_a_report_applies_when_it_names_the_stops_town():
    n = note("Lagos-Ore-Benin Expressway")
    assert sd.note_applies(n, "A121-1 Benin-Sagamu Expressway", ["Ore"])  # the names differ
    assert not sd.note_applies(n, "A121-1 Benin-Sagamu Expressway", ["Sagamu"])  # 140 km away


def test_a_town_is_matched_as_a_whole_word():
    assert not sd.note_applies(
        note("Lagos-Ibadan Expressway", summary="more repairs"), None, ["Ore"]
    )


def test_a_report_applies_when_its_road_sits_inside_this_road():
    n = note("Lagos-Ibadan Expressway")
    assert sd.note_applies(n, "E1 Lagos-Ibadan Expressway", [])
    assert not sd.note_applies(n, "A5 Lagos-Abeokuta Expressway", [])  # shares only "lagos"


def test_a_report_applies_when_two_place_words_are_shared():
    assert sd.note_applies(note("Benin-Sagamu-Ijebu road"), "A121 Benin-Sagamu Expressway", [])


def test_nothing_to_match_on_means_no_match():
    assert not sd.note_applies(note(), None, [])


# ---- the road at a stop -----------------------------------------------------------------------


def road(notes, **kw):
    base = {"road_name": "E1 Lagos-Ibadan Expressway", "places": [], "km": 54.0,
            "previous_km": 25.0, "today": TODAY}  # fmt: skip
    return sd.road_for_stop(notes, **{**base, **kw})


def test_no_report_says_so_plainly_and_still_gives_the_road_and_distance():
    r = road([])
    assert r.condition == sd.NO_REPORT and not r.has_recent_report and r.evidence_ids == []
    assert (r.name, r.km_from_start, r.km_since_previous_stop) == (
        "E1 Lagos-Ibadan Expressway",
        54.0,
        29.0,
    )


def test_a_recent_report_gives_condition_age_confidence_and_evidence():
    r = road([note(days=12, conf=Confidence.LOW)])
    assert r.has_recent_report and r.report_age_days == 12 and r.confidence == Confidence.LOW
    assert r.condition == "Reports suggest repairs are slowing traffic." and r.evidence_ids == [
        "rn-1"
    ]


@pytest.mark.parametrize("days", [93, 200])
def test_reports_older_than_three_months_are_ignored(days):
    assert not road([note(days=days)]).has_recent_report


def test_undated_and_future_reports_are_ignored():
    assert not road([note(published=None)]).has_recent_report
    assert not road([note(days=-5)]).has_recent_report


def test_the_newest_report_wins_then_the_more_confident_one():
    old, new = note(days=30, id="old"), note(days=5, id="new")
    assert road([old, new]).evidence_ids[0] == "new"
    same_day = [
        note(days=5, conf=Confidence.LOW, id="low"),
        note(days=5, conf=Confidence.HIGH, id="high"),
    ]
    assert road(same_day).evidence_ids[0] == "high"


def test_evidence_is_capped_at_three_reports():
    r = road([note(days=d, id=f"rn-{d}") for d in range(1, 8)])
    assert r.evidence_ids == ["rn-1", "rn-2", "rn-3"]


def test_without_a_distance_the_gap_since_the_last_stop_is_unknown():
    assert road([], km=None).km_since_previous_stop is None
    assert road([], previous_km=None).km_since_previous_stop is None


# ---- one photo per stop -----------------------------------------------------------------------


def photo(caption, kind="road", conf="medium", id=None):
    return a_record(id=id or f"img-{caption[:6]}", summary=caption, kind=kind, confidence=conf,
                    path=f"/images/s/{id or caption[:6]}.jpg")  # fmt: skip


def entry(title, kind, km, places=()):
    return sd.Entry(Stop(order=1, title=title), kind, km, list(places))


def test_the_site_photo_prefers_the_most_certain_one_and_ignores_road_photos():
    imgs = [photo("A road", "road", "high"), photo("Rock 1", "site", "medium", "r1"),
            photo("Rock 2", "site", "high", "r2")]  # fmt: skip
    assert sd.pick_site_image(imgs).id == "r2"
    assert sd.pick_site_image([photo("A road", "road")]) is None
    assert sd.pick_site_image([]) is None


def test_a_photo_goes_to_the_stop_its_caption_names():
    entries = [entry("Start", "start", 0), entry("Pass through Sagamu", "town", 54, ["Sagamu"]),
               entry("Pass through Ore", "town", 197, ["Ore"])]  # fmt: skip
    out = sd.assign_road_images([photo("Road near Ore town", id="p1")], entries, {})
    assert out[2].id == "p1" and out[2].shows_this_stop
    assert 0 not in out and 1 not in out


def test_a_photo_can_match_on_the_name_of_the_road():
    entries = [entry("Start", "start", 0), entry("Pass through Mowe", "town", 25, ["Mowe"])]
    names = {0: "E1 Lagos-Ibadan Expressway", 1: "E1 Lagos-Ibadan Expressway"}
    out = sd.assign_road_images([photo("Lagos Ibadan expressway", id="p1")], entries, names)
    assert len(out) == 1 and next(iter(out.values())).shows_this_stop


def test_a_photo_is_never_used_for_two_stops():
    entries = [
        entry("Pass through Ore", "town", 197, ["Ore"]),
        entry("Fuel near Ore", "fuel", 199, ["Ore"]),
    ]
    out = sd.assign_road_images([photo("Road near Ore", id="p1")], entries, {})
    assert len(out) == 1  # one photo, one stop: the other stop has none
    assert next(iter(out.values())).shows_this_stop


def test_leftover_stops_get_example_photos_nearest_the_destination_first():
    entries = [entry("Start", "start", 0), entry("Pass through A", "town", 50, ["Alpha"]),
               entry("Pass through B", "town", 150, ["Beta"]), entry("Visit", "visit", 200)]  # fmt: skip
    photos = [photo("A road in Ondo", id="p1"), photo("Another road in Ondo", id="p2")]
    out = sd.assign_road_images(photos, entries, {})
    assert set(out) == {1, 2}  # the stops nearest the destination, not the start
    assert not any(s.shows_this_stop for s in out.values())  # labelled as examples


def test_there_may_be_fewer_photos_than_stops_and_the_visit_never_gets_a_road_photo():
    entries = [
        entry("Start", "start", 0),
        entry("Pass through A", "town", 50, ["Alpha"]),
        entry("Visit", "visit", 200),
    ]
    out = sd.assign_road_images([photo("A road", id="p1")], entries, {})
    assert len(out) == 1 and 2 not in out
    assert sd.assign_road_images([], entries, {}) == {}


def test_site_photos_are_not_used_as_road_photos():
    entries = [entry("Pass through Ore", "town", 197, ["Ore"])]
    assert sd.assign_road_images([photo("Rock near Ore", "site", id="p1")], entries, {}) == {}


def test_the_stop_image_carries_the_credit_and_size():
    s = sd.to_stop_image(a_record(), shows_this_stop=True)
    assert (
        s.credit.startswith("Photo: Ada")
        and (s.width, s.height) == (800, 533)
        and s.path.endswith(".jpg")
    )


# ---- the line in the list ---------------------------------------------------------------------


def a_route():
    return RouteOption(id="primary", kind="primary", label="r", distance_km=268.1, duration_min=226,
                       roads=[], geometry=[])  # fmt: skip


def test_comment_lines():
    r = a_route()
    assert (
        sd.comment_for(entry("Leave", "start", 0), sd.StopRoad(), r)
        == "268 km, about 3 h 46 min without traffic."
    )
    assert sd.comment_for(entry("Visit", "visit", 268), sd.StopRoad(), r) == "Your destination."
    quiet = sd.StopRoad(name="E1 Lagos-Ibadan Expressway")
    assert (
        sd.comment_for(entry("Pass", "town", 25.4), quiet, r)
        == "25 km in on E1 Lagos-Ibadan Expressway · no recent road report"
    )
    reported = sd.StopRoad(
        name="E1", has_recent_report=True, report_age_days=65, confidence=Confidence.LOW
    )
    assert (
        sd.comment_for(entry("Pass", "town", 197), reported, r)
        == "197 km in on E1 · road report 65 days old (low confidence)"
    )


def test_a_short_comment_is_cut_at_a_word_with_an_ellipsis():
    out = sd.short("word " * 60, 40)
    assert out.endswith("…") and len(out) <= 40 and " …" not in out
    assert sd.short("fits", 40) == "fits"


# ---- the whole itinerary ----------------------------------------------------------------------


def trip(records, *, segments=True):
    segs = [RoadSegment(name="E1 Lagos-Ibadan Expressway", from_km=0, to_km=120),
            RoadSegment(name="A121-1 Benin-Sagamu Expressway", from_km=120, to_km=250)]  # fmt: skip
    route = RouteOption(id="primary", kind="primary", label="r", distance_km=250, duration_min=200,
                        roads=["E1 Lagos-Ibadan Expressway"], geometry=[], segments=segs if segments else [])  # fmt: skip
    stops = [MapStop(name="Mowe", kind="town", lat=6.5, lon=3.3, km_from_start=25, route_id="primary"),
             MapStop(name="Ore", kind="town", lat=6.5, lon=3.3, km_from_start=190, route_id="primary")]  # fmt: skip
    p = Place(name="Murtala Muhammed Airport", lat=6.5, lon=3.3)
    site = SiteConfig(id="idanre-hills", name="Idanre Hills", city="Idanre", state="Ondo",
                      origin=Endpoint(query="a"), destination=Endpoint(query="b"), corridors=[])  # fmt: skip
    request = TripRequest(site_id="idanre-hills", start_city="Lagos", start_date=date(2026, 10, 14),
                          end_date=date(2026, 10, 14), group_size=2)  # fmt: skip
    return GenInput(site=site, request=request, today=TODAY, delta=Delta(generated_at=NOW), records=records,
                    routes=SiteRoutes(site_id="idanre-hills", origin=p, destination=p, routes=[route],
                                      stops=stops, collected_at=NOW))  # fmt: skip


def test_each_outbound_stop_gets_its_road_comment_and_the_right_photo():
    records = [note("Lagos-Ore-Benin Expressway", id="rn-ore", days=65),
               photo("Idanre Hills", "site", "high", "site1"), photo("Road in Ondo State", id="road1")]  # fmt: skip
    stops, back = build_stops(trip(records))
    titles = [s.title for s in stops]
    assert titles == [
        "Leave Murtala Muhammed Airport",
        "Pass through Mowe",
        "Pass through Ore",
        "Visit Idanre Hills",
    ]
    start, mowe, ore, visit = stops
    assert (
        start.road.name == "A121-1 Benin-Sagamu Expressway"
    )  # the road that carries most of the drive
    assert mowe.road.name == "E1 Lagos-Ibadan Expressway" and not mowe.road.has_recent_report
    assert ore.road.has_recent_report and ore.road.evidence_ids == ["rn-ore"]
    assert visit.image.id == "site1" and visit.image.shows_this_stop
    assert (
        ore.image.id == "road1" and not ore.image.shows_this_stop
    )  # an example, nearest the destination
    assert start.image is None and mowe.image is None  # one photo, used once
    assert all(s.comment for s in stops)
    assert back[0].road is None and back[0].image is None  # the way back stays minimal


def test_citations_on_the_stop_are_not_changed_by_the_road_lookup():
    records = [note("Lagos-Ore-Benin Expressway", id="rn-ore")]
    ore = build_stops(trip(records))[0][2]
    assert ore.cited_ids == [route_id("idanre-hills", trip(records).primary)]
    assert ore.road.evidence_ids == ["rn-ore"]


def test_without_segments_the_road_name_is_unknown_but_reports_still_match_by_town():
    records = [note("Lagos-Ore-Benin Expressway", id="rn-ore")]
    stops, _ = build_stops(trip(records, segments=False))
    mowe, ore = stops[1], stops[2]
    assert mowe.road.name is None and ore.road.name is None
    assert ore.road.has_recent_report and not mowe.road.has_recent_report


def test_with_no_route_the_visit_stop_still_gets_its_photo():
    inp = trip([photo("Idanre Hills", "site", "high", "site1")])
    inp.routes = None
    stops, back = build_stops(inp)
    assert (
        [s.title for s in stops] == ["Visit Idanre Hills"]
        and stops[0].image.id == "site1"
        and back == []
    )


def test_the_itinerary_with_stop_details_round_trips_and_old_ones_still_load():
    it = generate_itinerary(trip([photo("Idanre Hills", "site", "high", "site1")]), now=NOW)
    assert Itinerary.model_validate_json(it.model_dump_json()) == it
    old = it.model_dump(mode="json")
    for s in [*old["stops"], *old["return_leg"]]:
        for key in ("comment", "image", "road", "advice"):
            s.pop(key, None)
    assert (
        Itinerary.model_validate(old).stops[0].road is None
    )  # an itinerary saved before this change


# ---- the model's part -------------------------------------------------------------------------


def test_the_outline_tells_the_model_which_evidence_each_stop_has():
    records = [note("Lagos-Ore-Benin Expressway", id="rn-ore", days=65)]
    stops, back = build_stops(trip(records))
    text = _outline(stops, back)
    assert (
        "Pass through Ore | road: A121-1 Benin-Sagamu Expressway | recent road evidence: rn-ore"
        in text
    )
    assert (
        "Pass through Mowe | road: E1 Lagos-Ibadan Expressway | recent road evidence: none" in text
    )
    assert "Return:" in text


def test_the_models_note_becomes_the_stops_advice_and_the_data_notes_stay():
    stops, _ = build_stops(trip([note("Lagos-Ore-Benin Expressway", id="rn-ore")]))
    out = _apply_notes(
        stops, [StopNote(order=3, note="Allow extra time near Ore.", cited_ids=["rn-ore"])]
    )
    ore = out[2]
    assert ore.advice == "Allow extra time near Ore." and "rn-ore" in ore.cited_ids
    assert ore.notes == stops[2].notes  # facts from the data are untouched
    assert all(s.advice == "" for i, s in enumerate(out) if i != 2)


def test_the_cli_loader_reads_photos_from_the_manifest(tmp_path):
    folder = tmp_path / "images" / "idanre-hills"
    folder.mkdir(parents=True)
    rec = a_record(id="img-1", kind="site")
    (folder / "manifest.json").write_text(
        ImageManifest(site_id="idanre-hills", collected_at=NOW, images=[rec]).model_dump_json()
    )
    site = trip([]).site
    request = trip([]).request
    inp = load_input(site, request, raw_dir=tmp_path / "raw", structured_dir=tmp_path / "s",
                     deltas_dir=tmp_path / "d", images_dir=tmp_path / "images", today=TODAY)  # fmt: skip
    assert [i.id for i in inp.images] == ["img-1"]


# ---- how far a report reaches ------------------------------------------------------------------


def test_a_report_that_names_the_place_applies_here():
    n = note("Osogbo roads", summary="News reports suggest flooding affected streets in Osogbo.")
    assert (
        sd.note_scope(n, "F205 Gbongan - Osogbo Road", ["Osogbo", "Osun-Osogbo Sacred Grove"])
        == "here"
    )


def test_a_town_glued_into_a_road_name_is_only_the_corridor():
    """The real Olumo Rock case: the protest was on the Lagos-Abeokuta expressway, not at Abeokuta."""
    n = note(
        "Lagos–Abeokuta Expressway",
        summary="Reports indicate students blocked the Lagos–Abeokuta Expressway.",
    )
    assert sd.note_scope(n, "Ikija Road", ["Abeokuta", "Olumo Rock"]) == "corridor"


def test_the_ore_flood_links_to_ore_as_the_corridor_not_as_a_place():
    n = note(
        "Lagos-Ore-Benin Expressway",
        summary="Reports suggest flooding on the Lagos-Ore-Benin expressway.",
    )
    assert sd.note_scope(n, "A121-1 Benin-Sagamu Expressway", ["Ore"]) == "corridor"


def test_a_report_about_this_road_has_road_scope():
    n = note("Lagos-Ibadan Expressway", summary="Repairs are slowing traffic.")
    assert sd.note_scope(n, "E1 Lagos-Ibadan Expressway", ["Mowe"]) == "road"


def test_a_report_about_somewhere_else_has_no_scope():
    assert (
        sd.note_scope(note("Lagos-Ibadan Expressway"), "F205 Gbongan - Osogbo Road", ["Osogbo"])
        is None
    )


def test_a_place_named_on_its_own_is_not_confused_with_a_longer_name():
    n = note("X", summary="Heavy rain in Idanre town.")
    assert sd.note_scope(n, None, ["Idanre"]) == "here"
    assert (
        sd.note_scope(note("X", summary="Roads to Ore-Ondo are bad."), None, ["Ore"]) == "corridor"
    )


def test_the_most_specific_report_wins_even_if_an_older_one_is_wider():
    wide = note(
        "Lagos-Ore-Benin Expressway",
        days=3,
        id="wide",
        summary="Flooding on the Lagos-Ore-Benin expressway.",
    )
    local = note("Ore", days=20, id="local", summary="Flooding in Ore town.")
    r = road([wide, local], road_name="A121-1 Benin-Sagamu Expressway", places=["Ore"])
    assert r.scope == "here" and r.evidence_ids[0] == "local" and r.evidence_ids[1] == "wide"


def test_a_stop_with_no_report_has_no_scope():
    assert road([]).scope is None


def test_the_outline_says_how_far_each_report_reaches():
    stops, back = build_stops(trip([note("Lagos-Ore-Benin Expressway", id="rn-ore", days=65)]))
    assert "recent road evidence: rn-ore (applies: corridor)" in _outline(stops, back)
    assert "Mowe | road: E1 Lagos-Ibadan Expressway | recent road evidence: none" in _outline(
        stops, back
    )


# ---- "this photo shows this stop" is a strong claim -------------------------------------------


def test_one_shared_word_with_the_road_makes_a_photo_an_example_not_an_exact_match():
    entries = [entry("Start", "start", 0), entry("Pass through Ifo", "town", 34, ["Ifo"])]
    names = {0: "A5 Lagos-Abeokuta Expressway", 1: "A5 Lagos-Abeokuta Expressway"}
    out = sd.assign_road_images([photo("Abeokuta-ijebu expressway", id="p1")], entries, names)
    assert len(out) == 1 and not next(iter(out.values())).shows_this_stop  # a different road


def test_two_shared_words_with_the_road_make_it_exact():
    entries = [entry("Pass through Mowe", "town", 25, ["Mowe"])]
    out = sd.assign_road_images(
        [photo("Lagos Ibadan expressway", id="p1")], entries, {0: "E1 Lagos-Ibadan Expressway"}
    )
    assert out[0].shows_this_stop


def test_naming_the_stops_town_makes_it_exact():
    entries = [entry("Pass through Ore", "town", 197, ["Ore"])]
    assert sd.assign_road_images([photo("Road in Ore", id="p1")], entries, {})[0].shows_this_stop


def test_an_ibadan_city_road_is_not_the_lagos_ibadan_expressway():
    entries = [entry("Pass through Mowe", "town", 25, ["Mowe"])]
    out = sd.assign_road_images(
        [photo("Challenge Expressway Ibadan", id="p1")], entries, {0: "E1 Lagos-Ibadan Expressway"}
    )
    assert not out[0].shows_this_stop
