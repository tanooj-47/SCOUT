"""
backend/app/geospatial/acquisition/normalizer_pipeline.py
Production data processing and normalization pipeline for national Indian geospatial datasets.
Converts raw acquired datasets (OpenStreetMap, DataMeet, Natural Earth, NASA FIRMS, WorldPop, Copernicus)
into standard M10-compliant GeoJSON layers and raster profiles.
"""

import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

import shapefile
import shapely.geometry
import shapely.validation
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scout.normalizer_pipeline")

# Canonical India WGS84 bounding box
INDIA_BBOX = (68.1, 6.5, 97.4, 35.5)  # min_lon, min_lat, max_lon, max_lat


def compute_checksums(filepath: Path) -> Tuple[int, str, str]:
    """Computes file size, SHA-256 and MD5 hashes."""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = filepath.stat().st_size
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return size, sha256.hexdigest(), md5.hexdigest()


def validate_geom(geom_dict: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], List[float]]]:
    """Validates geometry with Shapely, repairs if needed, returns (geom_dict, bbox)."""
    try:
        geom = shapely.geometry.shape(geom_dict)
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = shapely.validation.make_valid(geom)
            if geom.is_empty or not geom.is_valid:
                return None
        minx, miny, maxx, maxy = geom.bounds
        # Validate WGS84 bounds
        if minx < -180.0 or maxx > 180.0 or miny < -90.0 or maxy > 90.0:
            return None
        return shapely.geometry.mapping(geom), [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)]
    except Exception as e:
        logger.debug(f"Geometry validation failed: {e}")
        return None


# ==============================================================================
# Layer 1: Administrative Boundaries (National, States/UTs, Districts)
# ==============================================================================

