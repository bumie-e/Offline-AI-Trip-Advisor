from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bright_data_api_key: str = ""
    bright_data_unlocker_zone: str = ""  # Web Unlocker zone: fetches full pages
    bright_data_serp_zone: str = ""  # SERP API zone: dated Google News results
    bright_data_max_requests: int = 60  # per-run cost guard
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"  # extraction model for the structure phase
    generation_model: str = "claude-sonnet-5-5"  # itinerary writer
    weather_api_key: str = ""
    elevenlabs_api_key: str = ""
    database_url: str = ""  # Supabase Postgres pooler URL; reports are disabled while empty
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"  # packs, deltas, sites


settings = Settings()
