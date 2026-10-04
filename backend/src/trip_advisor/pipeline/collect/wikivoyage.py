"""Plain-text 'how to get there' guidance from Wikivoyage (CC BY-SA 4.0)."""

import hashlib
from datetime import UTC, datetime

from .http import Fetcher
from .models import DocKind, RawDocument

API = "https://en.wikivoyage.org/w/api.php"
LICENSE = "CC BY-SA 4.0"


def fetch_page(fetcher: Fetcher, site_id: str, title: str) -> RawDocument | None:
    resp = fetcher.get(
        API,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": title,
            "format": "json",
            "redirects": 1,
        },
    )
    pages = resp.json()["query"]["pages"]
    page = next(iter(pages.values()))
    text = page.get("extract")
    if "missing" in page or not text:
        return None
    url = f"https://en.wikivoyage.org/wiki/{page['title'].replace(' ', '_')}"
    return RawDocument(
        id=hashlib.sha1(url.encode()).hexdigest()[:16],
        site_id=site_id,
        kind=DocKind.ROUTE_GUIDE,
        source="wikivoyage",
        publisher="Wikivoyage",
        url=url,
        title=page["title"],
        published=None,
        fetched_at=datetime.now(UTC),
        text=text,
        license=LICENSE,
    )