def process_administrative_boundaries(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing Administrative Boundaries ---")
    out_dir = processed_dir / "administrative_boundaries"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    # 1. National Boundary (Survey of India official)
    soi_raw = raw_dir / "boundaries" / "survey_of_india" / "india-soi.geojson"
    if soi_raw.exists():
        with open(soi_raw, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        norm_features = []
        for i, ft in enumerate(features):
            val = validate_geom(ft.get("geometry", {}))
            if not val:
                continue
            geom_m, bbox = val
            norm_features.append({
                "type": "Feature",
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"in.gov.soi.national.{i}")),
                "geometry": geom_m,
                "properties": {
                    "feature_id": f"soi_national_boundary_{i+1}",
                    "name": "Republic of India (National Boundary)",
                    "category": "administrative",
                    "admin_level": 2,
                    "jurisdiction": "National",
                    "hazard_relevance": ["wildfire", "flood", "earthquake"],
                    "source_provider": "Survey of India",
                    "layer_name": "administrative_boundary_national",
                    "bounding_box": bbox,
                }
            })
        out_path = out_dir / "india_national_boundary.geojson"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)
        size, sha, md5 = compute_checksums(out_path)
        summaries.append({
            "layer": "administrative_boundary_national",
            "file": str(out_path.name),
            "feature_count": len(norm_features),
            "size_bytes": size,
            "sha256": sha,
            "md5": md5
        })
        logger.info(f"Processed National Boundary: {len(norm_features)} features ({size} bytes)")

    # 2. States & Union Territories (All 36 States/UTs)
    states_raw = raw_dir / "boundaries" / "osm" / "india-states.geojson"
    if states_raw.exists():
        with open(states_raw, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        norm_features = []
        for ft in features:
            val = validate_geom(ft.get("geometry", {}))
            if not val:
                continue
            geom_m, bbox = val
            props = ft.get("properties", {})
            name = props.get("NAME_1") or props.get("ST_NM") or props.get("name") or "Unknown State"
            state_code = props.get("ID_1") or props.get("ST_CEN_CD") or name
            norm_features.append({
                "type": "Feature",
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"in.gov.state.{state_code}")),
                "geometry": geom_m,
                "properties": {
                    "feature_id": f"state_{state_code}",
                    "name": name,
                    "category": "administrative",
                    "admin_level": 4,
                    "jurisdiction": "State/UT",
                    "hazard_relevance": ["wildfire", "flood", "earthquake"],
                    "source_provider": "DataMeet / OpenStreetMap / Census",
                    "layer_name": "administrative_boundary_states",
                    "bounding_box": bbox,
                    "census_code": props.get("ST_CEN_CD"),
                }
            })
        out_path = out_dir / "india_states_ut.geojson"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)
        size, sha, md5 = compute_checksums(out_path)
        summaries.append({
            "layer": "administrative_boundary_states",
            "file": str(out_path.name),
            "feature_count": len(norm_features),
            "size_bytes": size,
            "sha256": sha,
            "md5": md5
        })
        logger.info(f"Processed States & UTs: {len(norm_features)} features ({size} bytes)")

    # 3. Districts (Census 2011 - 641 Districts)
    dist_raw = raw_dir / "boundaries" / "osm" / "india-districts.geojson"
    if dist_raw.exists():
        with open(dist_raw, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        norm_features = []
        for ft in features:
            val = validate_geom(ft.get("geometry", {}))
            if not val:
                continue
            geom_m, bbox = val
            props = ft.get("properties", {})
            dist_name = props.get("DISTRICT") or props.get("name") or "Unknown District"
            st_name = props.get("ST_NM") or "Unknown State"
            c_code = props.get("censuscode") or props.get("DT_CEN_CD") or dist_name
            norm_features.append({
                "type": "Feature",
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"in.gov.district.{c_code}")),
                "geometry": geom_m,
                "properties": {
                    "feature_id": f"district_{c_code}",
                    "name": f"{dist_name} District",
                    "district_name": dist_name,
                    "state_name": st_name,
                    "category": "administrative",
                    "admin_level": 5,
                    "jurisdiction": "District",
                    "hazard_relevance": ["wildfire", "flood", "earthquake"],
                    "source_provider": "Office of the Registrar General & Census Commissioner, India",
                    "layer_name": "administrative_boundary_districts",
                    "bounding_box": bbox,
                    "census_code": props.get("censuscode"),
                    "state_census_code": props.get("ST_CEN_CD"),
                }
            })
        out_path = out_dir / "india_districts.geojson"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)
        size, sha, md5 = compute_checksums(out_path)
        summaries.append({
            "layer": "administrative_boundary_districts",
            "file": str(out_path.name),
            "feature_count": len(norm_features),
            "size_bytes": size,
            "sha256": sha,
            "md5": md5
        })
        logger.info(f"Processed Districts: {len(norm_features)} features ({size} bytes)")

    return summaries


# ==============================================================================
# Layer 2: Hospitals & Healthcare Facilities
# ==============================================================================

def process_hospitals(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing Healthcare Facilities ---")
    out_dir = processed_dir / "hospitals"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    hf_raw = raw_dir / "osm" / "health_facilities.geojson"
    if not hf_raw.exists():
        logger.warning(f"Raw health facilities file not found at {hf_raw}")
        return summaries

    with open(hf_raw, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    raw_features = data.get("features", [])
    norm_features = []
    # Filter for major hospitals, clinics, and trauma facilities with coordinates
    for ft in raw_features:
        geom = ft.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        if not (INDIA_BBOX[0] <= lon <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lat <= INDIA_BBOX[3]):
            continue

        props = ft.get("properties", {})
        amenity = props.get("amenity") or props.get("healthcare") or "hospital"
        if amenity not in ("hospital", "clinic", "health_post", "doctors", "pharmacy", "centre"):
            continue

        name = props.get("name") or props.get("name:en") or f"Health Facility ({amenity.title()})"
        osm_id = props.get("osm_id") or ft.get("id") or str(uuid.uuid4())

        norm_features.append({
            "type": "Feature",
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"osm.health.{osm_id}")),
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 6), round(lat, 6)]
            },
            "properties": {
                "feature_id": f"hospital_{osm_id}",
                "name": name,
                "category": "infrastructure",
                "facility_type": amenity,
                "hazard_relevance": ["wildfire", "flood", "earthquake"],
                "source_provider": "Humanitarian OpenStreetMap Team (HOT) / HDX",
                "layer_name": "healthcare_facilities",
                "bounding_box": [round(lon, 6), round(lat, 6), round(lon, 6), round(lat, 6)],
                "beds": props.get("beds"),
                "emergency": props.get("emergency"),
                "operator": props.get("operator") or props.get("operator:type"),
                "osm_id": str(osm_id),
            }
        })

    out_path = out_dir / "india_hospitals_healthcare.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "healthcare_facilities",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed Healthcare Facilities: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 3: Fire Stations & Emergency Response
