from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Synchronous SQLAlchemy 2.0 Engine
# Engine instantiation is lazy; no connection is established upon module import.
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=False,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
)

# Thread-safe Session Factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields an independent database session per request.
    Guarantees session cleanup via a try/finally block, releasing the connection
    back to the pool even when an unhandled exception or HTTP error occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
