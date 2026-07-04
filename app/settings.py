from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_BASE_URL = "http://localhost:8787"
LOCAL_GOOGLE_REDIRECT_URI = f"{LOCAL_BASE_URL}/oauth/callback/google"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    public_base_url: str = LOCAL_BASE_URL
    render_external_url: str = ""
    database_url: str = "sqlite:///./data/mehair-coach.sqlite3"
    libsql_auth_token: str = ""
    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = LOCAL_GOOGLE_REDIRECT_URI
    google_health_api_base: str = "https://health.googleapis.com/v4"
    app_scope: str = "health.read"
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    sync_lookback_days: int = 7
    sync_incremental_lookback_days: int = 2
    sync_incremental_overlap_hours: int = 2
    sync_min_interval_minutes: int = 15
    sync_on_connect: bool = True
    sync_metric_timeout_seconds: int = 4
    sync_request_budget_seconds: int = 16
    sync_metric_page_limit: int = 4
    sync_metric_concurrency: int = 6
    sync_metric_record_limit: int = 600
    sync_live_return_budget_seconds: int = 6
    sync_abandoned_after_minutes: int = 5
    host: str = "0.0.0.0"
    port: int = Field(default=8787, ge=1, le=65535)

    @property
    def base_url(self) -> str:
        if self.public_base_url.rstrip("/") == LOCAL_BASE_URL and self.render_external_url:
            return self.render_external_url.rstrip("/")
        return self.public_base_url.rstrip("/")

    @property
    def google_callback_url(self) -> str:
        if self.google_redirect_uri.rstrip("/") != LOCAL_GOOGLE_REDIRECT_URI:
            return self.google_redirect_uri.rstrip("/")
        return f"{self.base_url}/oauth/callback/google"

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("sqlite_path is only available when DATABASE_URL starts with sqlite:///")
        return Path(self.database_url.removeprefix("sqlite:///"))

    @property
    def mcp_allowed_hosts(self) -> list[str]:
        host = urlparse(self.base_url).netloc
        return [
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            *([host] if host else []),
        ]

    @property
    def mcp_allowed_origins(self) -> list[str]:
        return [
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            self.base_url,
            "https://chatgpt.com",
            "https://chat.openai.com",
        ]

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