# ==============================================================================

def process_fire_stations(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing Fire & Emergency Facilities ---")
    out_dir = processed_dir / "fire_stations"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    fs_raw = raw_dir / "osm" / "fire_stations_resolved.json"
    if not fs_raw.exists():
        fs_raw = raw_dir / "osm" / "fire_stations_raw.json"
    if not fs_raw.exists():
        logger.warning(f"Raw fire stations file not found at {fs_raw}")
        return summaries

    with open(fs_raw, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])
    norm_features = []
    for el in elements:
        lat = el.get("lat") or (el.get("center", {}).get("lat") if "center" in el else None)
        lon = el.get("lon") or (el.get("center", {}).get("lon") if "center" in el else None)
        if lat is None or lon is None:
            continue
        if not (INDIA_BBOX[0] <= lon <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lat <= INDIA_BBOX[3]):
            continue

        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or "Fire & Rescue Station"
        osm_id = el.get("id")

        norm_features.append({
            "type": "Feature",
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"osm.fire_station.{osm_id}")),
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 6), round(lat, 6)]
            },
            "properties": {
                "feature_id": f"fire_station_{osm_id}",
                "name": name,
                "category": "infrastructure",
                "facility_type": "fire_station",
                "hazard_relevance": ["wildfire", "flood", "earthquake"],
                "source_provider": "OpenStreetMap Contributors",
                "layer_name": "fire_stations",
                "bounding_box": [round(lon, 6), round(lat, 6), round(lon, 6), round(lat, 6)],
                "operator": tags.get("operator"),
                "phone": tags.get("phone") or tags.get("emergency:phone"),
                "osm_id": str(osm_id),
            }
        })

    out_path = out_dir / "india_fire_emergency_facilities.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "fire_stations",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed Fire Stations: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 4: Rivers & Hydrological Networks
# ==============================================================================

