"""Daily rain forecast from Open-Meteo (free, no API key)."""

from datetime import date, timedelta
from typing import Any

from trip_advisor.pipeline.collect.http import Fetcher
from trip_advisor.schemas.delta import WeatherEntry

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MAX_FORECAST_DAYS = 16  # Open-Meteo's limit; later dates are an error


def clamp_range(start: date, end: date, today: date) -> tuple[date, date]:
    """Keep the range inside what the API can forecast. May come back empty (start > end)."""
    return max(start, today), min(end, today + timedelta(days=MAX_FORECAST_DAYS - 1))


def parse_forecast(data: dict[str, Any], area: str) -> list[WeatherEntry]:
    daily = data.get("daily") or {}
    days, probs = daily.get("time") or [], daily.get("precipitation_probability_max") or []
    return [
        WeatherEntry(date=date.fromisoformat(d), area=area, rain_probability=round(p / 100, 2))
        for d, p in zip(days, probs, strict=False)
        if p is not None  # the API returns null beyond its reliable horizon
    ]


def fetch_weather(
    fetcher: Fetcher, *, lat: float, lon: float, area: str, start: date, end: date, today: date
) -> list[WeatherEntry]:
    start, end = clamp_range(start, end, today)
    if start > end:
        return []
    resp = fetcher.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "precipitation_probability_max",
            "timezone": "Africa/Lagos",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    return parse_forecast(resp.json(), area)
