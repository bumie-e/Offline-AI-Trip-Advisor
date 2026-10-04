import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from trip_advisor import cli
from trip_advisor.api import deps
from trip_advisor.config import settings
from trip_advisor.db import session as db_session_module
from trip_advisor.db.models import Base, PublishedDeltaRow, RateLimitRow, RoadReportRow
from trip_advisor.main import create_app
from trip_advisor.schemas.delta import Delta, WeatherEntry
from trip_advisor.services import ratelimit
from trip_advisor.services.deltas import latest_published, publish_delta

from .test_api import NOW, data  # noqa: F401  (pytest fixture)


def make_engine(*, skip: tuple[str, ...] = ()):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    tables = [t for name, t in Base.metadata.tables.items() if name not in skip]
    Base.metadata.create_all(engine, tables=tables)
    return engine


def delta_at(when: datetime, rain: float = 0.5) -> Delta:
    return Delta(
        generated_at=when,
        weather=[WeatherEntry(date=when.date(), area="Abeokuta", rain_probability=rain)],
    )


def build_client(data, engine, at=NOW) -> TestClient:  # noqa: F811
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[deps.data_dir] = lambda: data
    app.dependency_overrides[deps.db_session] = session
    app.dependency_overrides[deps.optional_db_session] = session
    app.dependency_overrides[deps.now] = lambda: at
    return TestClient(app)


# ---- published deltas ------------------------------------------------------------------------


def test_publish_stores_then_refuses_older_or_equal_deltas():
    with Session(make_engine()) as s:
        assert publish_delta(s, "olumo-rock", delta_at(NOW), now=NOW)
        assert not publish_delta(s, "olumo-rock", delta_at(NOW), now=NOW)  # equal
        assert not publish_delta(s, "olumo-rock", delta_at(NOW - timedelta(hours=1)), now=NOW)
        stored = latest_published(s, "olumo-rock")
        assert stored and stored.generated_at == NOW


def test_publish_replaces_with_a_newer_delta():
    with Session(make_engine()) as s:
        publish_delta(s, "olumo-rock", delta_at(NOW, 0.2), now=NOW)
        later = NOW + timedelta(hours=6)
        assert publish_delta(s, "olumo-rock", delta_at(later, 0.9), now=later)
        stored = latest_published(s, "olumo-rock")
        assert stored and stored.weather[0].rain_probability == 0.9
        assert s.scalar(select(func.count()).select_from(PublishedDeltaRow)) == 1


def test_latest_published_is_none_for_an_unknown_site():
    with Session(make_engine()) as s:
        assert latest_published(s, "nowhere") is None


# ---- the delta endpoint ----------------------------------------------------------------------


def write_bundled(folder, when: datetime, rain: float):
    (folder / "deltas" / "olumo-rock.json").write_text(delta_at(when, rain).model_dump_json())


def test_api_serves_the_published_delta_when_it_is_newer_than_the_bundled_one(data):  # noqa: F811
    write_bundled(data, NOW - timedelta(days=2), 0.1)
    engine = make_engine()
    with Session(engine) as s:
        publish_delta(s, "olumo-rock", delta_at(NOW, 0.9), now=NOW)
    body = build_client(data, engine).get("/delta/olumo-rock").json()
    assert body["weather"][0]["rain_probability"] == 0.9


def test_api_serves_the_bundled_delta_when_it_is_newer(data):  # noqa: F811
    write_bundled(data, NOW, 0.3)
    engine = make_engine()
    with Session(engine) as s:
        publish_delta(s, "olumo-rock", delta_at(NOW - timedelta(days=1), 0.9), now=NOW)
    body = build_client(data, engine).get("/delta/olumo-rock").json()
    assert body["weather"][0]["rain_probability"] == 0.3


def test_api_works_when_the_published_table_does_not_exist_yet(data):  # noqa: F811
    """The migration may not be applied yet: the endpoint must fall back, not return a 500."""
    write_bundled(data, NOW, 0.3)
    engine = make_engine(skip=("published_deltas",))
    resp = build_client(data, engine).get("/delta/olumo-rock")
    assert resp.status_code == 200 and resp.json()["weather"][0]["rain_probability"] == 0.3


def test_api_works_with_no_database_configured(data):  # noqa: F811
    write_bundled(data, NOW, 0.3)
    app = create_app()
    app.dependency_overrides[deps.data_dir] = lambda: data
    # No override for optional_db_session: the autouse conftest blanks DATABASE_URL.
    resp = TestClient(app).get("/delta/olumo-rock")
    assert resp.status_code == 200


def test_api_404_when_there_is_no_delta_anywhere(data):  # noqa: F811
    (data / "deltas" / "olumo-rock.json").unlink()
    assert build_client(data, make_engine()).get("/delta/olumo-rock").status_code == 404


# ---- rate limit ------------------------------------------------------------------------------


def report(**kw):
    base = {
        "id": str(uuid.uuid4()), "reported_at": (NOW - timedelta(hours=1)).isoformat(),
        "site_id": "olumo-rock", "route_id": "primary", "condition": "slow",
    }  # fmt: skip
    return {**base, **kw}


@pytest.fixture
def limited(monkeypatch):
    monkeypatch.setattr(settings, "report_items_per_hour", 5)
    monkeypatch.setattr(settings, "rate_limit_secret", "test-secret")


