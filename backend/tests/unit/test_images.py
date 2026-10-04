from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from trip_advisor.api import deps
from trip_advisor.main import create_app
from trip_advisor.pack.builder import build_pack
from trip_advisor.pipeline.collect import images as img
from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.pipeline.structure.models import StructuredSite
from trip_advisor.schemas.pack import ImageRecord, Pack
from trip_advisor.sites import Endpoint, ImageQueries, SiteConfig

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes" * 20


def page(title="File:Olumo Rock.jpg", *, width=3000, license="CC BY-SA 4.0", artist="<a>Ada</a>",
         description="Olumo Rock in Abeokuta", mime="image/jpeg", restrictions="", cats="Olumo Rock",
         thumb="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Olumo.jpg/800px-Olumo.jpg"):  # fmt: skip
    def m(v):
        return {"value": v}

    return {
        "title": title,
        "imageinfo": [{
            "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Olumo.jpg",
            "thumburl": thumb, "thumbwidth": 800, "thumbheight": 533, "width": width, "height": 2000,
            "mime": mime, "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
            "extmetadata": {
                "LicenseShortName": m(license), "LicenseUrl": m("https://creativecommons.org/x"),
                "Restrictions": m(restrictions), "Artist": m(artist),
                "ImageDescription": m(description), "Categories": m(cats),
                "DateTimeOriginal": m("2024-03-02 10:00:00"),
            },
        }],
    }  # fmt: skip


def candidate(**kw) -> img.Candidate:
    return img.parse_candidates({"query": {"pages": {"1": page(**kw)}}})[0]


# ---- parsing and filtering -------------------------------------------------------------------


def test_parse_reads_licence_author_and_date_as_plain_text():
    c = candidate(artist='<a href="//x">Ada <b>Obi</b></a>')
    assert (c.artist, c.license, c.taken) == ("Ada Obi", "CC BY-SA 4.0", date(2024, 3, 2))
    assert c.thumb_width == 800 and c.page_url.endswith("File:Olumo Rock.jpg")


def test_an_ordinary_free_photo_is_accepted():
    assert img.reject_reason(candidate(), "Olumo Rock") is None


@pytest.mark.parametrize("license", ["CC BY-SA 4.0", "CC BY 2.0", "CC0", "Public domain", "PDM"])
def test_free_licences_are_accepted(license):
    assert img.reject_reason(candidate(license=license), "Olumo Rock") is None


@pytest.mark.parametrize(
    "license",
    ["CC BY-NC 4.0", "CC BY-ND 2.0", "CC BY-NC-SA 3.0", "GFDL", "All rights reserved", ""],
)
def test_non_free_or_restricted_licences_are_rejected(license):
    assert "licence" in (img.reject_reason(candidate(license=license), "Olumo Rock") or "")


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"restrictions": "personality rights"}, "restrictions"),
        ({"width": 500}, "too small"),
        ({"mime": "image/tiff"}, "jpeg or png"),
        ({"mime": "video/webm"}, "jpeg or png"),
        ({"title": "File:Olumo Rock map.png"}, "not a photograph"),
        ({"title": "File:Olumo Rock painting by Ogunbona.jpg"}, "not a photograph"),
        ({"title": "File:Olumo Rock logo.jpg"}, "not a photograph"),
        ({"artist": ""}, "no author"),
        ({"title": "File:A woman at Olumo Rock.jpg"}, "people"),
        ({"title": "File:Priestesses of Olumo Rock.jpg"}, "people"),
        ({"title": "File:Pork meat seller at Olumo Rock.jpg"}, "people"),
    ],
)
def test_unsuitable_files_are_rejected_with_a_reason(kwargs, reason):
    assert reason in (img.reject_reason(candidate(**kwargs), "Olumo Rock") or "")


def test_site_photos_may_match_on_the_description_but_road_photos_must_name_the_road_in_the_title():
    c = candidate(
        title="File:Roadside view.jpg", description="Seen on the Lagos Ibadan expressway", cats=""
    )
    assert img.reject_reason(c, "Lagos Ibadan expressway", "site") is None
    assert "does not match" in (img.reject_reason(c, "Lagos Ibadan expressway", "road") or "")
    titled = candidate(title="File:Lagos Ibadan expressway.jpg", description="")
    assert img.reject_reason(titled, "Lagos Ibadan expressway", "road") is None


