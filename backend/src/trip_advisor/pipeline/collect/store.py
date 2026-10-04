import json
from pathlib import Path

from pydantic import BaseModel

RAW_DIR = Path("data/raw")


def save(model: BaseModel, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
    return path


def site_dir(site_id: str, base: Path = RAW_DIR) -> Path:
    return base / site_id
