"""Per-client request limit for the anonymous report endpoints.

The app stores no identity and no IP address, so the limiter does not either: the key is an
HMAC of the address with a secret and the current day, which cannot be turned back into an
address and stops matching after midnight. Counts live in the database because serverless
instances share no memory.
"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from trip_advisor.db.models import RateLimitRow

WINDOW = timedelta(hours=1)
KEEP = timedelta(days=2)


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry in {retry_after}s")
        self.retry_after = retry_after


def client_key(address: str, now: datetime, secret: str) -> str:
    message = f"{address}|{now.astimezone(UTC):%Y-%m-%d}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def _window_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _add(session: Session, key: str, window: datetime, items: int) -> int:
    """Atomically add to this window's counter and return the new total."""
    values = {"key": key, "window_start": window, "count": items}
    keys = [RateLimitRow.key, RateLimitRow.window_start]
    bump = {"count": RateLimitRow.count + items}
    if session.get_bind().dialect.name == "postgresql":
        pg = pg_insert(RateLimitRow).values(values)
        result = session.execute(
            pg.on_conflict_do_update(index_elements=keys, set_=bump).returning(RateLimitRow.count)
        )
    else:  # SQLite, used in tests, supports the same upsert
        lite = sqlite_insert(RateLimitRow).values(values)
        result = session.execute(
            lite.on_conflict_do_update(index_elements=keys, set_=bump).returning(RateLimitRow.count)
        )
    total = int(result.scalar_one())
    session.commit()
    return total


def enforce(session: Session, key: str, items: int, *, now: datetime, limit: int) -> None:
    """Count `items` against the key's hourly allowance. Raises RateLimited when over it."""
    window = _window_start(now)
    if _add(session, key, window, items) > limit:
        retry = int((window + WINDOW - now.astimezone(UTC)).total_seconds())
        raise RateLimited(max(retry, 1))


def purge_old(session: Session, *, now: datetime) -> int:
    cutoff = _window_start(now) - KEEP
    removed = session.execute(delete(RateLimitRow).where(RateLimitRow.window_start < cutoff))
    session.commit()
    return int(removed.rowcount)  # type: ignore[attr-defined]
