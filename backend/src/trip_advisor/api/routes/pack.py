from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from trip_advisor.api.deps import data_dir, site_or_404
from trip_advisor.schemas.pack import Pack
from trip_advisor.sites import SiteConfig

router = APIRouter(prefix="/pack", tags=["pack"])


@router.get("/{site_id}", response_model=Pack)
def get_pack(
    request: Request,
    site: SiteConfig = Depends(site_or_404),
    base: Path = Depends(data_dir),
) -> Response:
    """The offline pack. The version is the ETag, so an unchanged pack costs a 304."""
    file = base / "packs" / site.id / "pack.json"
    if not file.exists():
        raise HTTPException(404, f"No pack has been built for {site.id!r}")
    raw = file.read_text()
    version = Pack.model_validate_json(raw).version
    etag = f'"{version}"'
    headers = {"ETag": etag, "X-Pack-Version": version, "Cache-Control": "public, max-age=3600"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=raw, media_type="application/json", headers=headers)
