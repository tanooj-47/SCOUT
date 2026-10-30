from pathlib import Path
from typing import List, Union
import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


# Global settings instance
settings = Settings()