def test_every_word_of_the_query_must_match():
    assert "does not match" in (
        img.reject_reason(candidate(title="File:Rock.jpg", description="", cats=""), "Olumo Rock")
        or ""
    )


def test_credit_and_caption_are_ready_to_show():
    c = candidate(title="File:New_Olumo_Rock,_Abeokuta.jpg")
    assert img.credit_line(c) == "Photo: Ada, CC BY-SA 4.0, via Wikimedia Commons"
    assert img.caption(c) == "New Olumo Rock, Abeokuta"


# ---- download --------------------------------------------------------------------------------


def fetcher_for(handler) -> Fetcher:
    return Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), intervals={})


def test_download_returns_small_images():
    f = fetcher_for(
        lambda r: httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    )
    assert img.download(f, "https://upload.wikimedia.org/x/800px-a.jpg") == JPEG


def test_download_retries_smaller_when_too_big_for_a_phone():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        size = img.MAX_BYTES + 1 if "/800px-" in str(request.url) else 1000
        return httpx.Response(200, content=b"x" * size, headers={"content-type": "image/jpeg"})

    blob = img.download(fetcher_for(handler), "https://upload.wikimedia.org/x/800px-a.jpg")
    assert blob is not None and len(blob) == 1000 and "/500px-" in urls[-1]


def test_download_gives_up_when_even_the_smaller_one_is_too_big():
    f = fetcher_for(
        lambda r: httpx.Response(
            200, content=b"x" * (img.MAX_BYTES + 1), headers={"content-type": "image/jpeg"}
        )
    )
    assert img.download(f, "https://upload.wikimedia.org/x/800px-a.jpg") is None


def test_download_refuses_something_that_is_not_an_image():
    f = fetcher_for(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    )
    assert img.download(f, "https://upload.wikimedia.org/x/800px-a.jpg") is None


# ---- collecting a site -----------------------------------------------------------------------


class OkJudge:
    """A judge that approves everything, and records what it was asked."""

    name = "fake-judge"

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    def check(self, blob, mime, *, subject, caption):
        self.asked.append((subject, caption))
        return img.Verdict(shows_subject=True, people_prominent=False,
                           contact_details_visible=False, reason="Shows the rock.")  # fmt: skip


class ScriptedJudge(OkJudge):
    """Answers from a list, in order; None means 'could not decide'."""

    def __init__(self, *answers):
        super().__init__()
        self.answers = list(answers)

    def check(self, blob, mime, *, subject, caption):
        super().check(blob, mime, subject=subject, caption=caption)
        return self.answers.pop(0)


def verdict(**kw) -> img.Verdict:
    base = {"shows_subject": True, "people_prominent": False, "contact_details_visible": False,
            "reason": "ok"}  # fmt: skip
    return img.Verdict(**{**base, **kw})


def site(**queries) -> SiteConfig:
    return SiteConfig(
        id="olumo-rock", name="Olumo Rock", city="Abeokuta", state="Ogun",
        origin=Endpoint(query="a"), destination=Endpoint(query="b"), corridors=[],
        images=ImageQueries(**queries),
    )  # fmt: skip


