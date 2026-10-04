import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from trip_advisor.api import deps
from trip_advisor.db.models import Base, ItineraryCacheRow
from trip_advisor.main import create_app
from trip_advisor.pipeline.generate.writer import WriterOutput
from trip_advisor.schemas.itinerary import Advice, Severity, Verdict
from trip_advisor.schemas.pack import TripPack

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
BODY = {"site_id": "olumo-rock", "start_city": "Lagos", "arrival_airport": "LOS",
        "start_date": "2026-10-14", "end_date": "2026-10-14", "group_size": 2}  # fmt: skip


@pytest.fixture
def data(tmp_path: Path) -> Path:
    (tmp_path / "sites").mkdir()
    shutil.copy(REPO / "data/sites/olumo-rock.toml", tmp_path / "sites")
    shutil.copytree(REPO / "data/packs/olumo-rock", tmp_path / "packs" / "olumo-rock")
    (tmp_path / "deltas").mkdir()
    shutil.copy(REPO / "data/deltas/olumo-rock.json", tmp_path / "deltas")
    return tmp_path


@pytest.fixture
def db() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


class CountingWriter:
    """Stands in for the model: cites a real weather ID and writes its own summary."""

    def __init__(
        self, summary="Rain on 14 Oct may slow the drive, so allow extra time.", fail=False
    ):
        self.calls, self.summary, self.fail = 0, summary, fail

    def write(self, inp, findings, outline):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model is down")
        weather_ids = sorted(i for i in inp.known_ids() if i.startswith("weather-"))
        return WriterOutput(
            verdict=Verdict.GO_WITH_CHANGES,
            summary=self.summary,
            verdict_reasons=[
                Advice(
                    changed=True,
                    severity=Severity.HIGH,
                    cited_ids=weather_ids[:1],
                    advice="MODEL TEXT: reports suggest rain may slow the drive.",
                )
            ],
        )


def make_client(data, db, writer, cap=200):
    app = create_app()

    def session():
        with db() as s:
            yield s

    app.dependency_overrides[deps.data_dir] = lambda: data
    app.dependency_overrides[deps.optional_db_session] = session
    app.dependency_overrides[deps.now] = lambda: NOW
    app.dependency_overrides[deps.writer] = lambda: writer
    app.dependency_overrides[deps.daily_cap] = lambda: cap
    return TestClient(app)


def test_download_contains_pack_delta_and_the_models_summary_and_advice(data, db):
    w = CountingWriter()
    r = make_client(data, db, w).post("/pack/olumo-rock", json=BODY)
    assert r.status_code == 200
    trip = TripPack.model_validate(r.json())
    assert trip.advice_source == "model"
    assert trip.itinerary.summary == "Rain on 14 Oct may slow the drive, so allow extra time."
    assert any("MODEL TEXT" in a.advice for a in trip.itinerary.verdict_reasons)
    assert trip.pack.site_id == "olumo-rock" and trip.pack.records
    assert trip.delta.generated_at.isoformat().startswith("2026-10-04")  # what the advice used


def test_identical_request_is_served_from_the_cache_without_calling_the_model(data, db):
    w = CountingWriter()
    client = make_client(data, db, w)
    first = client.post("/pack/olumo-rock", json=BODY).json()
    second = client.post("/pack/olumo-rock", json=BODY).json()
    assert w.calls == 1 and second["advice_source"] == "model"
    assert second["itinerary"] == first["itinerary"]
    # A different trip is a different key.
    client.post("/pack/olumo-rock", json={**BODY, "group_size": 3})
    assert w.calls == 2


def test_daily_cap_stops_model_calls_and_falls_back_to_rule_text(data, db):
    w = CountingWriter()
    client = make_client(data, db, w, cap=1)
    assert client.post("/pack/olumo-rock", json=BODY).json()["advice_source"] == "model"
    capped = client.post("/pack/olumo-rock", json={**BODY, "group_size": 4}).json()
    assert capped["advice_source"] == "rules" and w.calls == 1
    assert capped["itinerary"]["summary"]  # the template summary is still there


