from typing import Generator
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """
    Provides an in-process HTTP TestClient for FastAPI endpoints.
    Allows testing HTTP responses without binding to a physical network socket.
    """
    with TestClient(app) as test_client:
        yield test_client
