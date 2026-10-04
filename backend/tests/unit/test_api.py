import json
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from trip_advisor.api import deps
from trip_advisor.db.models import AdviceRatingRow, Base, RoadReportRow, SiteStatusReportRow
from trip_advisor.main import create_app
from trip_advisor.services.reports import purge_older_than

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


@pytest.fixture
def data(tmp_path: Path) -> Path:
    (tmp_path / "sites").mkdir()
    shutil.copy(REPO / "data/sites/olumo-rock.toml", tmp_path / "sites")
    pack = tmp_path / "packs" / "olumo-rock"
    pack.mkdir(parents=True)
    shutil.copy(FIXTURES / "pack.sample.json", pack / "pack.json")
    # pack.json for olumo-rock plus the real slim routes, if built; else a minimal one.
    real = REPO / "data/packs/olumo-rock/routes.json"
    if real.exists():
        shutil.copy(real, pack / "routes.json")
    (tmp_path / "deltas").mkdir()
    shutil.copy(FIXTURES / "delta.sample.json", tmp_path / "deltas" / "olumo-rock.json")
    return tmp_path


@pytest.fixture
def db() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def client(data: Path, db: sessionmaker[Session]) -> TestClient:
    app = create_app()

    def session():
        with db() as s:
            yield s

    app.dependency_overrides[deps.data_dir] = lambda: data
    app.dependency_overrides[deps.db_session] = session
    app.dependency_overrides[deps.now] = lambda: NOW
    app.dependency_overrides[deps.writer] = lambda: None
    return TestClient(app)


def road_report(**kw):
    base = {
        "id": str(uuid.uuid4()), "reported_at": (NOW - timedelta(hours=2)).isoformat(),
        "site_id": "olumo-rock", "route_id": "primary", "condition": "slow",
        "lat": 7.167195, "lon": 3.342584, "note": "",
    }  # fmt: skip
    return {**base, **kw}


def trip(**kw):
    base = {"site_id": "olumo-rock", "start_city": "Lagos", "arrival_airport": "LOS",
            "start_date": "2026-10-14", "end_date": "2026-10-14", "group_size": 2}  # fmt: skip
    return {**base, **kw}


# --- places, pack, delta -------------------------------------------------------------------


def test_places_list_and_detail(client):
    listed = client.get("/places").json()
    assert [p["id"] for p in listed] == ["olumo-rock"]
    assert listed[0]["pack_version"] == "0.0.1-sample" and listed[0]["pack_bytes"] > 0
    assert client.get("/places/olumo-rock").json()["city"] == "Abeokuta"
    assert client.get("/places/nowhere").status_code == 404


def test_pack_served_with_etag_and_304_when_unchanged(client):
    r = client.get("/pack/olumo-rock")
    assert r.status_code == 200 and r.headers["etag"] == '"0.0.1-sample"'
    assert r.json()["site_id"] == "olumo-rock"
    again = client.get("/pack/olumo-rock", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


def test_pack_and_delta_404_cases(client, data):
    assert client.get("/pack/nowhere").status_code == 404
    (data / "packs" / "olumo-rock" / "pack.json").unlink()
    assert client.get("/pack/olumo-rock").status_code == 404
    (data / "deltas" / "olumo-rock.json").unlink()
    assert client.get("/delta/olumo-rock").status_code == 404


def test_delta_served(client):
    assert client.get("/delta/olumo-rock").json()["weather"][0]["area"] == "Abeokuta"


# --- itinerary -----------------------------------------------------------------------------


def test_itinerary_is_generated_from_the_stored_pack_and_delta(client):
    r = client.post("/itinerary", json=trip())
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] in {"go", "go_with_changes", "not_advised"}
    assert body["site_id"] == "olumo-rock" and body["verdict_reasons"]


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"site_id": "nowhere"}, 404),
        ({"end_date": "2026-10-10"}, 422),
        ({"end_date": "2026-12-30"}, 422),
        ({"group_size": 0}, 422),
    ],
)
def test_itinerary_rejects_bad_requests(client, changes, status):
    assert client.post("/itinerary", json=trip(**changes)).status_code == status


def test_itinerary_is_not_stored(client, db):
    client.post("/itinerary", json=trip())
    with db() as s:
        counts = [
            s.scalar(select(func.count()).select_from(t))
            for t in (RoadReportRow, SiteStatusReportRow, AdviceRatingRow)
        ]
    assert counts == [0, 0, 0]


# --- reports -------------------------------------------------------------------------------


def routes_known() -> bool:
    return (REPO / "data/packs/olumo-rock/routes.json").exists()


def test_road_report_is_stored_with_coarse_location_and_redacted_note(client, db):
    rep = road_report(note="Flooded, call +234 803 123 4567")
    r = client.post("/reports/road", json=[rep])
    assert r.status_code == 200 and r.json()["accepted"] == [rep["id"]]
    with db() as s:
        row = s.scalars(select(RoadReportRow)).one()
    assert (row.lat, row.lon) == (7.17, 3.34)
    assert "803" not in row.note and "[removed]" in row.note


