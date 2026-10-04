"""Photos of the heritage site and its roads from Wikimedia Commons.

Only freely licensed photos are kept, each with its author and licence, because those licences
require credit. Files are downloaded as small thumbnails so a phone can store them.
"""

import base64
import hashlib
import html
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import Field

from trip_advisor.schemas.common import Source, Strict
from trip_advisor.schemas.pack import ImageRecord
from trip_advisor.sites import SiteConfig

from .http import Fetcher

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
IMAGES_DIR = Path("data/images")
THUMB_WIDTH = 800
FALLBACK_WIDTH = 500  # Wikimedia only serves its standard thumbnail widths (500 is one)
MIN_WIDTH = 800  # the original must be at least this wide
MAX_BYTES = 350_000
SEARCH_LIMIT = 15
MAX_PER_KIND = {"site": 6, "road": 4}
MAX_DOWNLOAD_FAILURES = 3

# CC0, public domain, and attribution licences with no NC or ND clause.
_FREE = re.compile(r"^(CC0|CC[ -]BY(-SA)?\b|Public domain|PDM|PD\b)", re.IGNORECASE)
_RESTRICTED = re.compile(r"\b(NC|ND)\b|non-?commercial|no-?derivative", re.IGNORECASE)
# Things that are not photographs of the place.
_NOT_A_PHOTO = re.compile(
    r"\b(map|maps|logo|flag|painting|drawing|illustration|diagram|poster|screenshot|stamp|"
    r"postcard|coat of arms|banknote|icon)\b",
    re.IGNORECASE,
)
# Photos whose subject is a person. Identifiable people are not what a traveller needs to see,
# and some of these sites are sacred. The title is a reliable hint of the main subject.
_PEOPLE = re.compile(
    r"\b(woman|women|man|men|girl|girls|boy|boys|child|children|baby|babies|kid|kids|people|"
    r"person|portrait|selfie|wedding|bride|groom|family|priest|priests|priestess|priestesses|"
    r"worshipper|worshippers|student|students|pupil|pupils|crowd|seller|vendor|trader|hawker|"
    r"beggar|police|policeman|soldier|model|queen|king|oba|chief|youth|youths)\b",
    re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")
_EXT = {"image/jpeg": "jpg", "image/png": "png"}


class ImageManifest(Strict):
    site_id: str
    collected_at: datetime
    images: list[ImageRecord]
    judge: str = ""  # the model that looked at each picture, or "" if none did
    judged: dict[str, str] = Field(default_factory=dict)  # image id -> what the judge said


class Verdict(Strict):
    """What the judge saw. Photos are shown to travellers, so the bar is deliberately high."""

    shows_subject: bool  # it really is a photo of the thing it is supposed to show
    people_prominent: bool  # a face is clearly visible, or a person is the main subject
    contact_details_visible: bool  # a readable phone number, email or similar
    reason: str = Field(max_length=200)


class ImageJudge(Protocol):
    name: str

    def check(self, blob: bytes, mime: str, *, subject: str, caption: str) -> Verdict | None:
        """None when the judge could not decide."""
        ...


def verdict_problem(v: Verdict) -> str | None:
    if not v.shows_subject:
        return "judge: does not show the subject"
    if v.people_prominent:
        return "judge: people are prominent"
    if v.contact_details_visible:
        return "judge: shows contact details"
    return None


JUDGE_SYSTEM = """You check candidate photos for a travel app that shows a heritage site and the \
roads leading to it. Look at the picture and answer by calling the tool. Judge only what you can \
see: the caption was written by the uploader and may be wrong, so do not rely on it.

- shows_subject: for a road, true only if a road or highway is the main subject (its surface, \
lanes, a bridge, or traffic moving along it). It is false for a building beside a road, a drain \
or gutter, a market, a railway, a roadside stall, a car interior, or a view through a windshield \
with the dashboard in frame. For a heritage site, the landscape, monument, rock, grove, shrine, \
entrance or view counts.
- people_prominent: true if any person's face is clearly visible, or a person is the main \
subject, or there is a crowd with visible faces. Small distant figures do not count.
- contact_details_visible: true if a phone number, email address or similar can be read.
- reason: one short sentence saying what you see."""


class AnthropicJudge:
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=40.0, max_retries=1)
        self.name = model

    def check(self, blob: bytes, mime: str, *, subject: str, caption: str) -> Verdict | None:
        import anthropic
        from anthropic.types import MessageParam, ToolParam
        from pydantic import ValidationError

        tool: ToolParam = {
            "name": "judge_photo",
            "description": "Report what the photo shows.",
            "input_schema": Verdict.model_json_schema(),
        }
        message: MessageParam = {
            "role": "user",
            "content": [
                {  # type: ignore[list-item]  # mime is a plain str, the SDK wants a Literal
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": base64.b64encode(blob).decode(),
                    },
                },
                {"type": "text", "text": f"Subject it should show: {subject}\nCaption: {caption}"},
            ],
        }
        try:
            resp = self._client.messages.create(
                model=self.name,
                max_tokens=400,
                system=JUDGE_SYSTEM,
                tools=[tool],
                tool_choice={"type": "auto"},  # newer models reject a forced tool
                messages=[message],
            )
        except anthropic.APIError:
            return None
        for block in resp.content:
            if block.type == "tool_use":
                try:
                    return Verdict.model_validate(block.input)
                except ValidationError:
                    return None
        return None


