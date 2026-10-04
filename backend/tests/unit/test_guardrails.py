from datetime import date

import pytest

from trip_advisor.guardrails.catalog import Catalog, Fact
from trip_advisor.guardrails.checks import (
    ViolationKind,
    check_advice,
    guard_advice,
    guard_note,
    template_advice,
)
from trip_advisor.guardrails.wording import wording_problems
from trip_advisor.schemas.itinerary import Advice, Severity, Verdict

TODAY = date(2026, 10, 3)


def catalog() -> Catalog:
    c = Catalog()
    c.add(Fact("weather-2026-10-14", "weather", "Rain chance 86% on 14 Oct in Abeokuta",
               "Open-Meteo forecast", TODAY))  # fmt: skip
    c.add(Fact("road-note-1", "road_note", "Repairs under way on the expressway.", "Punch",
               date(2026, 9, 20)))  # fmt: skip
    c.add(Fact("news-1", "event", "strike (confirmed) affecting flights", "News reports", None))
    return c


def advice(text="Reports suggest rain may slow the drive.", ids=("weather-2026-10-14",), **kw):
    base = {"changed": True, "severity": Severity.ELEVATED, "advice": text, "cited_ids": list(ids)}
    return Advice(**{**base, **kw})


def kinds(a: Advice) -> set[ViolationKind]:
    return {v.kind for v in check_advice(a, catalog())}


def test_clean_advice_passes_unchanged():
    g = guard_advice(advice(), catalog())
    assert not g.replaced and not g.violations


def test_unknown_id_is_rejected_and_replaced_keeping_valid_ids_and_severity():
    bad = advice(ids=("weather-2026-10-14", "road-note-999"), severity=Severity.HIGH)
    g = guard_advice(bad, catalog())
    assert g.replaced and ViolationKind.UNKNOWN_ID in {v.kind for v in g.violations}
    assert g.advice.cited_ids == ["weather-2026-10-14"]
    assert g.advice.severity == Severity.HIGH  # a guardrail never relaxes the warning
    assert "Rain chance 86%" in g.advice.advice


def test_warning_with_only_invented_ids_becomes_a_cautious_uncited_template():
    g = guard_advice(advice(ids=("made-up",), severity=Severity.HIGH), catalog())
    assert g.replaced and g.advice.cited_ids == []
    assert "could not be tied to a source" in g.advice.advice
    assert g.advice.severity == Severity.HIGH


def test_warning_without_any_citation_is_flagged():
    assert ViolationKind.UNCITED in kinds(advice(ids=()))


def test_no_change_advice_may_cite_nothing():
    assert not kinds(advice("No change found.", ids=(), changed=False, severity=Severity.NONE))


@pytest.mark.parametrize(
    "text",
    [
        "The road is safe to drive.",
        "This route is unsafe after rain.",
        "It is dangerous to travel now.",
        "We guarantee dry weather.",
        "There is no risk on this road.",
        "The strike will definitely end.",
        "You must not travel on Tuesday.",
    ],
)
def test_banned_wording_is_caught(text):
    assert wording_problems(text)
    assert ViolationKind.WORDING in kinds(advice(text))


@pytest.mark.parametrize(
    "text",
    [
        "Reports suggest the road may be slow.",
        "See the safety notes and confirm with a guide.",
        "Consider leaving earlier to safeguard your schedule.",
    ],
)
def test_advisory_wording_passes(text):
    assert not wording_problems(text)


def test_banned_word_in_alternatives_is_caught_and_removed_by_template():
    a = advice(alternatives=["leave earlier", "use the safe route"])
    assert ViolationKind.WORDING in kinds(a)
    assert template_advice(a, catalog()).alternatives == ["leave earlier"]


def test_percentage_must_come_from_a_cited_source():
    assert not kinds(advice("Rain is 86% likely on the day."))
    assert ViolationKind.NUMBER_NOT_IN_SOURCE in kinds(advice("Rain is 95% likely on the day."))
    # Right number but not cited: still invented as far as the reader can tell.
    assert ViolationKind.NUMBER_NOT_IN_SOURCE in kinds(
        advice("Rain is 86% likely.", ids=("road-note-1",))
    )


def test_empty_and_overlong_advice():
    assert ViolationKind.EMPTY in kinds(advice("  "))
    assert ViolationKind.TOO_LONG in kinds(advice("x" * 700))


def test_stop_notes_are_guarded_too():
    ok, _ = guard_note("Rain chance is 86%.", ["weather-2026-10-14"], catalog())
    assert ok
    ok, found = guard_note("Rain chance is 86%.", [], catalog())
    assert not ok and found[0].kind == ViolationKind.NUMBER_NOT_IN_SOURCE
    assert not guard_note("This stretch is safe.", [], catalog())[0]


def test_sources_show_publisher_and_age_and_skip_unknown_ids():
    refs = catalog().sources_for(["road-note-1", "news-1", "ghost"], TODAY)
    assert [r.id for r in refs] == ["road-note-1", "news-1"]
    assert refs[0].label() == "Punch, 2026-09-20 (13 days old)"
    assert refs[1].label() == "News reports, date unknown"


def test_verdict_enum_untouched():
    assert Verdict.NOT_ADVISED == "not_advised"
