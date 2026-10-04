from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from trip_advisor.config import settings
from trip_advisor.db.session import DatabaseNotConfigured
from trip_advisor.db.session import get_session as _get_session
from trip_advisor.pipeline.generate.writer import ItineraryWriter
from trip_advisor.sites import SiteConfig, list_sites, load_site


def data_dir() -> Path:
    return settings.data_dir


def now() -> datetime:
    return datetime.now(UTC)


def db_session() -> Iterator[Session]:
    try:
        yield from _get_session()
    except DatabaseNotConfigured as exc:
        raise HTTPException(
            503, "Reports are not available: the database is not configured"
        ) from exc


def optional_db_session() -> Iterator[Session | None]:
    """A session when the database is configured, else None. For reads that have a file fallback."""
    try:
        yield from _get_session()
    except DatabaseNotConfigured:
        yield None


def model_name() -> str:
    return settings.generation_model


def daily_cap() -> int:
    return settings.model_calls_per_day


def writer() -> ItineraryWriter | None:
    """The model writer, only when a key is configured. Requests opt in with `?ai=true`."""
    if not settings.llm_api_key:
        return None
    from trip_advisor.pipeline.generate.writer import AnthropicWriter

    return AnthropicWriter(settings.llm_api_key, settings.generation_model)


def site_or_404(site_id: str, base: Path = Depends(data_dir)) -> SiteConfig:
    if site_id not in list_sites(base / "sites"):
        raise HTTPException(404, f"Unknown place {site_id!r}")
    return load_site(site_id, base / "sites")