def test_model_failure_still_returns_rule_based_advice(data, db):
    r = make_client(data, db, CountingWriter(fail=True)).post("/pack/olumo-rock", json=BODY)
    assert r.status_code == 200 and r.json()["advice_source"] == "rules"
    with db() as s:  # a fallback is not cached, so the next request can try the model again
        assert s.scalar(select(func.count()).select_from(ItineraryCacheRow)) == 0


def test_no_model_configured_gives_rules(data, db):
    r = make_client(data, db, None).post("/pack/olumo-rock", json=BODY).json()
    assert r["advice_source"] == "rules" and r["itinerary"]["summary"]


def test_ai_false_skips_the_model(data, db):
    w = CountingWriter()
    r = make_client(data, db, w).post("/pack/olumo-rock?ai=false", json=BODY).json()
    assert r["advice_source"] == "rules" and w.calls == 0


def test_summary_with_an_unsourced_figure_is_replaced_by_the_template(data, db):
    w = CountingWriter(summary="There is a 99% chance of rain, so avoid it.")
    r = make_client(data, db, w).post("/pack/olumo-rock", json=BODY).json()
    assert "99%" not in r["itinerary"]["summary"] and r["advice_source"] == "model"


def test_summary_with_banned_wording_is_replaced(data, db):
    w = CountingWriter(summary="The road is unsafe after rain.")
    r = make_client(data, db, w).post("/pack/olumo-rock", json=BODY).json()
    assert "unsafe" not in r["itinerary"]["summary"]


def test_database_down_means_no_spending_so_rule_text(data):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    broken = sessionmaker(engine)  # no tables: the cache and the cap cannot be checked
    w = CountingWriter()
    r = make_client(data, broken, w).post("/pack/olumo-rock", json=BODY).json()
    assert r["advice_source"] == "rules" and w.calls == 0


def test_without_a_database_the_model_still_works_for_local_runs(data):
    app = create_app()
    w = CountingWriter()
    app.dependency_overrides[deps.data_dir] = lambda: data
    app.dependency_overrides[deps.optional_db_session] = lambda: None
    app.dependency_overrides[deps.writer] = lambda: w
    r = TestClient(app).post("/pack/olumo-rock", json=BODY).json()
    assert r["advice_source"] == "model"


def test_itinerary_endpoint_uses_the_model_by_default_and_ai_false_turns_it_off(data, db):
    w = CountingWriter()
    client = make_client(data, db, w)
    assert "MODEL TEXT" in " ".join(
        a["advice"] for a in client.post("/itinerary", json=BODY).json()["verdict_reasons"]
    )
    off = client.post("/itinerary?ai=false", json={**BODY, "group_size": 5}).json()
    assert "MODEL TEXT" not in " ".join(a["advice"] for a in off["verdict_reasons"])


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/pack/olumo-rock", {**BODY, "site_id": "osun-osogbo"}, 422),
        ("/pack/nowhere", {**BODY, "site_id": "nowhere"}, 404),
        ("/pack/olumo-rock", {**BODY, "end_date": "2026-10-01"}, 422),
    ],
)
def test_download_rejects_bad_requests(data, db, path, body, status):
    assert make_client(data, db, CountingWriter()).post(path, json=body).status_code == status


def test_model_requests_are_rate_limited_per_connection(data, db, monkeypatch):
    monkeypatch.setattr("trip_advisor.api.limits.settings.model_requests_per_hour", 2)
    w = CountingWriter()
    client = make_client(data, db, w)
    codes = [
        client.post("/pack/olumo-rock", json={**BODY, "group_size": n}).status_code
        for n in (1, 2, 3)
    ]
    assert codes == [200, 200, 429]
    # Rule-only requests do not spend the allowance.
    assert client.post("/pack/olumo-rock?ai=false", json=BODY).status_code == 200


def test_yesterdays_calls_do_not_count_against_today(data, db):
    with db() as s:
        s.add(ItineraryCacheRow(key="old", site_id="olumo-rock", payload="{}",
                                created_at=NOW - timedelta(days=1)))  # fmt: skip
        s.commit()
    r = make_client(data, db, CountingWriter(), cap=1).post("/pack/olumo-rock", json=BODY).json()
    assert r["advice_source"] == "model"
