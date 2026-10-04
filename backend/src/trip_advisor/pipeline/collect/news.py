"""Recent road news and official notices. Titles, dates and short excerpts only."""

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

from .http import Fetcher
from .models import DocKind, RawDocument

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
FMINO_POSTS = "https://fmino.gov.ng/wp-json/wp/v2/posts"
_TAGS = re.compile(r"<[^>]+>")


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", raw))).strip()


def _doc_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def parse_google_rss(
    xml_text: str, *, site_id: str, corridor: str, query: str, fetched_at: datetime
) -> list[RawDocument]:
    docs = []
    for item in ET.fromstring(xml_text).iter("item"):
        link = (item.findtext("link") or "").strip()
        title = _clean(item.findtext("title") or "")
        if not link or not title:
            continue
        source_el = item.find("source")
        publisher = _clean(source_el.text or "") if source_el is not None else ""
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3]
        pub_raw = item.findtext("pubDate")
        published = parsedate_to_datetime(pub_raw).astimezone(UTC).date() if pub_raw else None
        docs.append(
            RawDocument(
                id=_doc_id(link),
                site_id=site_id,
                kind=DocKind.NEWS,
                source="google_news",
                publisher=publisher or "unknown",
                url=link,
                title=title,
                published=published,
                fetched_at=fetched_at,
                text=_clean(item.findtext("description") or ""),
                corridor=corridor,
                query=query,
            )
        )
    return docs


def fetch_google_news(
    fetcher: Fetcher, *, site_id: str, corridor: str, query: str, now: datetime
) -> list[RawDocument]:
    resp = fetcher.get(
        GOOGLE_NEWS_RSS,
        params={"q": f"{query} when:90d", "hl": "en-NG", "gl": "NG", "ceid": "NG:en"},
    )
    return parse_google_rss(
        resp.text, site_id=site_id, corridor=corridor, query=query, fetched_at=now
    )


def parse_fmino(
    posts: list[dict[str, object]], *, site_id: str, corridor: str, query: str, fetched_at: datetime
) -> list[RawDocument]:
    docs = []
    for post in posts:
        link = str(post.get("link", ""))
        title = _clean(str(post.get("title", {}).get("rendered", "")))  # type: ignore[attr-defined]
        if not link or not title:
            continue
        excerpt = _clean(str(post.get("excerpt", {}).get("rendered", "")))  # type: ignore[attr-defined]
        docs.append(
            RawDocument(
                id=_doc_id(link),
                site_id=site_id,
                kind=DocKind.GOV_NOTICE,
                source="fmino",
                publisher="Federal Ministry of Information and National Orientation",
                url=link,
                title=title,
                published=date.fromisoformat(str(post["date"])[:10]),
                fetched_at=fetched_at,
                text=excerpt,
                corridor=corridor,
                query=query,
            )
        )
    return docs


def fetch_fmino(
    fetcher: Fetcher, *, site_id: str, corridor: str, query: str, now: datetime, after: date
) -> list[RawDocument]:
    resp = fetcher.get(
        FMINO_POSTS,
        params={
            "search": query.replace('"', ""),
            "per_page": 20,
            "orderby": "date",
            "after": f"{after.isoformat()}T00:00:00",
            "_fields": "date,link,title,excerpt",
        },
    )
    return parse_fmino(resp.json(), site_id=site_id, corridor=corridor, query=query, fetched_at=now)
