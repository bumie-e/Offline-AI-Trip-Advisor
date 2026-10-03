from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bright_data_api_key: str = ""
    llm_api_key: str = ""
    weather_api_key: str = ""
    elevenlabs_api_key: str = ""
    database_url: str = "sqlite:///./data/app.db"


settings = Settings()
