import pytest

from trip_advisor.config import settings
from trip_advisor.db.session import get_engine


@pytest.fixture(autouse=True)
def never_touch_the_real_database(monkeypatch: pytest.MonkeyPatch):
    """`.env` holds the real DATABASE_URL, and the settings object reads it. No test may reach
    that database: tests that need one pass in their own (an in-memory SQLite)."""
    monkeypatch.setattr(settings, "database_url", "")
    get_engine.cache_clear()
    yield
    get_engine.cache_clear()
