from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import engine, get_db
from app.main import app


def pytest_configure(config):
    """Register custom markers so tests run cleanly with or without explicit ini discovery."""
    config.addinivalue_line(
        "markers",
        "database: Integration tests requiring a live PostgreSQL/PostGIS container",
    )


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """
    Standard in-process HTTP TestClient for endpoints not requiring database access
    (e.g. root navigational links, application liveness probes).
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Dedicated transactional session fixture for database-backed tests.
    Uses join_transaction_mode="create_savepoint" so service-level session.commit()
    calls are absorbed by savepoints and rolled back atomically with the outer transaction.
    Guarantees nested try/finally cleanup so connection and transaction are always closed.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        try:
            session.close()
        finally:
            try:
                transaction.rollback()
            finally:
                connection.close()
                engine.dispose()


@pytest.fixture(scope="function")
def db_client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Database-backed TestClient with get_db overridden to use the savepoint-isolated session.
    Preserves and restores existing dependency overrides safely.
    """
    saved_overrides = dict(app.dependency_overrides)
    try:
        app.dependency_overrides[get_db] = lambda: db_session
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides = saved_overrides
