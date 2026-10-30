from pathlib import Path
from app.core.config import Settings, PROJECT_ROOT, ENV_FILE_PATH


def test_default_settings():
    """Verify standard default configuration values."""
    settings = Settings()
    assert settings.PROJECT_NAME == "SCOUT"
    assert settings.APP_ENV == "development"
    assert settings.DEBUG is True
    assert settings.API_V1_STR == "/api/v1"
    assert isinstance(settings.ALLOWED_ORIGINS, list)
    assert len(settings.ALLOWED_ORIGINS) >= 1


def test_cors_origins_parsing():
    """Verify that ALLOWED_ORIGINS parses JSON lists and comma-separated strings."""
    # Test JSON list string
    settings_json = Settings(ALLOWED_ORIGINS='["http://localhost:8080", "https://scout.internal"]')
    assert settings_json.ALLOWED_ORIGINS == ["http://localhost:8080", "https://scout.internal"]

    # Test comma-separated string
    settings_csv = Settings(ALLOWED_ORIGINS="http://localhost:8080, https://scout.internal")
    assert settings_csv.ALLOWED_ORIGINS == ["http://localhost:8080", "https://scout.internal"]

    # Test direct list
    settings_list = Settings(ALLOWED_ORIGINS=["http://test.com"])
    assert settings_list.ALLOWED_ORIGINS == ["http://test.com"]


def test_resolved_paths():
    """Verify project root path resolution."""
    assert isinstance(PROJECT_ROOT, Path)
    assert isinstance(ENV_FILE_PATH, Path)
    assert ENV_FILE_PATH.name == ".env"
    assert PROJECT_ROOT.is_dir()
