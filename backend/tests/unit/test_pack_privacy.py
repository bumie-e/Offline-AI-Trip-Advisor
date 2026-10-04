from datetime import UTC, date, datetime, timedelta

from trip_advisor.pack.builder import MAX_PACK_BYTES, build_pack, version_for
from trip_advisor.pipeline.structure.models import StructuredSite
from trip_advisor.schemas.common import Confidence, Sensitivity, Source
from trip_advisor.schemas.pack import Pack, RoadNote, SiteFact
from trip_advisor.services.privacy import REDACTED, redact, round_coord

TODAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 9, tzinfo=UTC)


def road(i, published=date(2026, 9, 20), conf=Confidence.MEDIUM, summary="x") -> RoadNote:
    return RoadNote(
        id=f"road-{i}", summary=summary, source=Source(publisher="P", url="https://e.com/a", published=published),
        confidence=conf, last_verified=TODAY, route="Lagos-Abeokuta Expressway",
        rain_sensitivity=Sensitivity.HIGH,
    )  # fmt: skip


def fact(i) -> SiteFact:
    return SiteFact(
        id=f"fact-{i}", summary="Open daily.", source=Source(publisher="Wikivoyage", url="https://e.com/w"),
        confidence=Confidence.MEDIUM, last_verified=TODAY, topic="opening_hours",
    )  # fmt: skip


def structured(records) -> StructuredSite:
    return StructuredSite(site_id="olumo-rock", structured_on=TODAY, records=records, flags=[],
                          rejected=[], docs_processed=1)  # fmt: skip


def test_stale_and_undated_road_notes_are_left_out_but_facts_stay():
    recs = [road(1), road(2, published=date(2026, 3, 1)), road(3, published=None), fact(1)]
    pack, report = build_pack(structured(recs), today=TODAY, now=NOW)
    assert {r.id for r in pack.records} == {"road-1", "fact-1"}
    assert report.dropped_stale == 2


def test_facts_come_first_then_confident_then_newest():
    recs = [road(1, conf=Confidence.LOW), road(2, conf=Confidence.HIGH),
            road(3, conf=Confidence.HIGH, published=date(2026, 9, 28)), fact(1)]  # fmt: skip
    pack, _ = build_pack(structured(recs), today=TODAY, now=NOW)
    assert [r.id for r in pack.records] == ["fact-1", "road-3", "road-2", "road-1"]


def test_pack_is_trimmed_to_the_size_budget_dropping_lowest_priority_first():
    recs = [fact(0)] + [road(i, summary="y" * 2000, conf=Confidence.LOW) for i in range(80)]
    recs.append(road(999, summary="y" * 2000, conf=Confidence.HIGH))
    pack, report = build_pack(structured(recs), today=TODAY, now=NOW)
    assert report.size_bytes <= MAX_PACK_BYTES and report.dropped_for_size > 0
    ids = [r.id for r in pack.records]
    assert "fact-0" in ids and "road-999" in ids
    Pack.model_validate_json(pack.model_dump_json())


def test_version_is_stable_for_same_content_and_changes_with_it():
    a, b = [road(1)], [road(1), road(2)]
    assert version_for(a, TODAY) == version_for([road(1)], TODAY)
    assert version_for(a, TODAY) != version_for(b, TODAY)
    assert version_for(a, TODAY).startswith("2026.10.04+")
    assert version_for(a, TODAY) != version_for(a, TODAY + timedelta(days=1))


def test_coordinates_are_rounded_to_about_a_kilometre():
    assert round_coord(7.167195234) == 7.17 and round_coord(None) is None


def test_redact_removes_phones_emails_and_links_but_keeps_the_report():
    note = "Flooded near Ifo, call me on +234 803 123 4567 or ade@mail.com, see https://x.co/p"
    out = redact(note)
    assert "803" not in out and "@" not in out and "https" not in out
    assert out.startswith("Flooded near Ifo") and out.count(REDACTED) == 3
    assert (
        redact("Two lanes closed, about 40 minutes delay")
        == "Two lanes closed, about 40 minutes delay"
    )
