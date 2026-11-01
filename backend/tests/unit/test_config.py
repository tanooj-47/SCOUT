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


def test_database_url_construction():
    """Verify that SQLALCHEMY_DATABASE_URI constructs a valid, typed URL object."""
    custom_settings = Settings(
        POSTGRES_SERVER="192.168.1.50",
        POSTGRES_PORT=5433,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="secure_password",
        POSTGRES_DB="test_crisis_db",
    )
    url = custom_settings.SQLALCHEMY_DATABASE_URI
    assert url.drivername == "postgresql+psycopg2"
    assert url.host == "192.168.1.50"
    assert url.port == 5433
    assert url.username == "test_user"
    assert url.password == "secure_password"
    assert url.database == "test_crisis_db"


def test_special_character_escaping_in_database_url():
    """Verify that special characters in passwords and usernames are safely escaped by URL.create."""
    special_password = "p@$$w0rd/with?special#chars&percent%"
    custom_settings = Settings(
        POSTGRES_USER="scout_user",
        POSTGRES_PASSWORD=special_password,
        POSTGRES_SERVER="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="scout",
    )
    url = custom_settings.SQLALCHEMY_DATABASE_URI
    assert url.password == special_password
    rendered = url.render_as_string(hide_password=False)
    # Confirm URL renders without raising syntax or escaping exceptions
    assert "postgresql+psycopg2://scout_user:" in rendered
    assert "/scout" in rendered


def test_masked_database_uri():
    """Verify that get_masked_database_uri obscures password with asterisks."""
    custom_settings = Settings(
        POSTGRES_USER="scout_admin",
        POSTGRES_PASSWORD="super_secret_password_123",
        POSTGRES_SERVER="db.internal",
        POSTGRES_PORT=5432,
        POSTGRES_DB="scout_prod",
    )
    masked = custom_settings.get_masked_database_uri()
    assert "super_secret_password_123" not in masked
    assert "***" in masked
    assert "scout_admin" in masked
    assert "db.internal" in masked
    assert "scout_prod" in masked


def test_storage_settings():
    """Verify default storage directories and relative path assembly."""
    settings = Settings()
    assert settings.STORAGE_DIR == PROJECT_ROOT / "storage"
    assert settings.MEDIA_STORAGE_DIR == PROJECT_ROOT / "storage" / "media"
    assert settings.TEMP_STORAGE_DIR == PROJECT_ROOT / "storage" / "tmp"
    assert settings.MAX_UPLOAD_SIZE_BYTES == 10 * 1024 * 1024

    # Relative path resolution
    custom = Settings(STORAGE_DIR="custom_storage")
    assert custom.STORAGE_DIR == PROJECT_ROOT / "custom_storage"
    assert custom.MEDIA_STORAGE_DIR == PROJECT_ROOT / "custom_storage" / "media"


def test_geospatial_priority_threshold_config():
    """Verify default and validated operational priority threshold configuration."""
    import pytest
    import pydantic

    # Default value must be 1000.0 meters
    s_default = Settings()
    assert s_default.GEOSPATIAL_PRIORITY_THRESHOLD_METERS == 1000.0

    # Custom valid positive threshold
    s_custom = Settings(GEOSPATIAL_PRIORITY_THRESHOLD_METERS=2500.0)
    assert s_custom.GEOSPATIAL_PRIORITY_THRESHOLD_METERS == 2500.0

    # Invalid negative, zero, and non-finite values must be rejected
    with pytest.raises(pydantic.ValidationError):
        Settings(GEOSPATIAL_PRIORITY_THRESHOLD_METERS=-100.0)

    with pytest.raises(pydantic.ValidationError):
        Settings(GEOSPATIAL_PRIORITY_THRESHOLD_METERS=0.0)

    with pytest.raises(pydantic.ValidationError):
        Settings(GEOSPATIAL_PRIORITY_THRESHOLD_METERS=float("nan"))

