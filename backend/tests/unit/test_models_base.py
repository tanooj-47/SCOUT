from app.models.base import Base, POSTGRES_NAMING_CONVENTION
# Importing app.models ensures all 5 entities are registered on Base.metadata
import app.models  # noqa: F401


def test_declarative_base_naming_conventions():
    """Verify that Base has standardized PostgreSQL naming conventions attached."""
    assert Base.metadata.naming_convention == POSTGRES_NAMING_CONVENTION
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert Base.metadata.naming_convention["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert Base.metadata.naming_convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert Base.metadata.naming_convention["ck"] == "ck_%(table_name)s_%(constraint_name)s"
    assert Base.metadata.naming_convention["ix"] == "ix_%(column_0_label)s"


def test_approved_tables_registered():
    """
    Verify that in Milestone 03, exactly the five approved SCOUT entity tables
    are registered in Base.metadata.
    """
    expected_tables = {
        "incidents",
        "uploaded_media",
        "detection_results",
        "environmental_observations",
        "hazard_predictions",
        "incident_environmental_observations",
        "geographic_data_sources",
        "geographic_ingestion_runs",
        "geographic_features",
        "disaster_workflow_records",
        "workflow_approval_history",
    }
    assert set(Base.metadata.tables.keys()) == expected_tables
