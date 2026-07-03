from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    public_base_url: str = "http://localhost:8787"
    database_url: str = "sqlite:///./data/mehair-coach.sqlite3"
    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8787/oauth/callback/google"
    google_health_api_base: str = "https://health.googleapis.com/v4"
    app_scope: str = "health.read"
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    sync_lookback_days: int = 7
    host: str = "0.0.0.0"
    port: int = Field(default=8787, ge=1, le=65535)

    @property
    def base_url(self) -> str:
        return self.public_base_url.rstrip("/")

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported in v1.")
        return Path(self.database_url.removeprefix("sqlite:///"))

    @property
    def google_scopes(self) -> list[str]:
        return [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
            "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
            "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
            "https://www.googleapis.com/auth/googlehealth.settings.readonly",
            "https://www.googleapis.com/auth/googlehealth.profile.readonly",
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