@dataclass(frozen=True)
class Candidate:
    title: str  # "File:Olumo Rock, Abeokuta.jpg"
    page_url: str
    thumb_url: str
    width: int  # of the original
    thumb_width: int
    thumb_height: int
    mime: str
    license: str
    license_url: str | None
    restrictions: str
    artist: str
    description: str
    categories: str
    taken: date | None
    kind: str = ""
    query: str = ""


@dataclass
class Report:
    kept: Counter[str] = field(default_factory=Counter)
    rejected: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    judge_calls: int = 0
    undecided: int = 0  # the judge errored or gave no usable answer
    search_failures: int = 0
    download_failures: int = 0

    @property
    def incomplete(self) -> bool:
        """A failed search or several failed downloads mean the run saw only part of what exists
        (network or Wikimedia trouble). Its result must not replace a good set of images."""
        return self.search_failures > 0 or self.download_failures >= MAX_DOWNLOAD_FAILURES

    @property
    def judge_broken(self) -> bool:
        """Most answers missing means the judge is down or misconfigured, not that every photo is
        bad. Such a run must not replace a good set of images."""
        return self.judge_calls >= 3 and self.undecided / self.judge_calls > 0.5


def _text(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub(" ", raw))).strip()


def _meta(info: dict[str, Any], key: str) -> str:
    return str(info.get("extmetadata", {}).get(key, {}).get("value", "") or "")


def _taken(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def parse_candidates(payload: dict[str, Any]) -> list[Candidate]:
    out = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        out.append(
            Candidate(
                title=page["title"],
                page_url=info.get("descriptionurl", ""),
                thumb_url=info.get("thumburl") or info.get("url", ""),
                width=int(info.get("width", 0)),
                thumb_width=int(info.get("thumbwidth") or info.get("width", 0)),
                thumb_height=int(info.get("thumbheight") or info.get("height", 0)),
                mime=info.get("mime", ""),
                license=_text(_meta(info, "LicenseShortName")),
                license_url=_meta(info, "LicenseUrl") or None,
                restrictions=_text(_meta(info, "Restrictions")),
                artist=_text(_meta(info, "Artist")),
                description=_text(_meta(info, "ImageDescription")),
                categories=_text(_meta(info, "Categories")).replace("|", " "),
                taken=_taken(_meta(info, "DateTimeOriginal") or _meta(info, "DateTime")),
            )
        )
    return out


def _words(query: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) >= 3]


def reject_reason(c: Candidate, query: str, kind: str = "site") -> str | None:
    """Why a file cannot be used, or None when it is acceptable.

    Road photos must name the road in their title: a description that merely mentions the road
    is how unrelated pictures get in. Site photos may match on the description as well.
    """
    if c.mime not in _EXT:
        return "not a jpeg or png"
    if not c.license or not _FREE.search(c.license) or _RESTRICTED.search(c.license):
        return f"licence not allowed ({c.license or 'none'})"
    if c.restrictions:
        return f"has restrictions ({c.restrictions[:30]})"
    if c.width < MIN_WIDTH:
        return "too small"
    if _NOT_A_PHOTO.search(f"{c.title} {c.categories}"):
        return "not a photograph"
    if _PEOPLE.search(c.title):
        return "a photo of people"
    haystack = (
        c.title.lower() if kind == "road" else f"{c.title} {c.description} {c.categories}".lower()
    )
    if not all(w in haystack for w in _words(query)):
        return "does not match the search"
    if not c.artist:
        return "no author to credit"
    return None