def process_rivers(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing Major Rivers ---")
    out_dir = processed_dir / "rivers"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    rivers_raw = raw_dir / "natural_earth" / "ne_10m_rivers_lake_centerlines.geojson"
    if not rivers_raw.exists():
        logger.warning(f"Raw rivers file not found at {rivers_raw}")
        return summaries

    with open(rivers_raw, "r", encoding="utf-8") as f:
        data = json.load(f)

    norm_features = []
    for i, ft in enumerate(data.get("features", [])):
        val = validate_geom(ft.get("geometry", {}))
        if not val:
            continue
        geom_m, bbox = val
        # Check if intersects India
        if bbox[2] < INDIA_BBOX[0] or bbox[0] > INDIA_BBOX[2] or bbox[3] < INDIA_BBOX[1] or bbox[1] > INDIA_BBOX[3]:
            continue

        props = ft.get("properties", {})
        name = props.get("name") or props.get("name_en") or props.get("NAME") or "River Channel"
        river_id = props.get("ne_id") or i

        norm_features.append({
            "type": "Feature",
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ne.river.{river_id}")),
            "geometry": geom_m,
            "properties": {
                "feature_id": f"river_{river_id}",
                "name": name,
                "category": "water_body",
                "hazard_relevance": ["flood"],
                "source_provider": "Natural Earth 1:10m Hydrology",
                "layer_name": "major_rivers",
                "bounding_box": bbox,
                "scalerank": props.get("scalerank"),
                "featurecla": props.get("featurecla"),
            }
        })

    out_path = out_dir / "india_major_rivers.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "major_rivers",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed Major Rivers: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 5: Settlements & Populated Places
# ==============================================================================

def process_settlements(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing Populated Places ---")
    out_dir = processed_dir / "settlements"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    places_raw = raw_dir / "natural_earth" / "ne_10m_populated_places.geojson"
    if not places_raw.exists():
        logger.warning(f"Raw populated places file not found at {places_raw}")
        return summaries

    with open(places_raw, "r", encoding="utf-8") as f:
        data = json.load(f)

    norm_features = []
    for i, ft in enumerate(data.get("features", [])):
        val = validate_geom(ft.get("geometry", {}))
        if not val:
            continue
        geom_m, bbox = val
        props = ft.get("properties", {})
        lon, lat = bbox[0], bbox[1]
        sov = str(props.get("SOV0NAME", "")).lower()
        adm0 = str(props.get("ADM0NAME", "")).lower()

        if "india" not in sov and "india" not in adm0:
            if not (INDIA_BBOX[0] <= lon <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lat <= INDIA_BBOX[3]):
                continue

        name = props.get("NAME") or props.get("NAME_EN") or "Settlement"
        place_id = props.get("NE_ID") or i

        norm_features.append({
            "type": "Feature",
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ne.place.{place_id}")),
            "geometry": geom_m,
            "properties": {
                "feature_id": f"settlement_{place_id}",
                "name": name,
                "category": "settlement",
                "hazard_relevance": ["wildfire", "flood", "earthquake"],
                "source_provider": "Natural Earth 1:10m Populated Places",
                "layer_name": "populated_places",
                "bounding_box": bbox,
                "population": props.get("POP_MAX"),
                "population_min": props.get("POP_MIN"),
                "adm0name": props.get("ADM0NAME"),
                "adm1name": props.get("ADM1NAME"),
                "featurecla": props.get("FEATURECLA"),
            }
        })

    out_path = out_dir / "india_populated_places.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "populated_places",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed Populated Places: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 6: Roads & Transport Networks
# ==============================================================================

def process_roads(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing Roads & Transport Network ---")
    out_dir = processed_dir / "roads"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    shp_path = raw_dir / "natural_earth" / "roads" / "ne_10m_roads.shp"
    if not shp_path.exists():
        logger.warning(f"Raw roads shapefile not found at {shp_path}")
        return summaries

    sf = shapefile.Reader(str(shp_path))
    norm_features = []
    for i, sr in enumerate(sf.shapeRecords()):
        bbox = sr.shape.bbox
        if bbox[2] < INDIA_BBOX[0] or bbox[0] > INDIA_BBOX[2] or bbox[3] < INDIA_BBOX[1] or bbox[1] > INDIA_BBOX[3]:
            continue

        raw_geom = sr.shape.__geo_interface__
        val = validate_geom(raw_geom)
        if not val:
            continue
        geom_m, g_bbox = val
        rec = sr.record.as_dict()
        rtype = rec.get("type") or "Highway"
        name = rec.get("name") or f"Arterial Transport Corridor ({rtype})"

        norm_features.append({
            "type": "Feature",
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ne.road.{i}")),
            "geometry": geom_m,
            "properties": {
                "feature_id": f"road_{i+1}",
                "name": name,
                "category": "road",
                "road_type": rtype,
                "hazard_relevance": ["wildfire", "flood", "earthquake"],
                "source_provider": "Natural Earth 1:10m Roads Network",
                "layer_name": "transport_network",
                "bounding_box": g_bbox,
                "scalerank": rec.get("scalerank"),
                "expressway": rec.get("expressway"),
            }
        })

    out_path = out_dir / "india_transport_network.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "transport_network",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed Transport Network: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 7: Active Fire Observations (NASA FIRMS VIIRS)
# ==============================================================================

def process_fire_observations(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing NASA FIRMS Active Fire Observations ---")
    out_dir = processed_dir / "fire_observations"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    csv_path = raw_dir / "observations" / "nasa_firms" / "SUOMI_VIIRS_C2_South_Asia_7d.csv"
    if not csv_path.exists():
        logger.warning(f"Raw FIRMS CSV not found at {csv_path}")
        return summaries

    norm_features = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (ValueError, KeyError):
                continue

            if not (INDIA_BBOX[0] <= lon <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lat <= INDIA_BBOX[3]):
                continue

            frp = float(row.get("frp", 0.0))
            brightness = float(row.get("bright_ti4", 0.0))
            acq_date = row.get("acq_date", "")
            acq_time = row.get("acq_time", "")
            confidence = row.get("confidence", "nominal")

            norm_features.append({
                "type": "Feature",
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"nasa.firms.viirs.{acq_date}.{acq_time}.{lat}.{lon}")),
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 6), round(lat, 6)]
                },
                "properties": {
                    "feature_id": f"firms_viirs_{i+1}",
                    "name": f"Active Fire Thermal Anomaly ({frp:.1f} MW)",
                    "category": "other",
                    "hazard_relevance": ["wildfire"],
                    "source_provider": "NASA FIRMS (Suomi-NPP VIIRS C2 NRT)",
                    "layer_name": "active_fire_observations",
                    "bounding_box": [round(lon, 6), round(lat, 6), round(lon, 6), round(lat, 6)],
                    "acquisition_date": acq_date,
                    "acquisition_time_utc": acq_time,
                    "fire_radiative_power_mw": frp,
                    "brightness_temp_kelvin": brightness,
                    "confidence": confidence,
                    "satellite": row.get("satellite", "N"),
                    "day_night": row.get("daynight", "D"),
                }
            })

    out_path = out_dir / "india_firms_active_fires_7d.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "active_fire_observations",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed Active Fire Observations: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 8: Agro-Climatic Weather Reference Grid
