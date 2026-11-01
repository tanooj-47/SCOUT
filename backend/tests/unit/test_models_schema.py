import uuid
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import class_mapper
from geoalchemy2 import Geometry

from app.models import (
    Incident,
    UploadedMedia,
    DetectionResult,
    EnvironmentalObservation,
    HazardPrediction,
)


def test_uuid_primary_keys():
    """Verify that all five models define a UUID primary key."""
    for model in [Incident, UploadedMedia, DetectionResult, EnvironmentalObservation, HazardPrediction]:
        table = model.__table__
        pk_col = table.primary_key.columns[0]
        assert pk_col.name == "id"
        assert isinstance(pk_col.type, UUID)
        assert pk_col.nullable is False


def test_spatial_column_types_and_srid():
    """Verify that spatial columns have exact expected geometry types and SRID 4326."""
    # Incident location
    loc_col = Incident.__table__.columns["location"]
    assert isinstance(loc_col.type, Geometry)
    assert loc_col.type.geometry_type == "POINT"
    assert loc_col.type.srid == 4326
    assert loc_col.nullable is False

    # Incident observed_perimeter
    perim_col = Incident.__table__.columns["observed_perimeter"]
    assert isinstance(perim_col.type, Geometry)
    assert perim_col.type.geometry_type == "MULTIPOLYGON"
    assert perim_col.type.srid == 4326
    assert perim_col.nullable is True

    # UploadedMedia capture_location
    media_loc = UploadedMedia.__table__.columns["capture_location"]
    assert isinstance(media_loc.type, Geometry)
    assert media_loc.type.geometry_type == "POINT"
    assert media_loc.type.srid == 4326
    assert media_loc.nullable is True

    # HazardPrediction predicted_footprint
    pred_footprint = HazardPrediction.__table__.columns["predicted_footprint"]
    assert isinstance(pred_footprint.type, Geometry)
    assert pred_footprint.type.geometry_type == "MULTIPOLYGON"
    assert pred_footprint.type.srid == 4326
    assert pred_footprint.nullable is False


def test_jsonb_columns():
    """Verify that metadata, bounding_boxes, metrics_payload, and input_snapshot use JSONB."""
    assert isinstance(Incident.__table__.columns["metadata"].type, JSONB)
    assert isinstance(DetectionResult.__table__.columns["bounding_boxes"].type, JSONB)
    assert isinstance(EnvironmentalObservation.__table__.columns["metrics_payload"].type, JSONB)
    assert isinstance(HazardPrediction.__table__.columns["input_snapshot"].type, JSONB)


def test_timezone_aware_timestamps():
    """Verify that all timestamp columns are timezone-aware."""
    timestamp_checks = [
        (Incident, "reported_at"),
        (Incident, "updated_at"),
        (Incident, "contained_at"),
        (Incident, "archived_at"),
        (Incident, "perimeter_updated_at"),
        (UploadedMedia, "captured_at"),
        (UploadedMedia, "created_at"),
        (DetectionResult, "created_at"),
        (EnvironmentalObservation, "recorded_at"),
        (EnvironmentalObservation, "created_at"),
        (HazardPrediction, "created_at"),
    ]
    for model, col_name in timestamp_checks:
        col = model.__table__.columns[col_name]
        assert col.type.timezone is True, f"{model.__name__}.{col_name} must have timezone=True"


def test_foreign_keys_and_restrict_policy():
    """Verify that all foreign keys enforce ON DELETE RESTRICT (no hard-cascades)."""
    fk_checks = [
        (UploadedMedia.__table__, "incident_id", "incidents.id", True),
        (DetectionResult.__table__, "media_id", "uploaded_media.id", False),
        (EnvironmentalObservation.__table__, "incident_id", "incidents.id", True),
        (HazardPrediction.__table__, "incident_id", "incidents.id", False),
        (HazardPrediction.__table__, "primary_observation_id", "environmental_observations.id", True),
    ]
    for table, col_name, target, is_nullable in fk_checks:
        col = table.columns[col_name]
        assert col.nullable is is_nullable, f"{table.name}.{col_name} nullable mismatch"
        assert len(col.foreign_keys) == 1
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == target
        assert fk.ondelete == "RESTRICT"


def test_relationships_and_back_populates():
    """Verify two-way relationships and back_populates configuration across all 5 models."""
    # Incident relationships
    inc_mapper = class_mapper(Incident)
    assert "uploaded_media" in inc_mapper.relationships
    assert inc_mapper.relationships["uploaded_media"].back_populates == "incident"
    assert "environmental_observations" in inc_mapper.relationships
    assert inc_mapper.relationships["environmental_observations"].back_populates == "incident"
    assert "hazard_predictions" in inc_mapper.relationships
    assert inc_mapper.relationships["hazard_predictions"].back_populates == "incident"

    # UploadedMedia relationships
    media_mapper = class_mapper(UploadedMedia)
    assert media_mapper.relationships["incident"].back_populates == "uploaded_media"
    assert media_mapper.relationships["detection_results"].back_populates == "media"

    # DetectionResult relationships
    det_mapper = class_mapper(DetectionResult)
    assert det_mapper.relationships["media"].back_populates == "detection_results"

    # EnvironmentalObservation relationships
    obs_mapper = class_mapper(EnvironmentalObservation)
    assert obs_mapper.relationships["incident"].back_populates == "environmental_observations"
    assert obs_mapper.relationships["hazard_predictions"].back_populates == "primary_observation"

    # HazardPrediction relationships
    pred_mapper = class_mapper(HazardPrediction)
    assert pred_mapper.relationships["incident"].back_populates == "hazard_predictions"
    assert pred_mapper.relationships["primary_observation"].back_populates == "hazard_predictions"


