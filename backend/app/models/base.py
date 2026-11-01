from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# PostgreSQL Constraint Naming Conventions
# Standardizes constraint names across Alembic migrations and database engines
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    Root DeclarativeBase for all SCOUT models.
    Enforces standardized naming conventions and exports metadata for Alembic migrations.
    """
    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)
