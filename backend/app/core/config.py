from pathlib import Path
from typing import List, Union
import json
import math
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# Determine absolute path to project root and backend directory
# File location: <PROJECT_ROOT>/backend/app/core/config.py
CORE_DIR = Path(__file__).resolve().parent
APP_DIR = CORE_DIR.parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

ENV_FILE_PATH = PROJECT_ROOT / ".env"
BACKEND_ENV_FILE_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """
    Application Settings powered by Pydantic Settings.
    Loads configuration from environment variables and/or .env files,
    resolving paths relative to the project root directory.
    """

    model_config = SettingsConfigDict(
        # Check root .env first, then backend/.env if present
        env_file=(str(ENV_FILE_PATH), str(BACKEND_ENV_FILE_PATH)),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Environment
    APP_ENV: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "SCOUT"
    API_V1_STR: str = "/api/v1"

    # CORS Allowed Origins
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Logging
    LOG_LEVEL: str = "INFO"

    # Database Configuration
    POSTGRES_SERVER: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "scout_admin"
    POSTGRES_PASSWORD: str = "scout_dev_password"
    POSTGRES_DB: str = "scout"

    # Database Pool Configuration
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_PRE_PING: bool = True

    # Storage Configuration
    STORAGE_DIR: Path = PROJECT_ROOT / "storage"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB default

    # Geospatial Engine Configuration
    GEOSPATIAL_PRIORITY_THRESHOLD_METERS: float = 1000.0  # Operational high-priority exposure distance threshold

    # Environmental Subsystem Configuration
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1"
    NASA_POWER_BASE_URL: str = "https://power.larc.nasa.gov/api/temporal"
    ENVIRONMENTAL_REQUEST_TIMEOUT_SECONDS: float = 5.0
    ENVIRONMENTAL_MAX_RETRIES: int = 2
    ENVIRONMENTAL_BACKOFF_FACTOR: float = 0.5
    ENVIRONMENTAL_CURRENT_CACHE_TTL_SECONDS: int = 1800   # 30 minutes
    ENVIRONMENTAL_FORECAST_CACHE_TTL_SECONDS: int = 7200  # 2 hours
    ENVIRONMENTAL_HISTORICAL_CACHE_TTL_SECONDS: int = 86400  # 24 hours

    @property
    def MEDIA_STORAGE_DIR(self) -> Path:
        """Dedicated subdirectory for raster image files."""
        return self.STORAGE_DIR / "media"

    @property
    def TEMP_STORAGE_DIR(self) -> Path:
        """Dedicated subdirectory for staging in-flight uploads."""
        return self.STORAGE_DIR / "tmp"

    @field_validator("STORAGE_DIR", mode="before")
    @classmethod
    def assemble_storage_dir(cls, v: Union[str, Path]) -> Path:
        p = Path(v)
        if not p.is_absolute():
            return PROJECT_ROOT / p
        return p

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> URL:
        """
        Builds a safe, typed SQLAlchemy connection URL using URL.create.
        Special characters in usernames and passwords are automatically escaped.
        """
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    def get_masked_database_uri(self) -> str:
        """
        Returns the database URI with password masked.
        Safe for logs, exception reporting, and diagnostics.
        """
        return self.SQLALCHEMY_DATABASE_URI.render_as_string(hide_password=True)

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return v
        raise ValueError(f"Invalid format for ALLOWED_ORIGINS: {v}")

    @field_validator("GEOSPATIAL_PRIORITY_THRESHOLD_METERS")
    @classmethod
    def validate_geospatial_priority_threshold(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(
                f"GEOSPATIAL_PRIORITY_THRESHOLD_METERS must be a positive finite number, got {v}"
            )
        return float(v)


# Global settings instance
settings = Settings()