def test_check_constraints_present():
    """Verify that all required check constraints exist in model metadata."""
    def get_constraint_sql(table, name_fragment):
        matches = [c for c in table.constraints if name_fragment in str(c.name)]
        assert len(matches) >= 1, f"Missing constraint with fragment '{name_fragment}' in table {table.name}"
        return str(matches[0].sqltext)

    # Incident constraints
    assert "disaster_type IN" in get_constraint_sql(Incident.__table__, "ck_incidents_disaster_type")
    assert "status IN" in get_constraint_sql(Incident.__table__, "ck_incidents_status")
    assert "severity IN" in get_constraint_sql(Incident.__table__, "ck_incidents_severity")
    assert "is_archived" in get_constraint_sql(Incident.__table__, "ck_incidents_archival_consistency")

    # UploadedMedia constraints
    assert "file_size_bytes >= 0" in get_constraint_sql(UploadedMedia.__table__, "ck_uploaded_media_file_size_bytes")

    # DetectionResult constraints
    assert "classification IN" in get_constraint_sql(DetectionResult.__table__, "ck_detection_results_classification")
    assert "confidence >= 0" in get_constraint_sql(DetectionResult.__table__, "ck_detection_results_confidence")
    assert "inference_latency_ms >= 0" in get_constraint_sql(DetectionResult.__table__, "ck_detection_results_inference_latency_ms")

    # EnvironmentalObservation constraints
    assert "relative_humidity" in get_constraint_sql(EnvironmentalObservation.__table__, "ck_env_obs_relative_humidity")
    assert "wind_speed_mps" in get_constraint_sql(EnvironmentalObservation.__table__, "ck_env_obs_wind_speed_mps")
    assert "wind_direction_degrees" in get_constraint_sql(EnvironmentalObservation.__table__, "ck_env_obs_wind_direction_degrees")
    assert "precipitation_mm" in get_constraint_sql(EnvironmentalObservation.__table__, "ck_env_obs_precipitation_mm")

    # HazardPrediction constraints
    assert "forecast_horizon_hours > 0" in get_constraint_sql(HazardPrediction.__table__, "ck_hazard_predictions_forecast_horizon_hours")
    assert "projected_area_hectares >= 0" in get_constraint_sql(HazardPrediction.__table__, "ck_hazard_predictions_projected_area_hectares")
    assert "risk_level IN" in get_constraint_sql(HazardPrediction.__table__, "ck_hazard_predictions_risk_level")


def test_spatial_and_functional_indexes():
    """Verify that spatial GiST and functional geography indexes are registered without duplicates."""
    incident_indexes = {idx.name: idx for idx in Incident.__table__.indexes}
    assert "ix_incidents_location" in incident_indexes
    assert incident_indexes["ix_incidents_location"].dialect_options["postgresql"]["using"] == "gist"
    assert "ix_incidents_location_geography" in incident_indexes
    assert incident_indexes["ix_incidents_location_geography"].dialect_options["postgresql"]["using"] == "gist"
    assert "ix_incidents_observed_perimeter" in incident_indexes
    assert incident_indexes["ix_incidents_observed_perimeter"].dialect_options["postgresql"]["using"] == "gist"
    assert "ix_incidents_status_is_archived" in incident_indexes

    # Verify no duplicate automatic indexes exist on Incident
    assert "idx_incidents_location" not in incident_indexes
    assert "idx_incidents_observed_perimeter" not in incident_indexes

    media_indexes = {idx.name: idx for idx in UploadedMedia.__table__.indexes}
    assert "ix_uploaded_media_capture_location" in media_indexes
    assert media_indexes["ix_uploaded_media_capture_location"].dialect_options["postgresql"]["using"] == "gist"
    assert "idx_uploaded_media_capture_location" not in media_indexes

    prediction_indexes = {idx.name: idx for idx in HazardPrediction.__table__.indexes}
    assert "ix_hazard_predictions_predicted_footprint" in prediction_indexes
    assert prediction_indexes["ix_hazard_predictions_predicted_footprint"].dialect_options["postgresql"]["using"] == "gist"
    assert "ix_hazard_predictions_footprint_geography" in prediction_indexes
    assert prediction_indexes["ix_hazard_predictions_footprint_geography"].dialect_options["postgresql"]["using"] == "gist"
    assert "idx_hazard_predictions_predicted_footprint" not in prediction_indexes


