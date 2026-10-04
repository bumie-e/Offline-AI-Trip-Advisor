"""Database engine and session. Built for Supabase Postgres behind its connection pooler."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from trip_advisor.config import settings


class DatabaseNotConfigured(RuntimeError):
    pass


def normalize_url(url: str) -> str:
    """Use the psycopg 3 driver for any plain postgres URL (Supabase hands out `postgresql://`)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_engine() -> Engine:
    if not settings.database_url:
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    url = normalize_url(settings.database_url)
    if url.startswith("postgresql"):
        # Serverless functions open short-lived connections. Supabase's transaction pooler
        # (pgbouncer) does the pooling, so keep none here and avoid server-side prepared statements.
        return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})
    return create_engine(url)


def get_session() -> Iterator[Session]:
    with sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session