def commons(results: dict[str, list[dict]], blobs: dict[str, bytes] | None = None):
    """A fake Wikimedia: search results per query, and image bytes per file name."""
    blobs = blobs or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "commons.wikimedia.org":
            pages = results.get(request.url.params["gsrsearch"], [])
            return httpx.Response(
                200, json={"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}
            )
        name = request.url.path.rsplit("/", 1)[-1].split("px-", 1)[-1]
        return httpx.Response(
            200, content=blobs.get(name, JPEG), headers={"content-type": "image/jpeg"}
        )

    return fetcher_for(handler)


def thumb(name: str) -> str:
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/{name}/800px-{name}"


def test_collect_writes_files_and_a_manifest_with_credit(tmp_path):
    f = commons({"Olumo Rock": [page("File:Olumo Rock.jpg", thumb=thumb("Olumo.jpg"))]})
    manifest, report = img.collect_images(site(site=["Olumo Rock"]), f, out_dir=tmp_path, now=NOW)
    assert report.kept == {"site": 1} and not report.errors
    rec = manifest.images[0]
    assert rec.kind == "site" and rec.confidence == "high"  # the query is in the title
    assert rec.credit == "Photo: Ada, CC BY-SA 4.0, via Wikimedia Commons"
    assert rec.size_bytes == len(JPEG) and rec.path.startswith("/images/olumo-rock/img-olumo-rock-")
    assert (tmp_path / "olumo-rock" / rec.path.rsplit("/", 1)[-1]).read_bytes() == JPEG
    assert rec.source.publisher == "Wikimedia Commons" and rec.last_verified == NOW.date()


def test_collect_keeps_site_and_road_photos_apart_and_reports_rejections(tmp_path):
    f = commons({
        "Olumo Rock": [page("File:Olumo Rock.jpg", thumb=thumb("a.jpg")),
                       page("File:Olumo Rock map.png", thumb=thumb("b.png"))],
        "Abeokuta road": [page("File:Abeokuta road.jpg", thumb=thumb("c.jpg"), description="")],
    }, {"a.jpg": JPEG + b"1", "c.jpg": JPEG + b"2"})  # fmt: skip
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"], roads=["Abeokuta road"]), f, judge=OkJudge(), out_dir=tmp_path
    )
    assert {r.kind for r in manifest.images} == {"site", "road"}
    assert report.rejected["not a photograph"] == 1


def test_the_same_picture_under_two_titles_is_kept_once(tmp_path):
    f = commons(
        {
            "Olumo Rock": [
                page("File:Olumo Rock 1.jpg", thumb=thumb("a.jpg")),
                page("File:Olumo Rock 2.jpg", thumb=thumb("b.jpg")),
            ]
        }
    )  # same bytes
    manifest, _ = img.collect_images(site(site=["Olumo Rock"]), f, out_dir=tmp_path)
    assert len(manifest.images) == 1


def test_a_title_returned_by_two_queries_is_considered_once(tmp_path):
    p = page("File:Olumo Rock.jpg", thumb=thumb("a.jpg"))
    f = commons({"Olumo Rock": [p], "Olumo": [p]})
    manifest, _ = img.collect_images(site(site=["Olumo Rock", "Olumo"]), f, out_dir=tmp_path)
    assert len(manifest.images) == 1


def test_each_kind_is_capped_and_the_widest_photos_win(tmp_path):
    pages = [
        page(f"File:Olumo Rock {i}.jpg", width=1000 + i * 100, thumb=thumb(f"{i}.jpg"))
        for i in range(10)
    ]
    blobs = {f"{i}.jpg": JPEG + bytes([i]) for i in range(10)}
    manifest, _ = img.collect_images(
        site(site=["Olumo Rock"]), commons({"Olumo Rock": pages}, blobs), out_dir=tmp_path
    )
    assert len(manifest.images) == img.MAX_PER_KIND["site"]
    assert str(manifest.images[0].source.url).endswith("Olumo%20Rock%209.jpg")  # widest first


def test_a_failed_search_is_a_gap_not_a_crash(tmp_path):
    def handler(request):
        return httpx.Response(500)

    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)), intervals={}, sleep=lambda _: None
    )
    manifest, report = img.collect_images(site(site=["Olumo Rock"]), f, out_dir=tmp_path)
    assert manifest.images == [] and len(report.errors) == 1


def test_a_site_with_no_search_terms_collects_nothing(tmp_path):
    manifest, report = img.collect_images(site(), commons({}), out_dir=tmp_path)
    assert manifest.images == [] and not report.errors