def test_exact_columns_and_rejection_of_unapproved_fields():
    """Verify that every model defines only approved columns and rejects unapproved additions."""
    # 1. Incident
    incident_cols = set(Incident.__table__.columns.keys())
    expected_incident_cols = {
        "id", "disaster_type", "title", "status", "severity",
        "location", "observed_perimeter", "perimeter_updated_at",
        "reported_at", "updated_at", "contained_at",
        "is_archived", "archived_at", "metadata",
    }
    assert incident_cols == expected_incident_cols, f"Incident cols mismatch: {incident_cols ^ expected_incident_cols}"
    assert "incident_code" not in incident_cols
    assert "created_at" not in incident_cols
    assert "perimeter" not in incident_cols

    # 2. UploadedMedia
    media_cols = set(UploadedMedia.__table__.columns.keys())
    expected_media_cols = {
        "id", "incident_id", "storage_path", "media_format", "source_type",
        "file_size_bytes", "capture_location", "captured_at", "created_at",
    }
    assert media_cols == expected_media_cols, f"UploadedMedia cols mismatch: {media_cols ^ expected_media_cols}"
    for unapproved in ["original_filename", "media_type", "mime_type", "sha256_hash", "metadata", "updated_at"]:
        assert unapproved not in media_cols, f"Unapproved column {unapproved} found in uploaded_media"

    # 3. DetectionResult
    det_cols = set(DetectionResult.__table__.columns.keys())
    expected_det_cols = {
        "id", "media_id", "classification", "confidence", "bounding_boxes",
        "model_name", "model_version", "inference_latency_ms", "created_at",
    }
    assert det_cols == expected_det_cols, f"DetectionResult cols mismatch: {det_cols ^ expected_det_cols}"
    assert "model_name" in det_cols

    # 4. EnvironmentalObservation
    env_cols = set(EnvironmentalObservation.__table__.columns.keys())
    expected_env_cols = {
        "id", "incident_id", "recorded_at", "source", "temperature_celsius",
        "relative_humidity", "wind_speed_mps", "wind_direction_degrees",
        "precipitation_mm", "metrics_payload", "created_at",
        "location_type", "location_id", "requested_latitude", "requested_longitude",
        "resolved_latitude", "resolved_longitude", "location", "typology",
        "provider", "dataset_or_model", "valid_time_utc", "surface_pressure_hpa",
        "init_time_utc", "lead_time_hours", "algorithm_name", "algorithm_version",
        "source_fingerprint", "retrieved_at_utc",
    }
    assert env_cols == expected_env_cols, f"EnvironmentalObservation cols mismatch: {env_cols ^ expected_env_cols}"
    for unapproved in ["relative_humidity_percent", "wind_speed_kmh", "temperature_c"]:
        assert unapproved not in env_cols, f"Unapproved column {unapproved} found in environmental_observations"

    # 5. HazardPrediction
    pred_cols = set(HazardPrediction.__table__.columns.keys())
    expected_pred_cols = {
        "id", "incident_id", "primary_observation_id", "forecast_horizon_hours",
        "projected_area_hectares", "predicted_footprint", "risk_level",
        "model_name", "model_version", "input_snapshot", "created_at",
    }
    assert pred_cols == expected_pred_cols, f"HazardPrediction cols mismatch: {pred_cols ^ expected_pred_cols}"
    for unapproved in ["prediction_horizon_hours", "predicted_area_hectares", "spread_direction", "estimated_speed_kmh"]:
        assert unapproved not in pred_cols, f"Unapproved column {unapproved} found in hazard_predictions"


def test_column_nullability_and_immutability():
    """Verify specific nullability requirements: projected_area_hectares NOT NULL, etc."""
    assert HazardPrediction.__table__.columns["projected_area_hectares"].nullable is False
    assert HazardPrediction.__table__.columns["input_snapshot"].nullable is False
    assert HazardPrediction.__table__.columns["forecast_horizon_hours"].nullable is False
    assert HazardPrediction.__table__.columns["predicted_footprint"].nullable is False
    assert HazardPrediction.__table__.columns["risk_level"].nullable is False

    assert UploadedMedia.__table__.columns["incident_id"].nullable is True
    assert Incident.__table__.columns["observed_perimeter"].nullable is True
    assert Incident.__table__.columns["contained_at"].nullable is True
    assert Incident.__table__.columns["archived_at"].nullable is True


def test_metadata_declarative_base_preservation():
    """Verify that Incident.metadata still references DeclarativeBase.metadata, and incident_metadata maps to 'metadata'."""
    from app.models.base import Base
    assert Incident.metadata is Base.metadata
    assert "metadata" in Incident.__table__.columns
    assert Incident.__table__.columns["metadata"].name == "metadata"
    # Ensure instance maps to column
    assert hasattr(Incident, "incident_metadata")

