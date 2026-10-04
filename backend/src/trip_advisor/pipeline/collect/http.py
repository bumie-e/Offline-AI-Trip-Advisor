"""HTTP client with per-host rate limiting and retries."""

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

USER_AGENT = "OfflineTripAdvisor/0.1 (akinremibunmi111@gmail.com)"

# Minimum seconds between requests to a host (public services, be polite).
MIN_INTERVAL: dict[str, float] = {
    "nominatim.openstreetmap.org": 1.2,
    "overpass-api.de": 2.0,
    "overpass.private.coffee": 2.0,
    "router.project-osrm.org": 1.0,
    "news.google.com": 2.0,
    "fmino.gov.ng": 1.0,
    "en.wikivoyage.org": 1.0,
    "api.brightdata.com": 0.5,
}


class Fetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        intervals: dict[str, float] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 3,
    ) -> None:
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=90, follow_redirects=True
        )
        self.intervals = MIN_INTERVAL if intervals is None else intervals
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self.retries = retries

    def _wait(self, host: str) -> None:
        gap = self.intervals.get(host, 0.0)
        wait = self._last.get(host, 0.0) + gap - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        self._last[host] = time.monotonic()

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        host = urlparse(url).netloc
        for attempt in range(self.retries):
            self._wait(host)
            try:
                resp = self.client.request(method, url, **kw)
            except httpx.TransportError:
                if attempt == self.retries - 1:
                    raise
            else:
                if resp.status_code not in (429, 502, 503, 504):
                    resp.raise_for_status()
                    return resp
                if attempt == self.retries - 1:
                    resp.raise_for_status()
            self._sleep(2.0 * (attempt + 1) ** 2)
        raise RuntimeError("unreachable")

    def pause(self, seconds: float) -> None:
        self._sleep(seconds)

    def get(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("POST", url, **kw)
