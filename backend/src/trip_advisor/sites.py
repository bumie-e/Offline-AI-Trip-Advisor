"""Per-site configuration loaded from data/sites/*.toml."""

import tomllib
from pathlib import Path

from pydantic import Field

from trip_advisor.schemas.common import Strict

SITES_DIR = Path("data/sites")


class Endpoint(Strict):
    query: str  # label, and the Nominatim search used when coordinates are not pinned
    lat: float | None = None  # pin both to skip geocoding (verified, reproducible)
    lon: float | None = None

    @property
    def pinned(self) -> bool:
        return self.lat is not None and self.lon is not None


class Variant(Strict):
    """A hand-specified alternative road, routed through the given waypoints."""

    id: str
    label: str
    via: list[Endpoint]


class Corridor(Strict):
    """A road or road group whose recent condition we need evidence for."""

    name: str
    queries: list[str]
    match_terms: list[str]  # title/text must mention one of these
    primary: bool = False


class ImageQueries(Strict):
    """Wikimedia Commons search terms. Every word of a term must appear in a file's title or
    description, so keep them specific."""

    site: list[str] = Field(default_factory=list)  # the heritage site itself
    roads: list[str] = Field(default_factory=list)  # roads or towns on the way


def needs_geocoding(site: "SiteConfig") -> bool:
    points = [site.origin, site.destination, *(v for var in site.variants for v in var.via)]
    return not all(p.pinned for p in points)


class SiteConfig(Strict):
    id: str
    name: str
    city: str
    state: str
    origin: Endpoint
    destination: Endpoint
    variants: list[Variant] = Field(default_factory=list)
    corridors: list[Corridor]
    wikivoyage_pages: list[str] = Field(default_factory=list)
    images: ImageQueries = Field(default_factory=ImageQueries)


def load_site(site_id: str, sites_dir: Path = SITES_DIR) -> SiteConfig:
    data = tomllib.loads((sites_dir / f"{site_id}.toml").read_text())
    return SiteConfig.model_validate(data)


def list_sites(sites_dir: Path = SITES_DIR) -> list[str]:
    return sorted(p.stem for p in sites_dir.glob("*.toml"))
