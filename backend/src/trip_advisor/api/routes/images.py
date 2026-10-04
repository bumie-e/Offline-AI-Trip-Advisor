from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from trip_advisor.api.deps import data_dir, site_or_404
from trip_advisor.pipeline.collect.images import load_manifest
from trip_advisor.schemas.pack import ImageRecord
from trip_advisor.sites import SiteConfig

router = APIRouter(prefix="/images", tags=["images"])

# The id in the file name is a hash of the content, so a given URL never changes.
CACHE = "public, max-age=31536000, immutable"


def _records(site_id: str, base: Path) -> list[ImageRecord]:
    manifest = load_manifest(site_id, base / "images")
    return manifest.images if manifest else []


@router.get("/{site_id}", response_model=list[ImageRecord])
def list_images(
    site: SiteConfig = Depends(site_or_404), base: Path = Depends(data_dir)
) -> list[ImageRecord]:
    """Photos of the site and its roads, with the credit to show beside each."""
    return _records(site.id, base)


@router.get("/{site_id}/{filename}")
def get_image(
    filename: str,
    request: Request,
    site: SiteConfig = Depends(site_or_404),
    base: Path = Depends(data_dir),
) -> Response:
    """One image file. Only files named in the manifest are served, whatever the path says."""
    record = next(
        (r for r in _records(site.id, base) if r.path.rsplit("/", 1)[-1] == filename), None
    )
    file = base / "images" / site.id / filename
    if record is None or not file.is_file():
        raise HTTPException(404, "No such image")
    etag = f'"{record.id}"'
    headers = {"Cache-Control": CACHE, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(file, media_type=record.mime, headers=headers)
