from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
import pytest
from app.db.session import SessionLocal, get_db


def test_session_factory():
    """Verify that SessionLocal is configured and instantiates a Session."""
    session = SessionLocal()
    assert isinstance(session, Session)
    # Clean up session
    session.close()


def test_get_db_yields_and_closes_normally():
    """Verify that get_db generator yields an active session and closes it cleanly."""
    mock_session = MagicMock(spec=Session)
    with patch("app.db.session.SessionLocal", return_value=mock_session):
        gen = get_db()
        db = next(gen)
        assert db == mock_session
        assert not mock_session.close.called

        # Complete generator lifecycle
        with pytest.raises(StopIteration):
            next(gen)

        assert mock_session.close.called
        assert mock_session.close.call_count == 1


def test_get_db_closes_on_exception():
    """Verify that get_db closes the session even if an exception is raised in request handling."""
    mock_session = MagicMock(spec=Session)
    with patch("app.db.session.SessionLocal", return_value=mock_session):
        gen = get_db()
        db = next(gen)
        assert db == mock_session

        # Simulate unhandled exception in endpoint
        with pytest.raises(RuntimeError, match="Endpoint processing failure"):
            try:
                raise RuntimeError("Endpoint processing failure")
            finally:
                gen.close()

        assert mock_session.close.called
