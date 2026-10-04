"""Bright Data: SERP API (find dated items) and Web Unlocker (fetch full pages).

Both go through POST https://api.brightdata.com/request with a zone name.
Every call costs money, so requests are counted against a per-run budget.
"""

import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from .http import Fetcher
from .models import DocKind, RawDocument

API = "https://api.brightdata.com/request"
GOOGLE = "https://www.google.com/search"


class BrightDataError(RuntimeError):
    pass


class BudgetExceeded(BrightDataError):
    pass


class BrightData:
    def __init__(
        self,
        fetcher: Fetcher,
        api_key: str,
        *,
        unlocker_zone: str = "",
        serp_zone: str = "",
        max_requests: int = 60,
    ) -> None:
        self.fetcher = fetcher
        self.api_key = api_key
        self.unlocker_zone = unlocker_zone
        self.serp_zone = serp_zone
        self.max_requests = max_requests
        self.used = 0

    @property
    def can_search(self) -> bool:
        return bool(self.api_key and self.serp_zone)

    @property
    def can_fetch(self) -> bool:
        return bool(self.api_key and self.unlocker_zone)

    def _request(self, zone: str, url: str) -> httpx.Response:
        if self.used >= self.max_requests:
            raise BudgetExceeded(f"Bright Data budget of {self.max_requests} requests used")
        self.used += 1
        return self.fetcher.post(
            API,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"zone": zone, "url": url, "format": "raw"},
        )

    def serp_news(self, query: str, *, months: int = 3) -> list[dict[str, Any]]:
        """Google News results for the last `months` months, parsed to JSON by Bright Data."""
        if not self.serp_zone:
            raise BrightDataError("No SERP zone configured")
        url = (
            f"{GOOGLE}?q={quote_plus(query)}&tbm=nws&tbs=qdr:m{months}"
            "&gl=ng&hl=en&num=20&brd_json=1"
        )
        # Bright Data occasionally returns an empty body with HTTP 200, so retry once.
        for _ in range(2):
            resp = self._request(self.serp_zone, url)
            try:
                return _serp_items(resp.json())
            except ValueError:
                continue
        raise BrightDataError(
            f"SERP returned no JSON twice (HTTP {resp.status_code}, {len(resp.content)} bytes)"
        )

    def fetch_html(self, url: str) -> str:
        if not self.unlocker_zone:
            raise BrightDataError("No Web Unlocker zone configured")
        return self._request(self.unlocker_zone, url).text


def _serp_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Result lists vary by SERP type; accept the news and organic lists."""
    items: list[dict[str, Any]] = []
    for key in ("news", "organic", "top_stories"):
        value = payload.get(key)
        if isinstance(value, list):
            items.extend(i for i in value if isinstance(i, dict))
    return items


_RELATIVE = re.compile(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", re.IGNORECASE)
_ABSOLUTE_FORMATS = ("%b %d, %Y", "%d %b %Y", "%Y-%m-%d", "%B %d, %Y")


def parse_serp_date(raw: str | None, today: date) -> date | None:
    """Google gives either '3 days ago' or an absolute date. Unknown formats give None."""
    if not raw:
        return None
    raw = raw.strip()
    if m := _RELATIVE.search(raw):
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"minute": 0, "hour": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
        return today - timedelta(days=days)
    for fmt in _ABSOLUTE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()  # noqa: DTZ007 - date only
        except ValueError:
            continue
    return None


def serp_docs(
    items: list[dict[str, Any]],
    *,
    site_id: str,
    corridor: str,
    query: str,
    now: datetime,
) -> list[RawDocument]:
    docs = []
    today = now.astimezone(UTC).date()
    for item in items:
        url = str(item.get("link") or item.get("url") or "")
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        host = urlparse(url).netloc.lower()
        official = host.endswith(".gov.ng")
        docs.append(
            RawDocument(
                id=hashlib.sha1(url.encode()).hexdigest()[:16],
                site_id=site_id,
                kind=DocKind.GOV_NOTICE if official else DocKind.NEWS,
                source="bd_serp",
                publisher=str(item.get("source") or host),
                url=url,
                title=title,
                published=parse_serp_date(str(item.get("date") or ""), today),
                fetched_at=now,
                text=str(item.get("description") or item.get("snippet") or "").strip(),
                corridor=corridor,
                query=query,
            )
        )
    return docs