def post(client, n, ip="203.0.113.7", path="/reports/road"):
    return client.post(path, json=[report() for _ in range(n)], headers={"x-forwarded-for": ip})


def test_batches_over_the_hourly_allowance_get_429_with_retry_after(data, limited):  # noqa: F811
    client = build_client(data, make_engine(), at=NOW.replace(minute=15))
    assert post(client, 3).status_code == 200
    assert post(client, 2).status_code == 200  # exactly 5 items so far
    over = post(client, 1)
    assert over.status_code == 429
    assert 0 < int(over.headers["retry-after"]) <= 3600


def test_a_rejected_batch_stores_nothing(data, limited):  # noqa: F811
    engine = make_engine()
    client = build_client(data, engine, at=NOW.replace(minute=15))
    post(client, 5)
    assert post(client, 3).status_code == 429
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(RoadReportRow)) == 5


def test_each_client_has_its_own_allowance(data, limited):  # noqa: F811
    client = build_client(data, make_engine(), at=NOW.replace(minute=15))
    assert post(client, 5, ip="198.51.100.1").status_code == 200
    assert post(client, 5, ip="198.51.100.2").status_code == 200
    assert post(client, 1, ip="198.51.100.1").status_code == 429


def test_the_allowance_resets_in_the_next_hour(data, limited):  # noqa: F811
    engine = make_engine()
    assert post(build_client(data, engine, at=NOW.replace(minute=15)), 5).status_code == 200
    assert post(build_client(data, engine, at=NOW.replace(minute=15)), 1).status_code == 429
    later = NOW.replace(minute=15) + timedelta(hours=1)
    assert post(build_client(data, engine, at=later), 5).status_code == 200


def test_every_report_endpoint_is_limited(data, limited):  # noqa: F811
    client = build_client(data, make_engine(), at=NOW.replace(minute=15))
    post(client, 5, path="/reports/road")
    ratings = [
        {"id": str(uuid.uuid4()), "rated_at": (NOW - timedelta(hours=1)).isoformat(),
         "site_id": "olumo-rock", "helpful": True}
    ]  # fmt: skip
    resp = client.post("/reports/ratings", json=ratings, headers={"x-forwarded-for": "203.0.113.7"})
    assert resp.status_code == 429  # the allowance is shared across the report endpoints


def test_the_limiter_fails_open_if_its_table_is_missing(data, limited):  # noqa: F811
    engine = make_engine(skip=("rate_limits",))
    client = build_client(data, engine, at=NOW.replace(minute=15))
    for _ in range(3):  # far more than the limit of 5 items if it were counting
        assert post(client, 5).status_code == 200


def test_the_stored_key_never_contains_the_address():
    key = ratelimit.client_key("203.0.113.7", NOW, "s3cret")
    assert "203" not in key and len(key) == 32
    assert key == ratelimit.client_key("203.0.113.7", NOW, "s3cret")  # stable within the day
    assert key != ratelimit.client_key("203.0.113.7", NOW + timedelta(days=1), "s3cret")
    assert key != ratelimit.client_key("203.0.113.8", NOW, "s3cret")
    assert key != ratelimit.client_key("203.0.113.7", NOW, "other-secret")


def test_the_first_forwarded_address_is_used(data, limited):  # noqa: F811
    engine = make_engine()
    client = build_client(data, engine, at=NOW.replace(minute=15))
    client.post(
        "/reports/road", json=[report()], headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
    )
    expected = ratelimit.client_key("203.0.113.7", NOW.replace(minute=15), "test-secret")
    with Session(engine) as s:
        assert s.scalar(select(RateLimitRow.key)) == expected


def test_old_counters_are_purged_and_recent_ones_kept():
    with Session(make_engine()) as s:
        hour = NOW.replace(minute=0)
        for age, key in ((timedelta(days=3), "old"), (timedelta(hours=2), "recent")):
            s.add(RateLimitRow(key=key, window_start=hour - age, count=1))
        s.commit()
        assert ratelimit.purge_old(s, now=NOW) == 1
        assert s.scalars(select(RateLimitRow.key)).all() == ["recent"]


# ---- publishing from the command line --------------------------------------------------------


def test_cli_publish_stores_a_delta_with_weather(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(db_session_module, "get_engine", lambda: engine)
    assert cli._publish_delta("olumo-rock", delta_at(datetime.now(UTC))) is True
    with Session(engine) as s:
        assert latest_published(s, "olumo-rock") is not None


def test_cli_publish_refuses_a_delta_without_weather(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(db_session_module, "get_engine", lambda: engine)
    empty = Delta(generated_at=datetime.now(UTC))
    assert cli._publish_delta("olumo-rock", empty) is False
    with Session(engine) as s:
        assert latest_published(s, "olumo-rock") is None


def test_cli_publish_reports_a_missing_database_url():
    assert (
        cli._publish_delta("olumo-rock", delta_at(datetime.now(UTC))) is False
    )  # blanked by conftest


def test_cli_publish_reports_a_database_error_without_leaking_the_url(monkeypatch, capsys):
    engine = make_engine(skip=("published_deltas",))  # table missing, as before the migration
    monkeypatch.setattr(db_session_module, "get_engine", lambda: engine)
    assert cli._publish_delta("olumo-rock", delta_at(datetime.now(UTC))) is False
    err = capsys.readouterr().err
    assert "database error" in err and "sqlite" not in err
