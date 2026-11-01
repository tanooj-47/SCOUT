"""
backend/tests/unit/intelligence/test_geospatial_correction.py
Unit tests for Milestone 11 Correction C (Geospatial Context & PostGIS Contract).
Verifies:
1. Global default_context_catalog starts clean and empty by default (zero calibration features auto-loaded).
2. Explicit loading of calibration fixture via load_calibration_dehradun_features(catalog).
3. PostGIS contract Case 1: DB query with features returns features.
4. PostGIS contract Case 2: DB query with 0 features returns 0 features (no fallback).
5. PostGIS contract Case 3: DB failure raises PostGISUnavailableError (HTTP 503, no fallback).
6. PostGIS contract Case 4: db=None queries in-memory catalog only.
"""

from unittest.mock import MagicMock
import pytest

from app.geospatial.context import (
    GeographicContextCatalog,
    default_context_catalog,
    load_calibration_dehradun_features,
)
from app.geospatial.exceptions import PostGISUnavailableError
from app.geospatial.schemas import (
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
    IncidentSpatialContext,
    SpatialRelationship,
)
from app.intelligence.adapters.geospatial_adapter import GeospatialModelAdapter
from app.services.geospatial_service import GeospatialService


def _make_assessment_resp(features, data_provider="postgis_spatial_db"):
    return GeospatialAssessmentResponse(
        assessment_id="test-assess-1",
        incident_context=IncidentSpatialContext(
            disaster_type="wildfire",
            latitude=30.3165,
            longitude=78.0322,
            utm_epsg=32644,
            search_radius_meters=5000.0,
        ),
        exposure_summary=ExposureSummary(
            total_features_found=len(features),
            category_counts={},
            highlighted_exposed_features=features,
        ),
        data_provider=data_provider,
        features=features,
        missing_data_indicators=[],
    )


def test_default_catalog_is_initially_empty():
    """Default context catalog must not auto-load synthetic calibration fixtures into operational memory."""
    # Global catalog must be empty by default
    assert len(default_context_catalog) == 0


def test_explicit_calibration_loading():
    """Calibration features can be explicitly loaded for testing/calibration, but are marked operational_use=False."""
    local_catalog = GeographicContextCatalog()
    loaded_count = load_calibration_dehradun_features(local_catalog)
    assert loaded_count >= 10
    assert len(local_catalog) >= 10

    # Verify features carry synthetic test fixture markers
    for feat in local_catalog._features:
        meta = feat.get("metadata", {})
        assert meta.get("synthetic_test_fixture") is True
        assert meta.get("operational_use") is False


def test_m10_postgis_contract_case1_live_query_with_features():
    """Case 1: Live DB query returning features returns those features with data_provider='postgis_spatial_db'."""
    mock_service = MagicMock(spec=GeospatialService)
    db_feature = GeographicFeatureItem(
        id="db-hosp-1",
        name="Dehradun Military Hospital",
        category=FeatureCategory.INFRASTRUCTURE,
        distance_meters=1200.0,
        relationship=SpatialRelationship.WITHIN_RADIUS,
        source_dataset="postgis_hospitals",
    )
    mock_service.analyze_exposure.return_value = _make_assessment_resp(
        features=[db_feature],
        data_provider="postgis_spatial_db",
    )

    adapter = GeospatialModelAdapter(service=mock_service)
    mock_db = MagicMock()

    evidence, summary = adapter.collect_evidence(
        latitude=30.3165,
        longitude=78.0322,
        radius_meters=5000.0,
        db=mock_db,
    )

    assert evidence.status == "valid"
    assert summary.total_features_evaluated == 1
    assert summary.hospitals_found == 1
    assert evidence.provenance["spatial_source"] == "postgis_spatial_db"


def test_m10_postgis_contract_case2_live_query_with_zero_features():
    """Case 2: Live DB query with 0 features returns empty result without falling back to in-memory catalog."""
    mock_service = MagicMock(spec=GeospatialService)
    mock_service.analyze_exposure.return_value = _make_assessment_resp(
        features=[],
        data_provider="postgis_spatial_db",
    )

    adapter = GeospatialModelAdapter(service=mock_service)
    mock_db = MagicMock()

    evidence, summary = adapter.collect_evidence(
        latitude=30.3165,
        longitude=78.0322,
        radius_meters=5000.0,
        db=mock_db,
    )

    assert summary.total_features_evaluated == 0
    assert summary.settlements_found == 0
    assert summary.hospitals_found == 0
    assert evidence.provenance["spatial_source"] == "postgis_spatial_db"


def test_m10_postgis_contract_case3_db_failure_raises_503():
    """Case 3: When DB session is supplied and fails, adapter MUST propagate PostGISUnavailableError (HTTP 503) without fallback."""
    mock_service = MagicMock(spec=GeospatialService)
    mock_service.analyze_exposure.side_effect = PostGISUnavailableError("PostGIS connection refused on port 5432")

    adapter = GeospatialModelAdapter(service=mock_service)
    mock_db = MagicMock()

    with pytest.raises(PostGISUnavailableError) as exc_info:
        adapter.collect_evidence(
            latitude=30.3165,
            longitude=78.0322,
            radius_meters=5000.0,
            db=mock_db,
        )

    assert "PostGIS connection refused" in str(exc_info.value)
    assert exc_info.value.status_code == 503


def test_m10_postgis_contract_case4_db_none_queries_local_catalog():
    """Case 4: When db=None, queries local in-memory catalog only."""
    local_catalog = GeographicContextCatalog()
    load_calibration_dehradun_features(local_catalog)

    service = GeospatialService(catalog=local_catalog)
    adapter = GeospatialModelAdapter(service=service)

    evidence, summary = adapter.collect_evidence(
        latitude=30.3165,
        longitude=78.0322,
        radius_meters=5000.0,
        db=None,
    )

    assert evidence.status == "valid"
    assert summary.total_features_evaluated > 0
    assert summary.settlements_found >= 1
    assert evidence.provenance["spatial_source"] == "local_vector_catalog"
