"""Pull the article text and publication date out of a fetched HTML page."""

import json
from dataclasses import dataclass
from datetime import date

import trafilatura

MAX_TEXT_CHARS = 6000  # enough to judge road conditions; we extract facts, not republish


@dataclass(frozen=True)
class Article:
    text: str
    published: date | None


def extract_article(html: str, url: str) -> Article | None:
    raw = trafilatura.extract(
        html, url=url, output_format="json", with_metadata=True, favor_precision=True
    )
    if not raw:
        return None
    data = json.loads(raw)
    text = (data.get("text") or "").strip()
    if not text:
        return None
    published = None
    if data.get("date"):
        try:
            published = date.fromisoformat(str(data["date"])[:10])
        except ValueError:
            published = None
    return Article(text=text[:MAX_TEXT_CHARS], published=published)
