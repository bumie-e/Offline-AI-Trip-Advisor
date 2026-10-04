from pathlib import Path

from fastapi import APIRouter, Depends

from trip_advisor.api.deps import data_dir, site_or_404
from trip_advisor.schemas.api import PlaceSummary
from trip_advisor.schemas.pack import Pack
from trip_advisor.sites import SiteConfig, list_sites, load_site

router = APIRouter(prefix="/places", tags=["places"])


def summary(site: SiteConfig, base: Path) -> PlaceSummary:
    pack_file = base / "packs" / site.id / "pack.json"
    pack = Pack.model_validate_json(pack_file.read_text()) if pack_file.exists() else None
    return PlaceSummary(
        id=site.id, name=site.name, city=site.city, state=site.state,
        pack_version=pack.version if pack else None,
        pack_bytes=pack_file.stat().st_size if pack else None,
        pack_generated_at=pack.generated_at if pack else None,
    )  # fmt: skip


@router.get("", response_model=list[PlaceSummary])
def places(base: Path = Depends(data_dir)) -> list[PlaceSummary]:
    return [summary(load_site(i, base / "sites"), base) for i in list_sites(base / "sites")]


@router.get("/{site_id}", response_model=PlaceSummary)
def place(site: SiteConfig = Depends(site_or_404), base: Path = Depends(data_dir)) -> PlaceSummary:
    return summary(site, base)