# ==============================================================================

def process_weather_grid(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Normalizing ECMWF ERA5 Regional Weather Reference Points ---")
    out_dir = processed_dir / "weather"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    weather_raw = raw_dir / "weather" / "open_meteo_india_climatic_grid.json"
    if not weather_raw.exists():
        logger.warning(f"Raw weather grid not found at {weather_raw}")
        return summaries

    with open(weather_raw, "r", encoding="utf-8") as f:
        data = json.load(f)

    norm_features = []
    zones_dict = data.get("zones", {})
    if isinstance(zones_dict, dict):
        zone_items = zones_dict.items()
    elif isinstance(zones_dict, list):
        zone_items = [(z.get("zone_name", f"zone_{i}"), z) for i, z in enumerate(zones_dict)]
    else:
        zone_items = []

    for zname, zone in zone_items:
        lat = zone.get("latitude")
        lon = zone.get("longitude")
        hourly = zone.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        precips = hourly.get("precipitation", [])

        norm_features.append({
            "type": "Feature",
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"meteo.zone.{zname}")),
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 4), round(lat, 4)]
            },
            "properties": {
                "feature_id": f"era5_point_{zname.lower().replace(' ', '_')}",
                "name": f"ERA5 Regional Reference Point ({zname.replace('_', ' ')})",
                "zone_name": zname,
                "category": "other",
                "hazard_relevance": ["wildfire", "flood"],
                "source_provider": "ECMWF ERA5 / Open-Meteo Historical Reanalysis",
                "layer_name": "era5_regional_weather_samples",
                "data_type": "atmospheric_reanalysis_model_grid_sample",
                "notes": "Regional representative model grid point from ECMWF ERA5 reanalysis; not a physical ground weather station.",
                "bounding_box": [round(lon, 4), round(lat, 4), round(lon, 4), round(lat, 4)],
                "elevation_m": zone.get("elevation"),
                "hourly_records_count": len(times),
                "mean_temperature_c": round(sum(temps) / len(temps), 2) if temps else None,
                "max_wind_speed_kmh": round(max(winds), 2) if winds else None,
                "total_precipitation_mm": round(sum(precips), 2) if precips else None,
            }
        })

    # Save to primary corrected file
    out_path = out_dir / "india_era5_regional_weather_points.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "metadata": {
                "dataset_id": "open_meteo_era5_india_regional",
                "layer_name": "era5_regional_weather_samples",
                "provenance": "ECMWF ERA5 Reanalysis via Open-Meteo Historical Weather API",
                "record_type": "ERA5 Regional Reference Points (Agro-Climatic Baseline)",
                "feature_count": len(norm_features),
                "notes": "Regional representative model grid samples; not physical ground weather station telemetry."
            },
            "features": norm_features
        }, f, indent=2)

    # Also save to legacy filename for backward compatibility
    legacy_out_path = out_dir / "india_agro_climatic_stations.geojson"
    with open(legacy_out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": norm_features}, f, indent=2)

    size, sha, md5 = compute_checksums(out_path)
    summaries.append({
        "layer": "era5_regional_weather_samples",
        "file": str(out_path.name),
        "feature_count": len(norm_features),
        "size_bytes": size,
        "sha256": sha,
        "md5": md5
    })
    logger.info(f"Processed ERA5 Regional Weather Points: {len(norm_features)} features ({size} bytes)")
    return summaries


# ==============================================================================
# Layer 9: Raster Profiles (Copernicus DEM, WorldCover, WorldPop)
# ==============================================================================

def process_raster_profiles(raw_dir: Path, processed_dir: Path) -> List[Dict[str, Any]]:
    logger.info("--- Generating Raster Profiles & Metadata Analysis ---")
    summaries = []

    # 1. Copernicus DEM GLO-30
    dem_path = raw_dir / "elevation" / "copernicus_dem" / "Copernicus_DSM_COG_10_N24_00_E078_00_DEM.tif"
    if dem_path.exists():
        out_dir = processed_dir / "terrain"
        out_dir.mkdir(parents=True, exist_ok=True)
        size, sha, md5 = compute_checksums(dem_path)
        im = Image.open(str(dem_path))
        profile = {
            "dataset_id": "copernicus_dem_glo30_india",
            "layer_name": "elevation_glo30",
            "file_name": dem_path.name,
            "file_format": "Cloud-Optimized GeoTIFF (COG)",
            "file_size_bytes": size,
            "sha256": sha,
            "md5": md5,
            "dimensions_pixels": list(im.size),
            "spatial_resolution": "30m (1 arc-second)",
            "coordinate_reference_system": "EPSG:4326 (EGM96 vertical datum)",
            "bounding_box": [78.0, 24.0, 79.0, 25.0],
            "hazard_relevance": ["wildfire", "flood", "earthquake"],
            "morphological_derivatives": ["slope", "aspect", "topographic_wetness_index"],
            "nodata_value": -99999.0
        }
        out_path = out_dir / "copernicus_dem_glo30_profile.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        summaries.append({
            "layer": "elevation_glo30",
            "file": str(out_path.name),
            "feature_count": im.size[0] * im.size[1],
            "size_bytes": size,
            "sha256": sha,
            "md5": md5
        })
        logger.info(f"Generated Copernicus DEM Profile ({im.size[0]}x{im.size[1]} pixels)")

    # 2. ESA WorldCover 10m
    wc_path = raw_dir / "land_cover" / "esa_worldcover" / "ESA_WorldCover_10m_2021_v200_N24E078_Map.tif"
    if wc_path.exists():
        out_dir = processed_dir / "land_cover"
        out_dir.mkdir(parents=True, exist_ok=True)
        size, sha, md5 = compute_checksums(wc_path)
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(str(wc_path))
        profile = {
            "dataset_id": "esa_worldcover_2021_india",
            "layer_name": "land_cover_worldcover",
            "file_name": wc_path.name,
            "file_format": "Cloud-Optimized GeoTIFF (COG)",
            "file_size_bytes": size,
            "sha256": sha,
            "md5": md5,
            "dimensions_pixels": list(im.size),
            "spatial_resolution": "10m",
            "coordinate_reference_system": "EPSG:4326",
            "bounding_box": [78.0, 21.0, 81.0, 24.0],
            "hazard_relevance": ["wildfire", "flood"],
            "classes": {
                "10": "Tree cover",
                "20": "Shrubland",
                "30": "Grassland",
                "40": "Cropland",
                "50": "Built-up",
                "60": "Bare / sparse vegetation",
                "70": "Snow and ice",
                "80": "Permanent water bodies",
                "90": "Herbaceous wetland",
                "95": "Mangroves",
                "100": "Moss and lichen"
            },
            "nodata_value": 0
        }
        out_path = out_dir / "esa_worldcover_profile.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        summaries.append({
            "layer": "land_cover_worldcover",
            "file": str(out_path.name),
            "feature_count": im.size[0] * im.size[1],
            "size_bytes": size,
            "sha256": sha,
            "md5": md5
        })
        logger.info(f"Generated ESA WorldCover Profile ({im.size[0]}x{im.size[1]} pixels)")

    # 3. WorldPop India 1km Population Density
    wp_path = raw_dir / "population" / "worldpop" / "ind_pd_2020_1km.tif"
    if wp_path.exists():
        out_dir = processed_dir / "population"
        out_dir.mkdir(parents=True, exist_ok=True)
        size, sha, md5 = compute_checksums(wp_path)
        im = Image.open(str(wp_path))
        profile = {
            "dataset_id": "worldpop_pop_2020_india",
            "layer_name": "population_density_worldpop",
            "file_name": wp_path.name,
            "file_format": "GeoTIFF (32-bit float)",
            "file_size_bytes": size,
            "sha256": sha,
            "md5": md5,
            "dimensions_pixels": list(im.size),
            "spatial_resolution": "1km (30 arc-seconds)",
            "coordinate_reference_system": "EPSG:4326",
            "geographic_coverage": "Entire Territory of India (National Coverage)",
            "bounding_box": [68.1, 6.5, 97.4, 35.5],
            "hazard_relevance": ["wildfire", "flood", "earthquake"],
            "unit": "people per square kilometer",
            "nodata_value": -99999.0
        }
        out_path = out_dir / "worldpop_population_profile.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        summaries.append({
            "layer": "population_density_worldpop",
            "file": str(out_path.name),
            "feature_count": im.size[0] * im.size[1],
            "size_bytes": size,
            "sha256": sha,
            "md5": md5
        })
        logger.info(f"Generated WorldPop Population Profile ({im.size[0]}x{im.size[1]} pixels)")

    return summaries