def test_manifest_round_trips_and_missing_is_none(tmp_path):
    f = commons({"Olumo Rock": [page("File:Olumo Rock.jpg", thumb=thumb("a.jpg"))]})
    manifest, _ = img.collect_images(site(site=["Olumo Rock"]), f, out_dir=tmp_path)
    (tmp_path / "olumo-rock" / "manifest.json").write_text(manifest.model_dump_json())
    assert img.load_manifest("olumo-rock", tmp_path) == manifest
    assert img.load_manifest("nowhere", tmp_path) is None


def test_review_sheet_lists_credit_licence_and_page(tmp_path):
    f = commons({"Olumo Rock": [page("File:Olumo Rock.jpg", thumb=thumb("a.jpg"))]})
    manifest, _ = img.collect_images(site(site=["Olumo Rock"]), f, out_dir=tmp_path)
    sheet = tmp_path / "review.md"
    img.write_review(manifest, sheet)
    text = sheet.read_text()
    assert "Photo: Ada" in text and "CC BY-SA 4.0" in text and "commons.wikimedia.org/wiki" in text


# ---- the pack ---------------------------------------------------------------------------------


def a_record(**kw) -> ImageRecord:
    base = {
        "id": "img-olumo-rock-abc", "summary": "Olumo Rock", "kind": "site", "confidence": "high",
        "source": {"publisher": "Wikimedia Commons", "url": "https://commons.wikimedia.org/wiki/File:A.jpg"},
        "last_verified": "2026-10-05", "path": "/images/olumo-rock/img-olumo-rock-abc.jpg",
        "mime": "image/jpeg", "width": 800, "height": 533, "size_bytes": 90_000,
        "credit": "Photo: Ada, CC BY-SA 4.0, via Wikimedia Commons", "license": "CC BY-SA 4.0",
    }  # fmt: skip
    return ImageRecord.model_validate({**base, **kw})


def structured() -> StructuredSite:
    return StructuredSite(site_id="olumo-rock", structured_on=date(2026, 10, 5), records=[],
                          flags=[], rejected=[], docs_processed=0)  # fmt: skip


def test_images_ride_in_the_pack_and_change_its_version():
    plain, _ = build_pack(structured(), now=NOW)
    with_img, report = build_pack(structured(), now=NOW, images=[a_record()])
    assert [r.type for r in with_img.records] == ["image"] and report.kept == 1
    assert with_img.version != plain.version
    again = Pack.model_validate_json(with_img.model_dump_json())  # survives the round trip
    assert isinstance(again.records[0], ImageRecord)


def test_an_image_record_without_a_credit_or_with_a_zero_size_is_invalid():
    with pytest.raises(ValueError):
        a_record(size_bytes=0)
    with pytest.raises(ValueError):
        a_record(kind="map")


# ---- the API ---------------------------------------------------------------------------------


@pytest.fixture
def served(tmp_path):
    base = tmp_path
    (base / "sites").mkdir()
    (base / "sites" / "olumo-rock.toml").write_text(Path("data/sites/olumo-rock.toml").read_text())
    folder = base / "images" / "olumo-rock"
    folder.mkdir(parents=True)
    rec = a_record()
    (folder / "img-olumo-rock-abc.jpg").write_bytes(JPEG)
    (folder / "secret.txt").write_text("not an image in the manifest")
    manifest = img.ImageManifest(site_id="olumo-rock", collected_at=NOW, images=[rec])
    (folder / "manifest.json").write_text(manifest.model_dump_json())
    app = create_app()
    app.dependency_overrides[deps.data_dir] = lambda: base
    return TestClient(app)


def test_api_lists_the_images_with_their_credit(served):
    body = served.get("/images/olumo-rock").json()
    assert body[0]["credit"].startswith("Photo: Ada") and body[0]["path"].endswith(".jpg")


def test_api_serves_the_file_with_long_lived_caching(served):
    resp = served.get("/images/olumo-rock/img-olumo-rock-abc.jpg")
    assert resp.status_code == 200 and resp.content == JPEG
    assert resp.headers["content-type"] == "image/jpeg"
    assert (
        "immutable" in resp.headers["cache-control"]
        and "max-age=31536000" in resp.headers["cache-control"]
    )
    assert resp.headers["etag"] == '"img-olumo-rock-abc"'


