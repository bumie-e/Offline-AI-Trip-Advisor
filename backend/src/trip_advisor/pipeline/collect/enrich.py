"""Replace headline-only evidence with full page text and the page's own date."""

from datetime import date

import httpx

from .brightdata import BrightData, BrightDataError
from .extract import extract_article
from .freshness import cutoff
from .models import RawDocument

ENRICHABLE_SOURCES = {"bd_serp"}  # Google News RSS links are redirect-encoded, not fetchable
MAX_PER_CORRIDOR = 5


def enrich(
    docs: list[RawDocument], bd: BrightData, today: date, errors: list[str]
) -> list[RawDocument]:
    """Fetch the newest candidates and update text and date from the page itself.

    The page date wins over the SERP date, because SERP dates are often relative and rough.
    Items with no date at all are still fetched, since the page may reveal one.
    """
    if not bd.can_fetch:
        return docs
    floor = cutoff(today)
    candidates = [
        d
        for d in docs
        if d.source in ENRICHABLE_SOURCES and (d.published is None or d.published >= floor)
    ]
    candidates.sort(key=lambda d: d.published or date.max, reverse=True)
    chosen = {d.id for d in candidates[:MAX_PER_CORRIDOR]}

    out = []
    for doc in docs:
        if doc.id not in chosen:
            out.append(doc)
            continue
        try:
            article = extract_article(bd.fetch_html(doc.url), doc.url)
        except (httpx.HTTPError, BrightDataError) as exc:
            errors.append(f"bright data fetch failed for {doc.url}: {exc}")
            out.append(doc)
            continue
        if article is None:
            out.append(doc)
            continue
        out.append(
            doc.model_copy(
                update={"text": article.text, "published": article.published or doc.published}
            )
        )
    return out
