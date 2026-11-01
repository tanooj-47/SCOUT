"""
Unit tests for National Geographic Data Quality Correction & Validation.
Tests spatial clipping invariants, record accounting, WorldPop raster semantics,
healthcare coverage distributions, and ERA5 weather reference point terminology.
"""

import csv
import json
from pathlib import Path
import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROCESSED_GEO = PROJECT_ROOT / "data" / "processed" / "geospatial"
RAW_GEO = PROJECT_ROOT / "data" / "raw" / "geospatial"


class TestFireStationClippingQuality:
    """Verifies sovereign boundary clipping and accounting for fire stations."""

    def test_fire_station_clipped_file_exists(self):
        clipped_file = PROCESSED_GEO / "fire_stations" / "india_fire_stations_clipped.geojson"
        assert clipped_file.exists(), "Clipped fire stations GeoJSON must exist"
        assert clipped_file.stat().st_size > 0

    def test_fire_station_accounting_invariant(self):
        clipped_file = PROCESSED_GEO / "fire_stations" / "india_fire_stations_clipped.geojson"
        with open(clipped_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data.get("metadata", {})
        orig = meta.get("original_record_count")
        retained = meta.get("retained_record_count")
        excluded = meta.get("excluded_record_count")

        assert orig == 300, f"Expected 300 original records, got {orig}"
        assert retained == 146, f"Expected 146 retained records, got {retained}"
        assert excluded == 154, f"Expected 154 excluded records, got {excluded}"
        assert orig == retained + excluded, "Record accounting invariant violated"
        assert len(data.get("features", [])) == retained

    def test_fire_station_attributes_preserved(self):
        clipped_file = PROCESSED_GEO / "fire_stations" / "india_fire_stations_clipped.geojson"
        with open(clipped_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        assert len(features) > 0
        first = features[0]
        assert "geometry" in first
        assert first["geometry"]["type"] == "Point"
        assert len(first["geometry"]["coordinates"]) == 2
        props = first["properties"]
        assert "feature_id" in props
        assert "name" in props
        assert props["facility_type"] == "fire_station"
        assert "osm_id" in props


class TestFIRMSClippingQuality:
    """Verifies NASA FIRMS active fire hotspot clipping and accounting."""

    def test_firms_clipped_file_exists(self):
        clipped_file = PROCESSED_GEO / "fire_observations" / "india_firms_active_fires_clipped.geojson"
        assert clipped_file.exists(), "Clipped FIRMS GeoJSON must exist"

    def test_firms_accounting_invariant(self):
        clipped_file = PROCESSED_GEO / "fire_observations" / "india_firms_active_fires_clipped.geojson"
        with open(clipped_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data.get("metadata", {})
        acct = meta.get("record_accounting", {})
        total_sa = acct.get("total_south_asia_observations")
        bbox = acct.get("bounding_box_detections")
        inside = acct.get("inside_india_detections")
        outside_bbox = acct.get("outside_india_detections_in_bbox")

        assert total_sa == 11320, f"Expected 11,320 South Asia observations, got {total_sa}"
        assert bbox == 9308, f"Expected 9,308 bounding box detections, got {bbox}"
        assert inside == 5851, f"Expected 5,851 inside India detections, got {inside}"
        assert outside_bbox == 3457, f"Expected 3,457 outside India in bbox, got {outside_bbox}"
        assert bbox == inside + outside_bbox, "Bounding box accounting mismatch"
        assert len(data.get("features", [])) == inside

    def test_firms_coordinate_validity_and_ranges(self):
        clipped_file = PROCESSED_GEO / "fire_observations" / "india_firms_active_fires_clipped.geojson"
        with open(clipped_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for feat in data.get("features", []):
            coords = feat["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]
            assert 68.0 <= lon <= 97.5, f"Longitude out of India bounds: {lon}"
            assert 6.0 <= lat <= 37.5, f"Latitude out of India bounds: {lat}"
            props = feat["properties"]
            assert props["confidence"] in ["nominal", "high", "low"]
            assert props["satellite"] == "N"


class TestWorldPopSemanticValidation:
    """Verifies WorldPop raster semantics, units, dimensions, and metadata."""

    def test_worldpop_raster_properties(self):
        tif_path = RAW_GEO / "population" / "worldpop" / "ind_pd_2020_1km.tif"
        assert tif_path.exists(), "WorldPop GeoTIFF must exist"

        with Image.open(tif_path) as img:
            w, h = img.size
            assert (w, h) == (3508, 3451), f"Unexpected dimensions: {w}x{h}"
            assert img.mode == "F", f"Expected Float32 mode 'F', got {img.mode}"
            tag_v2 = img.tag_v2
            assert 33550 in tag_v2, "ModelPixelScaleTag must be present"
            assert 33922 in tag_v2, "ModelTiepointTag must be present"

    def test_worldpop_profile_semantics(self):
        prof_path = PROCESSED_GEO / "population" / "worldpop_population_profile.json"
        assert prof_path.exists(), "WorldPop profile JSON must exist"

        with open(prof_path, "r", encoding="utf-8") as f:
            prof = json.load(f)

        assert "people per square kilometer" in prof.get("unit", "").lower()
        assert prof.get("coordinate_reference_system") == "EPSG:4326"
        assert prof.get("nodata_value") == -99999.0


class TestHealthcareGeographicCoverage:
    """Verifies healthcare facility distribution across states and districts."""

    def test_healthcare_summary_files_exist(self):
        state_csv = PROCESSED_GEO / "healthcare" / "india_healthcare_state_summary.csv"
        dist_csv = PROCESSED_GEO / "healthcare" / "india_healthcare_district_summary.csv"
        assert state_csv.exists(), "State summary CSV must exist"
        assert dist_csv.exists(), "District summary CSV must exist"

    def test_state_summary_integrity(self):
        state_csv = PROCESSED_GEO / "healthcare" / "india_healthcare_state_summary.csv"
        with open(state_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 36, f"Expected 36 States/UTs, got {len(rows)}"
        total_matched = sum(int(r["total_facilities"]) for r in rows)
        assert total_matched == 121546, f"Expected 121,546 matched facilities, got {total_matched}"
        # Maharashtra should be the top mapped state
        assert rows[0]["state_name"] == "Maharashtra"
        assert int(rows[0]["total_facilities"]) > 10000

    def test_district_summary_integrity(self):
        dist_csv = PROCESSED_GEO / "healthcare" / "india_healthcare_district_summary.csv"
        with open(dist_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 641, f"Expected 641 districts, got {len(rows)}"
        zero_districts = [r["district_name"] for r in rows if int(r["total_facilities"]) == 0]
        assert len(zero_districts) == 3, f"Expected exactly 3 zero-facility districts, got {len(zero_districts)}"
        assert any("Diu" in d for d in zero_districts)
        assert any("Nicobar" in d for d in zero_districts)
        assert any("Lakshadweep" in d for d in zero_districts)


class TestEnvironmentalWeatherTerminology:
    """Verifies that weather sample records use accurate ERA5 reference point terminology."""

    def test_era5_weather_points_file_exists(self):
        weather_file = PROCESSED_GEO / "weather" / "india_era5_regional_weather_points.geojson"
        assert weather_file.exists(), "ERA5 weather points GeoJSON must exist"

    def test_era5_weather_terminology_enforced(self):
        weather_file = PROCESSED_GEO / "weather" / "india_era5_regional_weather_points.geojson"
        with open(weather_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        assert len(features) == 6, f"Expected 6 regional points, got {len(features)}"

        for feat in features:
            props = feat["properties"]
            name = props.get("name", "")
            assert "ERA5 Regional Reference Point" in name, f"Terminology violation in name: {name}"
            assert props.get("layer_name") == "era5_regional_weather_samples"
            assert "station" not in props.get("feature_id", "").lower() or "era5" in props.get("feature_id", "").lower()
            assert "reanalysis" in props.get("source_provider", "").lower()
