from datetime import UTC, date, datetime
from typing import Any

from trip_advisor.pipeline.collect.models import DocKind, RawDocument
from trip_advisor.pipeline.structure.models import FlagKind, Reason
from trip_advisor.pipeline.structure.run import structure_docs, write_review_sample
from trip_advisor.schemas.common import Confidence
from trip_advisor.schemas.pack import CostNote, Pack, RoadNote
from trip_advisor.sites import Endpoint, SiteConfig

TODAY = date(2026, 10, 3)
LONG = (
    "Repairs on the failed sections of the Lagos-Abeokuta expressway began on Monday. "
    "Motorists should expect delays and flooding after heavy rain. Entry to Olumo Rock costs "
    "N2,500 for foreigners. " * 2
)


def site() -> SiteConfig:
    return SiteConfig(
        id="olumo-rock", name="Olumo Rock", city="Abeokuta", state="Ogun",
        origin=Endpoint(query="a"), destination=Endpoint(query="b"), corridors=[],
    )  # fmt: skip


def doc(id="d1", text=LONG, published=date(2026, 9, 20), **kw) -> RawDocument:
    base = {
        "id": id, "site_id": "olumo-rock", "kind": DocKind.NEWS, "source": "bd_serp",
        "publisher": "Punch", "url": f"https://example.com/{id}", "title": "t",
        "published": published, "fetched_at": datetime(2026, 10, 3, tzinfo=UTC), "text": text,
    }  # fmt: skip
    return RawDocument(**{**base, **kw})


def road(**kw) -> dict[str, Any]:
    return {
        "type": "road_note", "summary": "Reports suggest repairs are under way with delays.",
        "quote": "Repairs on the failed sections of the Lagos-Abeokuta expressway began",
        "confidence": "medium", "route": "Lagos-Abeokuta Expressway",
        "rain_sensitivity": "high", **kw,
    }  # fmt: skip


class Fake:
    def __init__(self, by_doc: dict[str, list[dict[str, Any]]]) -> None:
        self.by_doc = by_doc

    def extract(self, d: RawDocument, site_name: str) -> list[dict[str, Any]]:
        out = self.by_doc[d.id]
        if isinstance(out, Exception):
            raise out
        return out


def run(docs, by_doc):
    return structure_docs(site(), docs, Fake(by_doc), TODAY)


def test_valid_record_becomes_pack_record_and_pack_validates():
    res = run([doc()], {"d1": [road()]})
    assert len(res.records) == 1 and isinstance(res.records[0], RoadNote)
    assert res.records[0].source.published == date(2026, 9, 20)
    pack = Pack(
        site_id="olumo-rock", version="t", generated_at=datetime.now(UTC), records=res.records
    )
    Pack.model_validate_json(pack.model_dump_json())


def test_quote_not_in_source_is_rejected():
    res = run([doc()], {"d1": [road(quote="The road is perfectly smooth everywhere")]})
    assert not res.records and res.rejected[0].reason == Reason.QUOTE_NOT_IN_SOURCE


def test_malformed_and_missing_fields_rejected():
    res = run([doc()], {"d1": [{"type": "mystery"}, road(route=None)]})
    assert [r.reason for r in res.rejected] == [Reason.MALFORMED, Reason.MISSING_FIELD]


def test_missing_rain_sensitivity_is_kept_as_medium_low_confidence_and_flagged():
    res = run([doc()], {"d1": [road(rain_sensitivity=None)]})
    rec = res.records[0]
    assert (rec.rain_sensitivity, rec.confidence) == ("medium", Confidence.LOW)
    assert FlagKind.ASSUMED_SENSITIVITY in {f.kind for f in res.flags}


