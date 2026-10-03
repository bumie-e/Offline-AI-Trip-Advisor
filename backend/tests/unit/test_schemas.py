import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from trip_advisor.schemas.delta import Delta
from trip_advisor.schemas.export import MODELS, export_schemas
from trip_advisor.schemas.itinerary import Advice, TripRequest
from trip_advisor.schemas.pack import Pack, RoadNote
from trip_advisor.schemas.reports import RoadReport

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_pack_fixture_validates():
    pack = Pack.model_validate(load("pack.sample.json"))
    assert isinstance(pack.records[0], RoadNote)
    assert pack.records[1].type == "contact"


def test_delta_fixture_validates():
    delta = Delta.model_validate(load("delta.sample.json"))
    assert delta.weather[0].rain_probability == 0.8


def test_advice_fixture_validates():
    advice = Advice.model_validate(load("advice.sample.json"))
    assert advice.cited_ids == ["road-note-001", "weather-2026-10-14"]


def test_pack_rejects_unknown_record_type():
    data = load("pack.sample.json")
    data["records"][0]["type"] = "mystery"
    with pytest.raises(ValidationError):
        Pack.model_validate(data)


def test_pack_rejects_missing_source():
    data = load("pack.sample.json")
    del data["records"][0]["source"]
    with pytest.raises(ValidationError):
        Pack.model_validate(data)


def test_rain_probability_bounds():
    data = load("delta.sample.json")
    data["weather"][0]["rain_probability"] = 1.5
    with pytest.raises(ValidationError):
        Delta.model_validate(data)


def test_unknown_fields_rejected():
    data = load("advice.sample.json")
    data["verdict"] = "safe"
    with pytest.raises(ValidationError):
        Advice.model_validate(data)


def test_trip_request_group_size_bounds():
    base = {
        "site_id": "olumo-rock",
        "start_city": "Lagos",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "group_size": 0,
    }
    with pytest.raises(ValidationError):
        TripRequest.model_validate(base)


def test_report_note_length_limit():
    with pytest.raises(ValidationError):
        RoadReport.model_validate(
            {
                "id": "8f14e45f-ceea-4672-9a6f-3c1f1d3f7a10",
                "reported_at": "2026-10-03T08:00:00Z",
                "site_id": "olumo-rock",
                "route_id": "lagos-abeokuta-road",
                "condition": "slow",
                "note": "x" * 501,
            }
        )


def test_export_writes_all_schemas(tmp_path):
    written = export_schemas(tmp_path)
    assert len(written) == len(MODELS)
    for path in written:
        assert json.loads(path.read_text())["type"] == "object"