def test_api_answers_304_when_the_device_already_has_it(served):
    resp = served.get(
        "/images/olumo-rock/img-olumo-rock-abc.jpg",
        headers={"If-None-Match": '"img-olumo-rock-abc"'},
    )
    assert resp.status_code == 304 and resp.content == b""


def test_api_serves_only_files_named_in_the_manifest(served):
    assert served.get("/images/olumo-rock/secret.txt").status_code == 404
    assert served.get("/images/olumo-rock/manifest.json").status_code == 404
    assert served.get("/images/olumo-rock/..%2F..%2Fsites%2Folumo-rock.toml").status_code == 404
    assert served.get("/images/olumo-rock/nothing.jpg").status_code == 404


def test_api_unknown_site_is_404_and_a_site_without_images_gives_an_empty_list(served, tmp_path):
    assert served.get("/images/nowhere").status_code == 404
    (tmp_path / "images" / "olumo-rock" / "manifest.json").unlink()
    assert served.get("/images/olumo-rock").json() == []


# ---- the judge -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "problem"),
    [
        ({}, None),
        ({"shows_subject": False}, "does not show the subject"),
        ({"people_prominent": True}, "people are prominent"),
        ({"contact_details_visible": True}, "contact details"),
    ],
)
def test_verdict_problems(kw, problem):
    got = img.verdict_problem(verdict(**kw))
    assert (got is None) if problem is None else (problem in (got or ""))


def one_site_page(i: int, **kw):
    return page(f"File:Olumo Rock {i}.jpg", width=3000 - i, thumb=thumb(f"{i}.jpg"), **kw)


def test_photos_the_judge_rejects_are_not_kept_and_the_next_candidate_fills_the_slot(tmp_path):
    pages = [one_site_page(i) for i in range(8)]
    blobs = {f"{i}.jpg": JPEG + bytes([i]) for i in range(8)}
    # the first two best candidates fail; then every other one passes
    judge = ScriptedJudge(verdict(people_prominent=True), verdict(shows_subject=False),
                          *[verdict() for _ in range(10)])  # fmt: skip
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"]),
        commons({"Olumo Rock": pages}, blobs),
        judge=judge,
        out_dir=tmp_path,
    )
    assert len(manifest.images) == img.MAX_PER_KIND["site"]  # still full
    assert len(judge.asked) == img.MAX_PER_KIND["site"] + 2  # looked at two extra
    assert report.rejected["judge: people are prominent"] == 1
    assert report.rejected["judge: does not show the subject"] == 1


def test_the_judge_is_told_what_each_kind_of_photo_should_show(tmp_path):
    f = commons({
        "Olumo Rock": [one_site_page(1)],
        "Abeokuta road": [page("File:Abeokuta road.jpg", thumb=thumb("r.jpg"), description="")],
    }, {"1.jpg": JPEG + b"1", "r.jpg": JPEG + b"2"})  # fmt: skip
    judge = OkJudge()
    img.collect_images(
        site(site=["Olumo Rock"], roads=["Abeokuta road"]), f, judge=judge, out_dir=tmp_path
    )
    subjects = [s for s, _ in judge.asked]
    assert "heritage site" in subjects[0] and "Olumo Rock" in subjects[0]
    assert "road" in subjects[1] and "on the way to Olumo Rock" in subjects[1]


def test_a_judge_that_cannot_decide_means_the_photo_is_not_used(tmp_path):
    f = commons({"Olumo Rock": [one_site_page(1)]})
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"]), f, judge=ScriptedJudge(None), out_dir=tmp_path
    )
    assert manifest.images == [] and report.rejected["judge could not decide"] == 1


def test_without_a_judge_road_photos_are_skipped_and_site_photos_are_marked_unchecked(tmp_path):
    f = commons({
        "Olumo Rock": [one_site_page(1)],
        "Abeokuta road": [page("File:Abeokuta road.jpg", thumb=thumb("r.jpg"), description="")],
    })  # fmt: skip
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"], roads=["Abeokuta road"]), f, out_dir=tmp_path
    )
    assert [r.kind for r in manifest.images] == ["site"]
    assert any("road photos skipped" in e for e in report.errors)
    assert manifest.judge == "" and list(manifest.judged.values()) == ["not checked by a judge"]