def test_guide_records_capped_at_medium():
    fact = {
        "type": "site_fact", "topic": "opening_hours", "confidence": "high",
        "summary": "The site is open on weekdays from nine to five.",
        "quote": "Repairs on the failed sections of the Lagos-Abeokuta expressway began",
    }  # fmt: skip
    res = run([doc(kind=DocKind.ROUTE_GUIDE)], {"d1": [fact]})
    assert res.records[0].confidence == Confidence.MEDIUM
    assert FlagKind.GUIDE_CAPPED in {f.kind for f in res.flags}


def test_cost_amount_must_appear_in_quote():
    cost = {
        "type": "cost_note", "summary": "Entry reportedly costs N2,500 for foreigners.",
        "quote": "Entry to Olumo Rock costs N2,500 for foreigners", "confidence": "medium",
        "item": "entry_fee_foreign", "amount_ngn_min": 2500, "amount_ngn_max": 2500,
    }  # fmt: skip
    ok = run([doc()], {"d1": [cost]})
    assert isinstance(ok.records[0], CostNote)
    wrong = run([doc()], {"d1": [{**cost, "amount_ngn_min": 5000, "amount_ngn_max": 5000}]})
    assert wrong.rejected[0].reason == Reason.AMOUNT_NOT_IN_QUOTE


def test_extractor_error_is_recorded_and_run_continues():
    res = run([doc("d1"), doc("d2")], {"d1": RuntimeError("boom"), "d2": [road()]})
    assert len(res.records) == 1
    assert res.rejected[0].reason == Reason.EXTRACTOR_ERROR


def test_duplicates_collapse_to_newest():
    docs = [doc("d1", published=date(2026, 9, 1)), doc("d2", published=date(2026, 9, 25))]
    res = run(docs, {"d1": [road()], "d2": [road()]})
    assert len(res.records) == 1 and res.records[0].source.published == date(2026, 9, 25)
    assert res.rejected[0].reason == Reason.DUPLICATE


def test_stale_and_undated_road_notes_flagged_and_downgraded():
    docs = [doc("old", published=date(2026, 3, 1)), doc("none", published=None)]
    res = run(docs, {"old": [road(route="A")], "none": [road(route="B")]})
    assert all(r.confidence == Confidence.LOW for r in res.records)
    kinds = {f.kind for f in res.flags}
    assert {FlagKind.STALE, FlagKind.UNDATED, FlagKind.LOW_CONFIDENCE} <= kinds


def test_headline_only_confidence_capped():
    res = run([doc(text="Kara Bridge repairs cripple Lagos-Abeokuta expressway Punch")],
              {"d1": [road(quote="repairs cripple Lagos-Abeokuta expressway")]})  # fmt: skip
    assert res.records[0].confidence == Confidence.LOW
    assert FlagKind.HEADLINE_ONLY in {f.kind for f in res.flags}


def test_review_sample_written(tmp_path):
    res = run([doc()], {"d1": [road()]})
    write_review_sample(res, tmp_path / "review.md")
    assert res.records[0].id in (tmp_path / "review.md").read_text()


def test_remark_about_the_document_is_rejected():
    meta = {
        "type": "site_fact", "topic": "history", "confidence": "low",
        "summary": "The document is a travel guide to Akure and has no specific information.",
        "quote": "Repairs on the failed sections of the Lagos-Abeokuta expressway began",
    }  # fmt: skip
    res = run([doc()], {"d1": [meta]})
    assert not res.records and res.rejected[0].reason == Reason.NO_CONTENT


def test_undated_guide_fact_not_flagged_but_undated_road_note_is():
    fact = {
        "type": "site_fact", "topic": "history", "confidence": "medium",
        "summary": "The town grew around a historic hilltop settlement.",
        "quote": "Repairs on the failed sections of the Lagos-Abeokuta expressway began",
    }  # fmt: skip
    res = run([doc(published=None)], {"d1": [fact, road()]})
    flagged = {f.record_id: f.kind for f in res.flags if f.kind == FlagKind.UNDATED}
    assert len(flagged) == 1 and next(iter(flagged)).startswith("road-note")
