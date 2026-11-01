"""
backend/tests/unit/geospatial/test_context_and_exposure.py
Unit tests for GeographicContextCatalog and ExposureEngine.
"""

import pytest
import shapely.geometry

from app.geospatial.context import GeographicContextCatalog
from app.geospatial.exposure import ExposureEngine
from app.geospatial.schemas import (
    FeatureCategory,
    SpatialRelationship,
)


@pytest.fixture
def populated_catalog() -> GeographicContextCatalog:
    """Fixture providing a controlled catalog populated with known features."""
    cat = GeographicContextCatalog()

    # 1. Settlement in Mill Valley, CA (37.9060, -122.5450)
    cat.add_feature(
        feature_id="feat-settle-01",
        name="Mill Valley Residential District",
        category=FeatureCategory.SETTLEMENT,
        geometry=shapely.geometry.Point(-122.5450, 37.9060),
        source_dataset="osm_settlements_v1",
        metadata={"population_estimate": 14000},
    )

    # 2. Forest Polygon in Muir Woods (near 37.8970, -122.5811)
    cat.add_feature(
        feature_id="feat-veg-01",
        name="Muir Woods Redwood Canopy",
        category=FeatureCategory.VEGETATION,
        geometry=shapely.geometry.Polygon([
            (-122.59, 37.89),
            (-122.57, 37.89),
            (-122.57, 37.91),
            (-122.59, 37.91),
            (-122.59, 37.89),
        ]),
        source_dataset="usfs_timber_v2",
        metadata={"fuel_model": "Timber Litter"},
    )

    # 3. Highway Road LineString (CA-1)
    cat.add_feature(
        feature_id="feat-road-01",
        name="State Route 1 Corridor",
        category=FeatureCategory.ROAD,
        geometry=shapely.geometry.LineString([
            (-122.55, 37.88),
            (-122.56, 37.90),
            (-122.58, 37.92),
        ]),
        source_dataset="caltrans_highway_gis",
        metadata={"lanes": 2, "access_type": "primary"},
    )

    # 4. Critical Infrastructure: Electrical Substation
    cat.add_feature(
        feature_id="feat-infra-01",
        name="Marin 115kV Power Substation",
        category=FeatureCategory.INFRASTRUCTURE,
        geometry=shapely.geometry.Point(-122.5350, 37.9120),
        source_dataset="california_energy_infra",
        metadata={"voltage_kv": 115},
    )

    return cat