def test_retrying_a_sync_is_safe_and_reports_duplicates(client, db):
    batch = [road_report(), road_report()]
    first = client.post("/reports/road", json=batch).json()
    second = client.post("/reports/road", json=batch).json()
    assert len(first["accepted"]) == 2 and second["accepted"] == []
    assert sorted(second["duplicates"]) == sorted(r["id"] for r in batch)
    with db() as s:
        assert s.scalar(select(func.count()).select_from(RoadReportRow)) == 2


def test_same_id_twice_in_one_batch_is_stored_once(client, db):
    rep = road_report()
    r = client.post("/reports/road", json=[rep, rep]).json()
    assert r["accepted"] == [rep["id"]] and r["duplicates"] == [rep["id"]]


def test_bad_reports_are_rejected_individually_not_the_whole_batch(client, db):
    good = road_report()
    future = road_report(reported_at=(NOW + timedelta(days=3)).isoformat())
    old = road_report(reported_at=(NOW - timedelta(days=90)).isoformat())
    r = client.post("/reports/road", json=[good, future, old]).json()
    assert r["accepted"] == [good["id"]]
    assert {x["id"] for x in r["rejected"]} == {future["id"], old["id"]}


@pytest.mark.skipif(not routes_known(), reason="needs built routes")
def test_unknown_route_is_rejected(client):
    rep = road_report(route_id="made-up")
    r = client.post("/reports/road", json=[rep]).json()
    assert r["rejected"][0]["reason"].startswith("unknown route")


def test_unknown_site_is_404_and_oversized_batch_is_422(client):
    assert client.post("/reports/road", json=[road_report(site_id="nowhere")]).status_code == 404
    assert client.post("/reports/road", json=[road_report() for _ in range(51)]).status_code == 422


def test_naive_timestamp_is_treated_as_utc(client):
    rep = road_report(reported_at="2026-10-04T07:00:00")
    assert client.post("/reports/road", json=[rep]).json()["accepted"] == [rep["id"]]


def test_site_status_and_ratings(client, db):
    status = {"id": str(uuid.uuid4()), "reported_at": NOW.isoformat(), "site_id": "olumo-rock",
              "status": "open", "note": "Guide at the gate: ade@mail.com"}  # fmt: skip
    rating = {"id": str(uuid.uuid4()), "rated_at": NOW.isoformat(), "site_id": "olumo-rock",
              "helpful": True, "comment": "great"}  # fmt: skip
    assert client.post("/reports/site-status", json=[status]).json()["accepted"] == [status["id"]]
    assert client.post("/reports/ratings", json=[rating]).json()["accepted"] == [rating["id"]]
    with db() as s:
        assert "@" not in s.scalars(select(SiteStatusReportRow)).one().note
        assert s.scalars(select(AdviceRatingRow)).one().helpful is True


def test_invalid_payload_values_are_422(client):
    assert client.post("/reports/road", json=[road_report(condition="great")]).status_code == 422
    assert client.post("/reports/road", json=[road_report(lat=123)]).status_code == 422


def test_reports_unavailable_when_database_not_configured(data, monkeypatch):
    monkeypatch.setattr("trip_advisor.db.session.settings.database_url", "")
    from trip_advisor.db.session import get_engine

    get_engine.cache_clear()
    app = create_app()
    app.dependency_overrides[deps.data_dir] = lambda: data
    r = TestClient(app).post("/reports/road", json=[road_report()])
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


# --- retention and migration ---------------------------------------------------------------


def test_purge_removes_only_rows_older_than_the_retention_window(client, db):
    old, new = road_report(), road_report()
    client.post("/reports/road", json=[old])
    client.post("/reports/road", json=[new])
    with db() as s:
        row = s.get(RoadReportRow, uuid.UUID(old["id"]))
        row.received_at = NOW - timedelta(days=400)
        s.commit()
        assert purge_older_than(s, 365, now=NOW) == 1
        assert s.scalar(select(func.count()).select_from(RoadReportRow)) == 1


def test_migration_creates_the_same_tables_as_the_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.cmd_opts = type("O", (), {"x": [f"url={url}"]})()
    command.upgrade(cfg, "head")
    from sqlalchemy import inspect

    migrated = inspect(create_engine(url))
    for table in Base.metadata.sorted_tables:
        assert {c["name"] for c in migrated.get_columns(table.name)} == {
            c.name for c in table.columns
        }
    command.downgrade(cfg, "base")


def test_pack_json_fixture_is_valid_json():
    json.loads((FIXTURES / "pack.sample.json").read_text())


def test_database_failure_is_a_clean_503_not_a_stack_trace(data):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    broken = sessionmaker(engine)  # tables were never created: the migration was not run

    def session():
        with broken() as s:
            yield s

    app = create_app()
    app.dependency_overrides[deps.data_dir] = lambda: data
    app.dependency_overrides[deps.db_session] = session
    r = TestClient(app, raise_server_exceptions=False).post("/reports/road", json=[road_report()])
    assert r.status_code == 503 and r.json() == {"detail": "Reports are temporarily unavailable"}
