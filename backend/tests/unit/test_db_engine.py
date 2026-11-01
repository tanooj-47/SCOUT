from app.db.session import engine


def test_engine_dialect_and_driver():
    """Verify that engine is configured with PostgreSQL dialect and psycopg2 driver."""
    assert engine.dialect.name == "postgresql"
    assert engine.driver == "psycopg2"


def test_engine_pool_configuration():
    """Verify pool_pre_ping and pooling parameters on the engine."""
    assert engine.pool._pre_ping is True
    assert engine.echo is False


def test_engine_lazy_initialization():
    """
    Verify that engine exists without active connections checkout.
    create_engine is lazy and does not contact the PostgreSQL server on instantiation.
    """
    assert engine.pool.checkedin() == 0
    assert engine.pool.checkedout() == 0