class TestGeographicContextCatalog:
    """Tests for spatial feature catalog management and filtering."""

    def test_layer_availability(self, populated_catalog):
        assert populated_catalog.is_layer_available(FeatureCategory.SETTLEMENT) is True
        assert populated_catalog.is_layer_available(FeatureCategory.VEGETATION) is True
        assert populated_catalog.is_layer_available(FeatureCategory.ROAD) is True
        assert populated_catalog.is_layer_available(FeatureCategory.INFRASTRUCTURE) is True
        assert populated_catalog.is_layer_available(FeatureCategory.WATER_BODY) is False

    def test_missing_layers_identification(self, populated_catalog):
        missing = populated_catalog.get_missing_layers()
        assert "water_body_layer_unavailable" in missing
        assert "administrative_layer_unavailable" in missing
        assert "settlement_layer_unavailable" not in missing

    def test_query_nearby_features_within_radius(self, populated_catalog):
        # Origin at Mill Valley center (37.9060, -122.5450)
        # Search radius 2,000 meters
        results = populated_catalog.query_nearby_features(
            latitude=37.9060,
            longitude=-122.5450,
            radius_meters=2000.0,
        )

        assert len(results) >= 2
        # First result should be the settlement point itself (distance ~0m)
        assert results[0].id == "feat-settle-01"
        assert results[0].distance_meters < 10.0
        assert results[0].relationship == SpatialRelationship.INTERSECTS

        # Verify sorted ascending by distance
        distances = [f.distance_meters for f in results]
        assert distances == sorted(distances)

    def test_category_filtering(self, populated_catalog):
        results = populated_catalog.query_nearby_features(
            latitude=37.9060,
            longitude=-122.5450,
            radius_meters=10000.0,
            categories=[FeatureCategory.INFRASTRUCTURE],
        )

        assert len(results) == 1
        assert results[0].id == "feat-infra-01"
        assert results[0].category == FeatureCategory.INFRASTRUCTURE

    def test_catalog_add_new_feature_and_len(self):
        cat = GeographicContextCatalog()
        assert len(cat) == 0

        added = cat.add_feature(
            feature_id="feat-test-1",
            name="Test Point",
            category=FeatureCategory.SETTLEMENT,
            geometry=shapely.geometry.Point(-122.0, 37.0),
            source_dataset="test_source",
        )
        assert added is True
        assert len(cat) == 1
        feat = cat.get_feature("feat-test-1")
        assert feat is not None
        assert feat["name"] == "Test Point"
        assert feat["category"] == FeatureCategory.SETTLEMENT

    def test_catalog_duplicate_feature_overwrite_default(self):
        cat = GeographicContextCatalog()
        cat.add_feature(
            feature_id="feat-dup-1",
            name="Initial Name",
            category=FeatureCategory.SETTLEMENT,
            geometry=shapely.geometry.Point(-122.0, 37.0),
            source_dataset="v1",
        )
        assert len(cat) == 1
        assert cat.get_feature("feat-dup-1")["name"] == "Initial Name"

        # Overwrite with default overwrite=True
        added = cat.add_feature(
            feature_id="feat-dup-1",
            name="Updated Name",
            category=FeatureCategory.SETTLEMENT,
            geometry=shapely.geometry.Point(-122.1, 37.1),
            source_dataset="v2",
        )
        assert added is True
        assert len(cat) == 1
        assert cat.get_feature("feat-dup-1")["name"] == "Updated Name"
        assert cat.get_feature("feat-dup-1")["source_dataset"] == "v2"

    def test_catalog_duplicate_feature_no_overwrite(self):
        cat = GeographicContextCatalog()
        cat.add_feature(
            feature_id="feat-no-overwrite-1",
            name="Original Entry",
            category=FeatureCategory.INFRASTRUCTURE,
            geometry=shapely.geometry.Point(-122.0, 37.0),
            source_dataset="original_ds",
        )
        assert len(cat) == 1

        # Reject overwrite
        added = cat.add_feature(
            feature_id="feat-no-overwrite-1",
            name="Attempted Modification",
            category=FeatureCategory.ROAD,
            geometry=shapely.geometry.Point(-122.5, 37.5),
            source_dataset="new_ds",
            overwrite=False,
        )
        assert added is False
        assert len(cat) == 1
        feat = cat.get_feature("feat-no-overwrite-1")
        assert feat["name"] == "Original Entry"
        assert feat["category"] == FeatureCategory.INFRASTRUCTURE

    def test_catalog_invalid_feature_id(self):
        cat = GeographicContextCatalog()
        with pytest.raises(ValueError, match="feature_id must be a non-empty string"):
            cat.add_feature(
                feature_id="",
                name="Invalid ID",
                category=FeatureCategory.ROAD,
                geometry=shapely.geometry.Point(0, 0),
                source_dataset="test",
            )
        with pytest.raises(ValueError, match="feature_id must be a non-empty string"):
            cat.add_feature(
                feature_id=None,  # type: ignore
                name="Invalid ID None",
                category=FeatureCategory.ROAD,
                geometry=shapely.geometry.Point(0, 0),
                source_dataset="test",
            )

    def test_catalog_category_update_resynchronizes_layers(self):
        cat = GeographicContextCatalog()
        cat.add_feature(
            feature_id="feat-morph-1",
            name="Morphing Asset",
            category=FeatureCategory.ROAD,
            geometry=shapely.geometry.Point(-122.0, 37.0),
            source_dataset="caltrans",
        )
        assert cat.is_layer_available(FeatureCategory.ROAD) is True
        assert cat.is_layer_available(FeatureCategory.SETTLEMENT) is False

        # Morph category to SETTLEMENT
        cat.add_feature(
            feature_id="feat-morph-1",
            name="Morphed Asset",
            category=FeatureCategory.SETTLEMENT,
            geometry=shapely.geometry.Point(-122.0, 37.0),
            source_dataset="census",
            overwrite=True,
        )
        assert len(cat) == 1
        assert cat.is_layer_available(FeatureCategory.ROAD) is False
        assert cat.is_layer_available(FeatureCategory.SETTLEMENT) is True

    def test_catalog_remove_and_clear(self):
        cat = GeographicContextCatalog()
        cat.add_feature(
            feature_id="feat-temp-1",
            name="Temporary Road",
            category=FeatureCategory.ROAD,
            geometry=shapely.geometry.Point(-122.0, 37.0),
            source_dataset="test",
        )
        cat.add_feature(
            feature_id="feat-temp-2",
            name="Temporary Settle",
            category=FeatureCategory.SETTLEMENT,
            geometry=shapely.geometry.Point(-122.1, 37.1),
            source_dataset="test",
        )
        assert len(cat) == 2
        assert cat.is_layer_available(FeatureCategory.ROAD) is True

        # Remove nonexistent
        assert cat.remove_feature("nonexistent-id") is False
        assert len(cat) == 2

        # Remove feat-temp-1
        assert cat.remove_feature("feat-temp-1") is True
        assert len(cat) == 1
        assert cat.get_feature("feat-temp-1") is None
        assert cat.is_layer_available(FeatureCategory.ROAD) is False
        assert cat.is_layer_available(FeatureCategory.SETTLEMENT) is True

        # Clear
        cat.clear()
        assert len(cat) == 0
        assert cat.is_layer_available(FeatureCategory.SETTLEMENT) is False
        assert len(cat.get_missing_layers()) == len(FeatureCategory)