def credit_line(c: Candidate) -> str:
    return f"Photo: {c.artist}, {c.license}, via Wikimedia Commons"


def caption(c: Candidate) -> str:
    name = re.sub(r"^File:", "", c.title)
    name = re.sub(r"\.(jpe?g|png)$", "", name, flags=re.IGNORECASE).replace("_", " ").strip()
    return name[:200]


def search(fetcher: Fetcher, query: str) -> list[Candidate]:
    resp = fetcher.get(
        COMMONS_API,
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,  # files
            "gsrlimit": SEARCH_LIMIT,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": THUMB_WIDTH,
            "format": "json",
        },
    )
    return parse_candidates(resp.json())


def download(fetcher: Fetcher, url: str) -> bytes | None:
    """The thumbnail bytes, trying a smaller size once if the first is too big for a phone."""
    for candidate_url in (url, re.sub(r"/\d+px-", f"/{FALLBACK_WIDTH}px-", url)):
        resp = fetcher.get(candidate_url)
        if not resp.headers.get("content-type", "").startswith("image/"):
            return None
        if len(resp.content) <= MAX_BYTES:
            return resp.content
        if candidate_url != url or "px-" not in url:
            break
    return None


def _select(fetcher: Fetcher, queries: list[str], kind: str, report: Report) -> list[Candidate]:
    """Every acceptable candidate, widest first. The caller stops once it has enough."""
    seen: set[str] = set()
    keep: list[Candidate] = []
    for query in queries:
        try:
            found = search(fetcher, query)
        except (httpx.HTTPError, ValueError) as exc:
            report.search_failures += 1
            report.errors.append(f"search failed for {query!r}: {exc}")
            continue
        for c in found:
            if c.title in seen:
                continue
            seen.add(c.title)
            if why := reject_reason(c, query, kind):
                report.rejected[why.split(" (")[0]] += 1
                continue
            keep.append(Candidate(**{**c.__dict__, "kind": kind, "query": query}))
    keep.sort(key=lambda c: (-c.width, c.title))
    return keep


def _record(site_id: str, c: Candidate, blob: bytes, today: date) -> tuple[ImageRecord, str]:
    digest = hashlib.sha256(blob).hexdigest()[:10]
    image_id = f"img-{site_id}-{digest}"
    filename = f"{image_id}.{_EXT[c.mime]}"
    exact = re.sub(r"[^a-z0-9]+", "", c.query.lower()) in re.sub(r"[^a-z0-9]+", "", c.title.lower())
    record = ImageRecord(
        id=image_id,
        summary=caption(c),
        source=Source(publisher="Wikimedia Commons", url=c.page_url, published=c.taken),  # type: ignore[arg-type]
        confidence="high" if exact else "medium",  # type: ignore[arg-type]
        last_verified=today,
        kind=c.kind,  # type: ignore[arg-type]
        path=f"/images/{site_id}/{filename}",
        mime=c.mime,
        width=c.thumb_width,
        height=c.thumb_height,
        size_bytes=len(blob),
        credit=credit_line(c),
        license=c.license,
        license_url=c.license_url,
    )
    return record, filename


MAX_TRIES_FACTOR = 3  # look at up to this many times the number we want, since the judge says no


def _subject(site: SiteConfig, kind: str) -> str:
    if kind == "site":
        return f"{site.name} ({site.city}, {site.state} State, Nigeria), a heritage site"
    return f"a road, highway, bridge or traffic scene on the way to {site.name}"


