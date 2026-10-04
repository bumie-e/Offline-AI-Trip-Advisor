import json
from datetime import UTC, date, datetime

import httpx
import pytest

from trip_advisor.pipeline.collect.brightdata import (
    BrightData,
    BudgetExceeded,
    parse_serp_date,
    serp_docs,
)
from trip_advisor.pipeline.collect.enrich import enrich
from trip_advisor.pipeline.collect.extract import extract_article
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.collect.models import DocKind, RawDocument

TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)

HTML = """<html><head><title>Road repairs</title>
<meta property="article:published_time" content="2026-09-18T08:00:00Z"></head>
<body><article><h1>Repairs begin on Lagos-Abeokuta Expressway</h1>
<p>The Federal Ministry of Works said repairs on the failed sections of the Lagos-Abeokuta
expressway began on Monday, with night works planned to reduce gridlock for motorists
travelling between Lagos and Abeokuta. Officials asked drivers to expect delays.</p>
<p>Motorists were advised to use alternative routes during the closure of some lanes.</p>
</article></body></html>"""


def make_bd(handler, **kw) -> tuple[BrightData, list[dict]]:
    seen: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(
            {"auth": request.headers.get("authorization"), "body": json.loads(request.content)}
        )
        return handler(request)

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(wrapped)), intervals={})
    return BrightData(fetcher, "KEY", **kw), seen


def test_serp_request_shape_and_three_month_filter():
    payload = {
        "news": [{"title": "t", "link": "https://x.ng/a", "source": "X", "date": "2 days ago"}]
    }
    bd, seen = make_bd(lambda r: httpx.Response(200, json=payload), serp_zone="serp1")
    items = bd.serp_news("Lagos-Abeokuta expressway")
    assert items[0]["title"] == "t"
    body = seen[0]["body"]
    assert seen[0]["auth"] == "Bearer KEY"
    assert body["zone"] == "serp1" and body["format"] == "raw"
    assert "tbm=nws" in body["url"] and "tbs=qdr:m3" in body["url"]
    assert "gl=ng" in body["url"] and "brd_json=1" in body["url"]


def test_serp_retries_once_on_empty_body_then_succeeds():
    replies = iter(
        [
            httpx.Response(200, content=b""),
            httpx.Response(200, json={"news": [{"title": "t", "link": "https://x.ng"}]}),
        ]
    )
    bd, seen = make_bd(lambda r: next(replies), serp_zone="s")
    assert len(bd.serp_news("q")) == 1
    assert len(seen) == 2 and bd.used == 2  # the retry is counted against the budget


def test_serp_gives_a_clear_error_after_two_empty_bodies():
    from trip_advisor.pipeline.collect.brightdata import BrightDataError

    bd, _ = make_bd(lambda r: httpx.Response(200, content=b""), serp_zone="s")
    with pytest.raises(BrightDataError, match="no JSON twice"):
        bd.serp_news("q")
    assert bd.used == 2


def test_missing_zone_is_an_error_not_a_request():
    from trip_advisor.pipeline.collect.brightdata import BrightDataError

    bd, seen = make_bd(lambda r: httpx.Response(200, json={}))
    with pytest.raises(BrightDataError):
        bd.serp_news("q")
    with pytest.raises(BrightDataError):
        bd.fetch_html("https://x.ng")
    assert seen == []
    assert not bd.can_search and not bd.can_fetch


