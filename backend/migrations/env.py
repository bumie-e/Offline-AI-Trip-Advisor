from alembic import context
from sqlalchemy import create_engine

from trip_advisor.config import settings
from trip_advisor.db.models import Base
from trip_advisor.db.session import normalize_url

target_metadata = Base.metadata


def _url() -> str:
    # `-x url=...` lets tests and one-off runs override the configured database.
    return normalize_url(
        context.get_x_argument(as_dictionary=True).get("url") or settings.database_url
    )


def run_migrations_online() -> None:
    url = _url()
    if not url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
