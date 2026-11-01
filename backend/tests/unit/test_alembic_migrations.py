import subprocess
import sys
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory

backend_dir = Path(__file__).resolve().parent.parent.parent
ini_path = backend_dir / "alembic.ini"


def test_alembic_discovers_migration_history():
    """Verify that Alembic discovers the schema migration scripts."""
    alembic_cfg = Config(str(ini_path))
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "0004_disaster_workflow_records"

    revision1 = script.get_revision("0001_initial_schema")
    assert revision1 is not None
    assert revision1.down_revision is None

    revision2 = script.get_revision("0002_environmental_observations_upgrade")
    assert revision2 is not None
    assert revision2.down_revision == "0001_initial_schema"

    revision3 = script.get_revision("0003_persistent_geospatial_features")
    assert revision3 is not None
    assert revision3.down_revision == "0002_environmental_observations_upgrade"

    revision4 = script.get_revision("0004_disaster_workflow_records")
    assert revision4 is not None
    assert revision4.down_revision == "0003_persistent_geospatial_features"


def test_offline_sql_upgrade_generation():
    """Verify that alembic upgrade head --sql generates valid DDL without database connection."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ini_path),
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=str(backend_dir.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Alembic offline upgrade failed:\n{result.stderr}"
    sql_output = result.stdout

    # Verify all 10 tables are created
    assert "CREATE TABLE incidents" in sql_output
    assert "CREATE TABLE uploaded_media" in sql_output
    assert "CREATE TABLE detection_results" in sql_output
    assert "CREATE TABLE environmental_observations" in sql_output
    assert "CREATE TABLE hazard_predictions" in sql_output
    assert "CREATE TABLE geographic_data_sources" in sql_output
    assert "CREATE TABLE geographic_ingestion_runs" in sql_output
    assert "CREATE TABLE geographic_features" in sql_output
    assert "CREATE TABLE disaster_workflow_records" in sql_output
    assert "CREATE TABLE workflow_approval_history" in sql_output
    assert "uq_geo_features_source_feature_layer" in sql_output
    assert "ix_geo_features_layer_category" in sql_output

    # Verify spatial columns and indexes are included
    assert "geometry(POINT,4326)" in sql_output
    assert "geometry(MULTIPOLYGON,4326)" in sql_output
    assert "USING gist ((location::geography))" in sql_output
    assert "USING gist ((predicted_footprint::geography))" in sql_output

    # Verify RESTRICT foreign key policies
    assert "ON DELETE RESTRICT" in sql_output

    # Verify no duplicate spatial indexes in generated DDL
    assert "CREATE INDEX idx_incidents_location " not in sql_output
    assert "CREATE INDEX idx_incidents_observed_perimeter " not in sql_output
    assert "CREATE INDEX idx_uploaded_media_capture_location " not in sql_output
    assert "CREATE INDEX idx_hazard_predictions_predicted_footprint " not in sql_output

    # Verify exact approved column names and absence of legacy/unapproved names
    assert "incident_code" not in sql_output
    assert "relative_humidity_percent" not in sql_output
    assert "wind_speed_kmh" not in sql_output
    assert "prediction_horizon_hours" not in sql_output
    assert "predicted_area_hectares" not in sql_output
    assert "projected_area_hectares FLOAT NOT NULL" in sql_output


def test_offline_sql_downgrade_generation():
    """Verify that alembic downgrade base --sql generates clean drop table statements in reverse order."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ini_path),
            "downgrade",
            "0001_initial_schema:base",
            "--sql",
        ],
        cwd=str(backend_dir.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Alembic offline downgrade failed:\n{result.stderr}"
    sql_output = result.stdout

    # Verify reverse dependency order of drops
    pred_pos = sql_output.find("DROP TABLE hazard_predictions;")
    obs_pos = sql_output.find("DROP TABLE environmental_observations;")
    det_pos = sql_output.find("DROP TABLE detection_results;")
    media_pos = sql_output.find("DROP TABLE uploaded_media;")
    inc_pos = sql_output.find("DROP TABLE incidents;")

    assert pred_pos != -1 and obs_pos != -1 and det_pos != -1 and media_pos != -1 and inc_pos != -1
    assert pred_pos < obs_pos < det_pos < media_pos < inc_pos