def collect_images(
    site: SiteConfig,
    fetcher: Fetcher,
    *,
    judge: ImageJudge | None = None,
    out_dir: Path = IMAGES_DIR,
    now: datetime | None = None,
) -> tuple[ImageManifest, Report]:
    """Collect photos. Title and licence rules cannot tell a road from a building beside it, or
    keep people out of frame, so a judge looks at each picture. Without one, road photos are
    skipped and site photos are kept unchecked."""
    now = now or datetime.now(UTC)
    report = Report()
    base = out_dir / site.id
    base.mkdir(parents=True, exist_ok=True)
    records: list[ImageRecord] = []
    judged: dict[str, str] = {}
    for kind, queries in (("site", site.images.site), ("road", site.images.roads)):
        if kind == "road" and queries and judge is None:
            report.errors.append("road photos skipped: no image judge (set LLM_API_KEY)")
            continue
        wanted = MAX_PER_KIND[kind]
        tries = 0
        for c in _select(fetcher, queries, kind, report):
            if report.kept[kind] >= wanted or tries >= wanted * MAX_TRIES_FACTOR:
                break
            tries += 1
            try:
                blob = download(fetcher, c.thumb_url)
            except httpx.HTTPError as exc:
                report.download_failures += 1
                report.errors.append(f"download failed for {c.title!r}: {exc}")
                continue
            if blob is None:
                report.rejected["file too big or not an image"] += 1
                continue
            note = "not checked by a judge"
            if judge is not None:
                verdict = judge.check(
                    blob, c.mime, subject=_subject(site, kind), caption=caption(c)
                )
                report.judge_calls += 1
                if verdict is None:
                    report.undecided += 1
                    report.rejected["judge could not decide"] += 1
                    continue
                if problem := verdict_problem(verdict):
                    report.rejected[problem] += 1
                    continue
                note = verdict.reason
            record, filename = _record(site.id, c, blob, now.date())
            if any(r.id == record.id for r in records):
                continue  # the same picture under two titles
            (base / filename).write_bytes(blob)
            records.append(record)
            judged[record.id] = note
            report.kept[kind] += 1
    manifest = ImageManifest(
        site_id=site.id,
        collected_at=now,
        images=records,
        judge=judge.name if judge else "",
        judged=judged,
    )
    return manifest, report


def prune(folder: Path, keep: set[str]) -> int:
    """Remove image files from earlier runs that the new manifest no longer lists, so a photo
    that was rejected can never ship by accident. Only .jpg and .png files are touched."""
    removed = 0
    for file in folder.iterdir():
        if file.suffix in (".jpg", ".png") and file.name not in keep:
            file.unlink()
            removed += 1
    return removed


def save_collection(manifest: ImageManifest, report: Report, base: Path) -> str | None:
    """Write the manifest and review sheet, and remove files it no longer lists.

    Returns None when saved. Otherwise returns why it refused, having touched nothing: a run
    that saw only part of the picture must not replace a good set of images.
    """
    if report.judge_broken:
        return f"the judge failed on {report.undecided} of {report.judge_calls} photos"
    if report.incomplete:
        return (
            f"{report.search_failures} searches and {report.download_failures} downloads failed "
            "(network or Wikimedia trouble)"
        )
    existing = load_manifest(manifest.site_id, base.parent)
    if not manifest.images and existing and existing.images:
        return f"it found no images, but {len(existing.images)} are already stored"
    base.mkdir(parents=True, exist_ok=True)
    (base / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    write_review(manifest, base / "review.md")
    prune(base, {r.path.rsplit("/", 1)[-1] for r in manifest.images})
    return None


def load_manifest(site_id: str, base: Path = IMAGES_DIR) -> ImageManifest | None:
    file = base / site_id / "manifest.json"
    return ImageManifest.model_validate_json(file.read_text()) if file.exists() else None


def write_review(manifest: ImageManifest, path: Path) -> None:
    """A sheet for checking each image against its Commons page before it ships."""
    lines = [f"# Hand-check images: {manifest.site_id} ({len(manifest.images)} images)", ""]
    for r in manifest.images:
        lines += [
            f"## {r.path.rsplit('/', 1)[-1]} [{r.kind}, {r.confidence}]",
            f"- caption: {r.summary}",
            f"- credit: {r.credit}",
            f"- licence: {r.license} {r.license_url or ''}",
            f"- page: {r.source.url}",
            f"- size: {r.width}x{r.height}, {r.size_bytes / 1000:.0f} KB",
            f"- judge ({manifest.judge or 'none'}): {manifest.judged.get(r.id, 'not checked')}",
            (
                "- [ ] shows what the caption says   [ ] licence confirmed on the page   "
                "[ ] suitable (no one identifiable, nothing sacred shown disrespectfully)"
            ),
            "",
        ]
    path.write_text("\n".join(lines))
