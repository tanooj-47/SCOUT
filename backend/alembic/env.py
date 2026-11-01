import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# Ensure backend directory is in sys.path for absolute imports
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings
from app.models.base import Base
import geoalchemy2  # noqa: F401 - Register GeoAlchemy2 spatial reflection types

# Alembic Config object, which provides access to the values within the .ini file in use.
# Safely handle when imported outside Alembic's CLI runner
config = getattr(context, "config", None)

# Interpret the config file for Python logging.
if config is not None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata object for 'autogenerate' support
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """
    Schema-aware object filter for Alembic autogeneration.
    Explicitly excludes PostGIS extension-managed schemas and internal tables
    so that migrations never attempt to modify or drop PostGIS system objects.
    """
    if type_ == "table":
        # Ignore tables in PostGIS / Tiger / Topology extension schemas
        schema = getattr(object, "schema", None)
        if schema in ("tiger", "tiger_data", "topology"):
            return False

        # Ignore core PostGIS system and catalog tables
        if name in (
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
            "raster_columns",
            "raster_overviews",
        ):
            return False

        # Ignore extension table prefixes
        if name.startswith(("tiger_", "topology_")):
            return False

    return True


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we don't
    even need a DBAPI to be available. Calls to context.execute() here emit the
    given string to the script output.
    """
    url = settings.SQLALCHEMY_DATABASE_URI
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we create an Engine and associate a connection with the
    context. We pass the SQLAlchemy URL object directly to create_engine() with
    NullPool, avoiding ConfigParser percent-interpolation issues with special
    characters in passwords.
    """
    connectable = create_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# Execute migrations only when invoked inside an active Alembic CLI execution context
if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
