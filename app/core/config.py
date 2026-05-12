"""
ClimaSync Collection Service — Configuration

ONE place where all .env variables are loaded.
No other file reads .env directly — every file imports Settings from here.

If any required variable is missing, the service refuses to start.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigurationError

# ── Timezone ────────────────────────────────────────────────────────
# Pakistan Standard Time — used everywhere in the service
PKT_TIMEZONE = "Asia/Karachi"


class Settings(BaseSettings):
    """All environment variables loaded and validated in one place.

    Pydantic Settings reads from .env automatically via the model_config.
    """

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────
    collection_db_host: str = Field(..., description="Supabase PostgreSQL hostname")
    collection_db_port: int = Field(default=5432, description="Database port")
    collection_db_name: str = Field(default="postgres", description="Database name")
    collection_db_user: str = Field(..., description="Database username")
    collection_db_password: str = Field(..., description="Database password")
    collection_db_pool_min: int = Field(default=2, ge=1, le=100, description="Min pool connections")
    collection_db_pool_max: int = Field(default=10, ge=1, le=100, description="Max pool connections")

    # ── Main System Connection ──────────────────────────────────
    main_system_base_url: str = Field(..., description="Main ClimaSync API base URL")
    main_system_api_key: str = Field(..., description="Internal API key for main system auth")

    # ── USGS Earthquake API ─────────────────────────────────────
    usgs_base_url: str = Field(
        default="https://earthquake.usgs.gov/fdsnws/event/1/query",
        description="USGS earthquake API endpoint",
    )
    usgs_min_magnitude: float = Field(default=2.5, ge=0.0, le=5.0, description="Minimum earthquake magnitude to capture")
    usgs_lookback_hours: int = Field(default=6, ge=1, le=24, description="Hours of overlap for USGS updates")
    usgs_poll_interval_seconds: int = Field(default=300, ge=60, description="Seconds between USGS polls")

    # ── Open-Meteo Weather API ──────────────────────────────────
    openmeteo_base_url: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        description="Open-Meteo weather API endpoint",
    )
    openmeteo_poll_interval_minutes: int = Field(default=120, ge=1, description="Minutes between weather poll checks")
    openmeteo_request_delay_ms: int = Field(default=500, ge=0, description="Delay between location requests (ms)")

    # ── Google Flood Hub API ────────────────────────────────────
    google_flood_hub_base_url: str = Field(
        default="https://floodforecasting.googleapis.com/v1",
        description="Google Flood Forecasting API endpoint",
    )
    google_flood_hub_api_key: str = Field(default="", description="Google Cloud API key for Flood Hub")

    # ── Pakistan Geographic Bounds ──────────────────────────────
    pakistan_min_lat: float = Field(default=23.0, description="Pakistan southern latitude")
    pakistan_max_lat: float = Field(default=38.0, description="Pakistan northern latitude")
    pakistan_min_lon: float = Field(default=60.0, description="Pakistan western longitude")
    pakistan_max_lon: float = Field(default=78.0, description="Pakistan eastern longitude")

    # ── Collection Intervals ────────────────────────────────────
    flood_current_interval_minutes: int = Field(default=60, ge=1, description="Minutes between flood gauge current polls")
    flood_forecast_interval_hours: int = Field(default=6, ge=1, description="Hours between flood forecast polls")
    breach_dispatch_interval_seconds: int = Field(default=30, ge=1, description="Seconds between breach dispatch attempts")
    threshold_reload_interval_hours: int = Field(default=1, ge=1, description="Hours between threshold cache reloads")
    cleanup_hour_pkt: int = Field(default=0, ge=0, le=23, description="Hour (PKT) for daily cleanup job")
    cleanup_minute_pkt: int = Field(default=5, ge=0, le=59, description="Minute (PKT) for daily cleanup job")

    # ── Application ─────────────────────────────────────────────
    app_port: int = Field(default=8000, ge=1, le=65535, description="Port the service listens on")
    app_env: Literal["development", "production"] = Field(default="development", description="Runtime environment")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging verbosity level"
    )
    service_name: str = Field(default="climasync-collection", description="Service identifier used in logs")

    # ── Dispatch Settings ───────────────────────────────────────
    max_dispatch_attempts: int = Field(default=5, ge=1, description="Max dispatch retries per breach")
    dispatch_batch_size: int = Field(default=10, ge=1, description="Breaches dispatched per cycle")

    # ── Rate Limiting Defaults ──────────────────────────────────
    api_backoff_initial_s: float = Field(default=10.0, ge=1, description="Initial backoff seconds on rate limit")
    api_backoff_multiplier: float = Field(default=2.0, ge=1, description="Backoff exponential multiplier")
    api_backoff_max_s: float = Field(default=600.0, ge=10, description="Maximum backoff seconds")

    # ── Validation ──────────────────────────────────────────────

    @field_validator("collection_db_host", "collection_db_password", "main_system_api_key")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ConfigurationError("Field cannot be empty")
        return v

    @field_validator("main_system_base_url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ConfigurationError(f"main_system_base_url must start with http:// or https://, got: {v}")
        return v.rstrip("/")

    @property
    def database_dsn(self) -> str:
        """Build the asyncpg-compatible DSN from individual components.

        Password is URL-encoded to handle special characters (@, :, /, etc).
        """
        return (
            f"postgresql://{self.collection_db_user}:{quote_plus(self.collection_db_password)}"
            f"@{self.collection_db_host}:{self.collection_db_port}"
            f"/{self.collection_db_name}"
        )

    @property
    def pakistan_bounding_box(self) -> tuple[float, float, float, float]:
        """Return (min_lat, max_lat, min_lon, max_lon) for Pakistan."""
        return (
            self.pakistan_min_lat,
            self.pakistan_max_lat,
            self.pakistan_min_lon,
            self.pakistan_max_lon,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    The cache ensures environment variables are only read once at startup.
    Use settings.reload() during testing if you need to refresh values.
    """
    return Settings()
