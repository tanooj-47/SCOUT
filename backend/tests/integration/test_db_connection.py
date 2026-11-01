import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.db.session import engine


@pytest.mark.database
def test_live_database_connection():
    """
    Live database integration test.
    Attempts to connect to PostgreSQL/PostGIS.
    If the database is offline or unreachable, skips safely.
    If the database connects, asserts that PostgreSQL and PostGIS are functional.
    Does NOT swallow assertion or programming errors.
    """
    try:
        try:
            connection = engine.connect()
        except OperationalError as exc:
            pytest.skip(f"Live database is offline/unreachable on {engine.url.host}:{engine.url.port}: {exc}")

        with connection:
            result = connection.execute(text("SELECT 1")).scalar()
            assert result == 1

            # Test PostGIS extension availability
            postgis_version = connection.execute(text("SELECT PostGIS_Full_Version();")).scalar()
            assert postgis_version is not None
            assert "POSTGIS" in postgis_version
    finally:
        engine.dispose()