def test_budget_stops_requests():
    bd, seen = make_bd(
        lambda r: httpx.Response(200, text="<html/>"), unlocker_zone="u", max_requests=2
    )
    bd.fetch_html("https://a.ng")
    bd.fetch_html("https://b.ng")
    with pytest.raises(BudgetExceeded):
        bd.fetch_html("https://c.ng")
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3 days ago", date(2026, 9, 30)),
        ("2 weeks ago", date(2026, 9, 19)),
        ("5 hours ago", TODAY),
        ("1 month ago", date(2026, 9, 3)),
        ("Jul 13, 2026", date(2026, 7, 13)),
        ("2026-08-02", date(2026, 8, 2)),
        ("sometime", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_serp_date(raw, expected):
    assert parse_serp_date(raw, TODAY) == expected


def test_serp_docs_marks_gov_ng_as_official_and_skips_incomplete():
    items = [
        {"title": "Works update", "link": "https://frsc.gov.ng/x", "date": "Sep 1, 2026"},
        {"title": "Punch story", "link": "https://punchng.com/y", "source": "Punch"},
        {"title": "no link"},
        {"link": "https://z.ng"},
    ]
    docs = serp_docs(items, site_id="s", corridor="c", query="q", now=NOW)
    assert [d.kind for d in docs] == [DocKind.GOV_NOTICE, DocKind.NEWS]
    assert docs[0].published == date(2026, 9, 1) and docs[1].publisher == "Punch"


def test_parses_real_serp_response_fixture():
    from pathlib import Path

    payload = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "serp_news.sample.json").read_text()
    )
    docs = serp_docs(payload["news"], site_id="s", corridor="c", query="q", now=NOW)
    assert len(docs) == 4
    assert docs[0].published == date(2026, 7, 24)  # '24 Jul 2026'
    assert docs[2].published == date(2026, 9, 19)  # '2 weeks ago' relative to TODAY
    assert docs[0].publisher == "The Guardian Nigeria News" and docs[0].text


def test_extract_article_gets_text_and_page_date():
    art = extract_article(HTML, "https://x.ng/a")
    assert art is not None
    assert "failed sections" in art.text and art.published == date(2026, 9, 18)


def test_extract_article_returns_none_for_empty_page():
    assert extract_article("<html><body></body></html>", "https://x.ng/a") is None


def make_doc(id_: str, published: date | None, source: str = "bd_serp") -> RawDocument:
    return RawDocument(
        id=id_,
        site_id="s",
        kind=DocKind.NEWS,
        source=source,
        publisher="p",
        url=f"https://x.ng/{id_}",
        title="Abeokuta road",
        published=published,
        fetched_at=NOW,
    )


def test_enrich_replaces_text_and_page_date_wins():
    bd, _ = make_bd(lambda r: httpx.Response(200, text=HTML), unlocker_zone="u")
    errors: list[str] = []
    out = enrich([make_doc("a", date(2026, 9, 30))], bd, TODAY, errors)
    assert "failed sections" in out[0].text
    assert out[0].published == date(2026, 9, 18)  # page date, not the SERP's rough date
    assert errors == []


def test_enrich_skips_old_unfetchable_sources_and_respects_cap():
    bd, seen = make_bd(lambda r: httpx.Response(200, text=HTML), unlocker_zone="u")
    docs = [
        make_doc("old", date(2026, 1, 1)),  # outside the 3-month window
        make_doc("rss", date(2026, 9, 30), source="google_news"),  # not enrichable
        *[make_doc(f"n{i}", date(2026, 9, 1 + i)) for i in range(8)],
    ]
    enrich(docs, bd, TODAY, [])
    assert len(seen) == 5  # MAX_PER_CORRIDOR
    fetched = {s["body"]["url"] for s in seen}
    assert "https://x.ng/old" not in fetched and "https://x.ng/rss" not in fetched


def test_enrich_failure_keeps_original_and_records_error():
    bd, _ = make_bd(lambda r: httpx.Response(403), unlocker_zone="u")
    errors: list[str] = []
    doc = make_doc("a", date(2026, 9, 30))
    assert enrich([doc], bd, TODAY, errors) == [doc]
    assert len(errors) == 1 and "bright data fetch failed" in errors[0]


def test_enrich_noop_without_unlocker_zone():
    bd, seen = make_bd(lambda r: httpx.Response(200, text=HTML), serp_zone="s")
    doc = make_doc("a", date(2026, 9, 30))
    assert enrich([doc], bd, TODAY, []) == [doc] and seen == []
