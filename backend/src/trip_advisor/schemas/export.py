"""Export JSON Schema files for the app and on-device model teams."""

import json
from pathlib import Path

from pydantic import BaseModel

from .api import PlaceSummary, Receipt
from .delta import Delta
from .itinerary import Advice, Itinerary, TripRequest
from .pack import Pack, TripPack
from .reports import AdviceRating, RoadReport, SiteStatusReport

MODELS: dict[str, type[BaseModel]] = {
    "pack": Pack,
    "trip_pack": TripPack,
    "delta": Delta,
    "advice": Advice,
    "trip_request": TripRequest,
    "itinerary": Itinerary,
    "road_report": RoadReport,
    "site_status_report": SiteStatusReport,
    "advice_rating": AdviceRating,
    "place_summary": PlaceSummary,
    "receipt": Receipt,
}


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in MODELS.items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
        written.append(path)
    return written
