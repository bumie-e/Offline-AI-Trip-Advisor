"""Rate limit for the report endpoints."""

import hashlib
import logging
from datetime import datetime

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from trip_advisor.config import settings
from trip_advisor.services import ratelimit

log = logging.getLogger(__name__)


def client_address(request: Request) -> str:
    """The caller's address. On Vercel the first X-Forwarded-For entry is set by the platform."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _secret() -> str:
    # Set RATE_LIMIT_SECRET in production. The fallback only keeps local runs working.
    return settings.rate_limit_secret or hashlib.sha256(settings.database_url.encode()).hexdigest()


def enforce_rate_limit(
    db: Session,
    request: Request,
    items: int,
    at: datetime,
    *,
    scope: str = "",
    limit: int | None = None,
) -> None:
    """Count the batch against the caller's hourly allowance, or answer 429.

    Fails open: if the counter cannot be updated (table missing, database hiccup) the reports go
    through, because losing a traveller's report is worse than letting one extra batch in.
    """
    address = client_address(request) + (f"|{scope}" if scope else "")  # no scope: unchanged key
    key = ratelimit.client_key(address, at, _secret())
    try:
        ratelimit.enforce(db, key, items, now=at, limit=limit or settings.report_items_per_hour)
    except ratelimit.RateLimited as exc:
        raise HTTPException(
            429,
            "Too many reports from this connection. Your app will retry later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        log.warning("rate limiter unavailable, allowing the request", exc_info=True)


def enforce_model_limit(db: Session | None, request: Request, at: datetime) -> None:
    """Each model-written itinerary costs money, so a connection gets a small hourly allowance.

    The global daily cap in `services.trips` is the hard ceiling; this stops one caller using it up.
    """
    if db is not None:
        enforce_rate_limit(
            db, request, 1, at, scope="model", limit=settings.model_requests_per_hour
        )
