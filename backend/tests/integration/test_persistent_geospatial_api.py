"""
backend/tests/integration/test_persistent_geospatial_api.py
Integration tests for Persistent Geospatial REST API endpoints (Milestone 10).
Tests endpoint controllers, parameter validation, and database dependency handling.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid
import pytest
from geoalchemy2.elements import WKTElement

from app.api.v1.endpoints.geospatial import (
    analyze_exposure_endpoint,
    get_nearby_features_endpoint,
    list_features_endpoint,
    list_ingestion_runs_endpoint,
    list_layers_endpoint,
    list_sources_endpoint,
)
from app.geospatial.schemas import (
    ExposureAnalysisRequest,
    FeatureCategory,
    FeatureListResponse,
    LayerSummaryResponse,
)
from app.models.geospatial import (
    GeographicDataSource,
    GeographicFeature,
    GeographicIngestionRun,
)


@pytest.fixture
def mock_db_session():
    """Provides a mocked database session with realistic geospatial entities."""
    session = MagicMock()

    source_id = uuid.uuid4()
    source = GeographicDataSource(
        id=source_id,
        provider="openstreetmap",
        dataset_name="osm_critical_facilities",
        dataset_version="2026-Q3",
        source_url="https://download.geofabrik.de/asia/india.html",
        license_identifier="ODbL-1.0",
        attribution_text="Data © OpenStreetMap contributors, ODbL 1.0",
        source_crs="EPSG:4326",
        metadata_payload={"region": "Uttarakhand"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    run_id = uuid.uuid4()
    ingestion_run = GeographicIngestionRun(
        id=run_id,
        source_id=source_id,
        layer_name="critical_facilities",
        area_of_interest="in_dehradun_basin",
        source_file_name="calibration_dehradun_features.geojson",
        source_checksum="a" * 64,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_features=13,
        inserted_features=13,
        updated_features=0,
        skipped_features=0,
        rejected_features=0,
        status="completed",
        error_summary=None,
    )

    feat = GeographicFeature(
        id=uuid.uuid4(),
        source_id=source_id,
        source=source,
        ingestion_run_id=run_id,
        layer_name="critical_facilities",
        category="infrastructure",
        source_feature_id="osm_node_1001",
        name="Doon Hospital",
        properties={"amenity": "hospital", "emergency": "yes"},
        geometry=WKTElement("POINT(78.0340 30.3204)", srid=4326),
        geometry_type="Point",
        source_crs="EPSG:4326",
        hazard_relevance=["wildfire", "flood", "earthquake"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    return session, source, ingestion_run, feat


class TestPersistentGeospatialAPI:
    """Verifies persistent geospatial endpoints and response serialization."""

    def test_list_layers_endpoint(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.execute.return_value.all.return_value = [
            ("critical_facilities", 10),
            ("hydrology", 5),
        ]
        session.scalars.return_value.all.side_effect = [
            ["infrastructure"],
            ["water_body"],
        ]

        layers = list_layers_endpoint(db=session)
        assert len(layers) == 2
        assert isinstance(layers[0], LayerSummaryResponse)
        assert layers[0].layer_name == "critical_facilities"
        assert layers[0].feature_count == 10
        assert layers[0].categories == ["infrastructure"]

        assert layers[1].layer_name == "hydrology"
        assert layers[1].feature_count == 5

    def test_list_sources_endpoint(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.scalars.return_value.all.side_effect = None
        session.scalars.return_value.all.return_value = [source]

        sources = list_sources_endpoint(db=session)
        assert len(sources) == 1
        assert sources[0].provider == "openstreetmap"
        assert sources[0].license_identifier == "ODbL-1.0"
        assert "Data © OpenStreetMap" in sources[0].attribution_text

    def test_list_ingestion_runs_endpoint(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.scalars.return_value.all.side_effect = None
        session.scalars.return_value.all.return_value = [run]

        runs = list_ingestion_runs_endpoint(limit=50, db=session)
        assert len(runs) == 1
        assert runs[0].layer_name == "critical_facilities"
        assert runs[0].status == "completed"
        assert runs[0].total_features == 13

    def test_list_features_endpoint_bbox(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.scalars.return_value.all.side_effect = None
        session.scalars.return_value.all.return_value = [feat]
        session.scalar.return_value = 1

        response = list_features_endpoint(
            min_lon=78.0,
            min_lat=30.0,
            max_lon=78.2,
            max_lat=30.5,
            layer_name="critical_facilities",
            limit=25,
            offset=0,
            include_geometry=True,
            db=session,
        )
        assert isinstance(response, FeatureListResponse)
        assert response.total == 1
        assert response.limit == 25
        assert len(response.features) == 1
        assert response.features[0].name == "Doon Hospital"
        assert response.features[0].category == FeatureCategory.INFRASTRUCTURE
        assert response.features[0].geometry is not None

    def test_list_features_endpoint_radius(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.execute.return_value.all.return_value = [(feat, 420.5)]
        session.scalar.return_value = 1

        response = list_features_endpoint(
            latitude=30.3204,
            longitude=78.0340,
            radius_meters=5000.0,
            hazard="wildfire",
            limit=10,
            offset=0,
            include_geometry=False,
            db=session,
        )
        assert response.total == 1
        assert len(response.features) == 1
        assert response.features[0].distance_meters == 420.5
        assert response.features[0].relationship.value == "within_radius"

    def test_get_nearby_features_endpoint(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.execute.return_value.all.return_value = [(feat, 150.0)]

        features = get_nearby_features_endpoint(
            latitude=30.3204,
            longitude=78.0340,
            radius_meters=3000.0,
            categories=None,
            limit=50,
            include_geometry=False,
            db=session,
        )
        assert len(features) == 1
        assert features[0].name == "Doon Hospital"
        assert features[0].distance_meters == 150.0

    def test_analyze_exposure_endpoint_with_persistent_db(self, mock_db_session):
        session, source, run, feat = mock_db_session
        session.execute.return_value.all.side_effect = [
            [(feat, 250.0)],          # persistent radius query
            [("critical_facilities", 1)],  # list_layers
        ]
        session.scalars.return_value.all.return_value = ["infrastructure"]

        req = ExposureAnalysisRequest(
            latitude=30.3204,
            longitude=78.0340,
            search_radius_meters=5000.0,
            disaster_type="wildfire",
            include_geometry=False,
        )

        assessment = analyze_exposure_endpoint(request=req, db=session)
        assert assessment.data_provider == "postgis_spatial_db"
        assert assessment.exposure_summary.total_features_found == 1
        assert assessment.exposure_summary.closest_feature_name == "Doon Hospital"
        assert len(assessment.features) == 1
        assert any("critical infrastructure" in f for f in assessment.contributing_factors)
        assert len(assessment.missing_data_indicators) >= 4