class TestExposureEngine:
    """Tests for exposure metrics aggregation and highlighting."""

    def test_exposure_analysis_aggregation(self, populated_catalog):
        engine = ExposureEngine(populated_catalog)

        summary = engine.analyze_exposure(
            latitude=37.9060,
            longitude=-122.5450,
            search_radius_meters=5000.0,
        )

        assert summary.total_features_found >= 3
        assert summary.category_counts.get("settlement") == 1
        assert summary.category_counts.get("infrastructure") == 1
        assert summary.closest_feature_distance_meters is not None
        assert summary.closest_feature_distance_meters < 10.0
        assert summary.closest_feature_name == "Mill Valley Residential District"
        assert len(summary.highlighted_exposed_features) >= 1

    def test_exposure_engine_configurable_priority_threshold(self):
        cat = GeographicContextCatalog()
        # Origin: (37.9060, -122.5450)
        # 0.0135 degrees latitude is ~1,498 - 1,500 meters north
        cat.add_feature(
            feature_id="feat-mid-distance",
            name="Intermediate Station",
            category=FeatureCategory.INFRASTRUCTURE,
            geometry=shapely.geometry.Point(-122.5450, 37.9195),
            source_dataset="test_grid",
        )

        # Default engine (1,000.0m threshold)
        engine_default = ExposureEngine(cat)
        res_default = engine_default.analyze_exposure(
            latitude=37.9060,
            longitude=-122.5450,
            search_radius_meters=3000.0,
        )
        assert res_default.total_features_found == 1
        assert 1400.0 < res_default.closest_feature_distance_meters < 1600.0
        # Should NOT be highlighted under default 1000m threshold
        assert len(res_default.highlighted_exposed_features) == 0

        # Engine initialized with 2,000.0m threshold
        engine_wide = ExposureEngine(cat, priority_threshold_meters=2000.0)
        res_wide = engine_wide.analyze_exposure(
            latitude=37.9060,
            longitude=-122.5450,
            search_radius_meters=3000.0,
        )
        assert res_wide.total_features_found == 1
        # Should BE highlighted under 2000m threshold
        assert len(res_wide.highlighted_exposed_features) == 1
        assert res_wide.highlighted_exposed_features[0].id == "feat-mid-distance"

        # Engine with call-level override
        res_call_override = engine_default.analyze_exposure(
            latitude=37.9060,
            longitude=-122.5450,
            search_radius_meters=3000.0,
            priority_threshold_meters=2000.0,
        )
        assert len(res_call_override.highlighted_exposed_features) == 1
        assert res_call_override.highlighted_exposed_features[0].id == "feat-mid-distance"

    def test_exposure_engine_invalid_thresholds(self, populated_catalog):
        with pytest.raises(ValueError, match="priority_threshold_meters must be a positive finite number"):
            ExposureEngine(populated_catalog, priority_threshold_meters=0.0)

        with pytest.raises(ValueError, match="priority_threshold_meters must be a positive finite number"):
            ExposureEngine(populated_catalog, priority_threshold_meters=-500.0)

        with pytest.raises(ValueError, match="priority_threshold_meters must be a positive finite number"):
            ExposureEngine(populated_catalog, priority_threshold_meters=float("nan"))

        engine = ExposureEngine(populated_catalog)
        with pytest.raises(ValueError, match="priority_threshold_meters must be a positive finite number"):
            engine.analyze_exposure(
                latitude=37.9060,
                longitude=-122.5450,
                search_radius_meters=2000.0,
                priority_threshold_meters=-10.0,
            )