def run_pipeline():
    base_dir = Path("data")
    raw_dir = base_dir / "raw" / "geospatial"
    processed_dir = base_dir / "processed" / "geospatial"
    processed_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = []
    all_summaries.extend(process_administrative_boundaries(raw_dir, processed_dir))
    all_summaries.extend(process_hospitals(raw_dir, processed_dir))
    all_summaries.extend(process_fire_stations(raw_dir, processed_dir))
    all_summaries.extend(process_rivers(raw_dir, processed_dir))
    all_summaries.extend(process_settlements(raw_dir, processed_dir))
    all_summaries.extend(process_roads(raw_dir, processed_dir))
    all_summaries.extend(process_fire_observations(raw_dir, processed_dir))
    all_summaries.extend(process_weather_grid(raw_dir, processed_dir))
    all_summaries.extend(process_raster_profiles(raw_dir, processed_dir))

    # Save master execution manifest
    manifest_path = processed_dir / "processed_layers_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "pipeline": "scout_national_geospatial_normalizer",
            "geographic_scope": "National Coverage (Republic of India)",
            "total_layers": len(all_summaries),
            "layers": all_summaries
        }, f, indent=2)

    logger.info(f"=== Pipeline Complete! Processed {len(all_summaries)} layers. Manifest saved to {manifest_path} ===")


if __name__ == "__main__":
    run_pipeline()