def test_the_manifest_and_review_sheet_say_who_checked_each_photo(tmp_path):
    f = commons({"Olumo Rock": [one_site_page(1)]})
    manifest, _ = img.collect_images(
        site(site=["Olumo Rock"]), f, judge=OkJudge(), out_dir=tmp_path
    )
    assert manifest.judge == "fake-judge" and list(manifest.judged.values()) == ["Shows the rock."]
    sheet = tmp_path / "review.md"
    img.write_review(manifest, sheet)
    assert "judge (fake-judge): Shows the rock." in sheet.read_text()


class FakeMessages:
    def __init__(self, result):
        self.result, self.sent = result, None

    def create(self, **kw):
        self.sent = kw
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def anthropic_judge(result) -> tuple[img.AnthropicJudge, FakeMessages]:
    judge = img.AnthropicJudge.__new__(img.AnthropicJudge)
    judge.name = "model-x"
    messages = FakeMessages(result)
    judge._client = type("C", (), {"messages": messages})()
    return judge, messages


def tool_reply(payload: dict):
    from types import SimpleNamespace

    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=payload)])


def test_anthropic_judge_sends_the_picture_and_parses_the_answer():
    reply = {"shows_subject": True, "people_prominent": False, "contact_details_visible": False,
             "reason": "A rock."}  # fmt: skip
    judge, messages = anthropic_judge(tool_reply(reply))
    got = judge.check(JPEG, "image/jpeg", subject="Olumo Rock", caption="A rock")
    assert got is not None and got.shows_subject and got.reason == "A rock."
    block = messages.sent["messages"][0]["content"][0]
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"
    assert block["source"]["data"]  # base64 of the bytes
    assert messages.sent["model"] == "model-x"


def test_anthropic_judge_gives_none_on_a_bad_reply_or_an_api_error():
    import anthropic
    import httpx as _httpx

    judge, _ = anthropic_judge(tool_reply({"shows_subject": "maybe"}))
    assert judge.check(JPEG, "image/jpeg", subject="s", caption="c") is None
    err = anthropic.APIConnectionError(request=_httpx.Request("POST", "https://x"))
    judge, _ = anthropic_judge(err)
    assert judge.check(JPEG, "image/jpeg", subject="s", caption="c") is None


def test_saving_removes_files_from_earlier_runs_that_are_no_longer_listed(tmp_path):
    folder = tmp_path / "olumo-rock"
    folder.mkdir()
    (folder / "img-olumo-rock-old.jpg").write_bytes(b"rejected last time")
    (folder / "img-olumo-rock-old.png").write_bytes(b"rejected last time")
    (folder / "notes.txt").write_text("not an image: left alone")
    f = commons({"Olumo Rock": [page("File:Olumo Rock.jpg", thumb=thumb("a.jpg"))]})
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"]), f, judge=OkJudge(), out_dir=tmp_path
    )
    assert (folder / "img-olumo-rock-old.jpg").exists()  # collecting alone deletes nothing
    assert img.save_collection(manifest, report, folder) is None
    kept = manifest.images[0].path.rsplit("/", 1)[-1]
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        [kept, "manifest.json", "review.md", "notes.txt"]
    )


def test_a_failing_judge_never_replaces_the_existing_images(tmp_path):
    folder = tmp_path / "olumo-rock"
    folder.mkdir()
    (folder / "img-olumo-rock-good.jpg").write_bytes(b"a good, already approved photo")
    (folder / "manifest.json").write_text("the existing manifest")
    pages = [one_site_page(i) for i in range(5)]
    blobs = {f"{i}.jpg": JPEG + bytes([i]) for i in range(5)}
    broken = ScriptedJudge(*[None] * 20)  # every answer missing: misconfigured, or the API is down
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"]),
        commons({"Olumo Rock": pages}, blobs),
        judge=broken,
        out_dir=tmp_path,
    )
    assert manifest.images == [] and report.judge_broken
    assert "judge failed" in (img.save_collection(manifest, report, folder) or "")
    assert (folder / "img-olumo-rock-good.jpg").read_bytes() == b"a good, already approved photo"
    assert (folder / "manifest.json").read_text() == "the existing manifest"


def test_a_judge_that_mostly_works_is_not_called_broken():
    report = img.Report(judge_calls=10, undecided=2)
    assert not report.judge_broken
    assert img.Report(judge_calls=10, undecided=6).judge_broken


def test_too_few_judge_calls_do_not_count_as_a_broken_judge():
    assert not img.Report(judge_calls=2, undecided=2).judge_broken  # not enough to tell
    assert not img.Report().judge_broken  # no judge, or nothing to judge


def stored_site(tmp_path):
    """A site folder holding one approved photo and a manifest listing it."""
    folder = tmp_path / "olumo-rock"
    folder.mkdir()
    (folder / "img-olumo-rock-good.jpg").write_bytes(b"approved photo")
    record = a_record(id="img-olumo-rock-good", path="/images/olumo-rock/img-olumo-rock-good.jpg")
    good = img.ImageManifest(site_id="olumo-rock", collected_at=NOW, images=[record])
    (folder / "manifest.json").write_text(good.model_dump_json())
    return folder


def test_a_run_where_every_search_failed_leaves_the_stored_images_alone(tmp_path):
    """The real failure: the network dropped, nothing was found, and the folder was emptied."""
    folder = stored_site(tmp_path)

    def offline(request):
        raise httpx.ConnectError("nodename nor servname provided")

    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(offline)), intervals={}, sleep=lambda _: None
    )
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"], roads=["Abeokuta road"]), f, judge=OkJudge(), out_dir=tmp_path
    )
    assert manifest.images == [] and report.search_failures == 2 and report.incomplete
    assert "searches" in (img.save_collection(manifest, report, folder) or "")
    assert (folder / "img-olumo-rock-good.jpg").read_bytes() == b"approved photo"
    assert len(img.load_manifest("olumo-rock", tmp_path).images) == 1  # type: ignore[union-attr]


def test_one_failed_search_out_of_several_also_refuses_to_replace(tmp_path):
    folder = stored_site(tmp_path)
    ok = page("File:Olumo Rock.jpg", thumb=thumb("a.jpg"))

    def handler(request):
        if request.url.host == "commons.wikimedia.org":
            if request.url.params["gsrsearch"] == "Olumo Rock":
                return httpx.Response(200, json={"query": {"pages": {"1": ok}}})
            return httpx.Response(500)
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)), intervals={}, sleep=lambda _: None
    )
    manifest, report = img.collect_images(
        site(site=["Olumo Rock"], roads=["Abeokuta road"]), f, judge=OkJudge(), out_dir=tmp_path
    )
    assert len(manifest.images) == 1 and report.incomplete  # one photo found, one search failed
    assert img.save_collection(manifest, report, folder) is not None
    assert (folder / "img-olumo-rock-good.jpg").exists()


def test_many_failed_downloads_count_as_an_incomplete_run():
    assert not img.Report(download_failures=img.MAX_DOWNLOAD_FAILURES - 1).incomplete
    assert img.Report(download_failures=img.MAX_DOWNLOAD_FAILURES).incomplete


def test_finding_nothing_does_not_replace_a_stored_set(tmp_path):
    folder = stored_site(tmp_path)
    empty = img.ImageManifest(site_id="olumo-rock", collected_at=NOW, images=[])
    refused = img.save_collection(empty, img.Report(), folder)  # a clean run that found nothing
    assert refused and "1 are already stored" in refused
    assert (folder / "img-olumo-rock-good.jpg").exists()


def test_a_first_run_that_finds_nothing_may_save_an_empty_manifest(tmp_path):
    folder = tmp_path / "olumo-rock"
    empty = img.ImageManifest(site_id="olumo-rock", collected_at=NOW, images=[])
    assert img.save_collection(empty, img.Report(), folder) is None
    assert img.load_manifest("olumo-rock", tmp_path) == empty
