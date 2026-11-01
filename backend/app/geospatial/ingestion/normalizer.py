"""
backend/app/geospatial/ingestion/normalizer.py
Robust GeoJSON feature parsing, coordinate validation, category classification,
and multi-hazard relevance mapping.
Milestone 10: Persistent Geospatial Data Integration.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
import pyproj
import shapely.geometry
import shapely.validation
from shapely.ops import transform

from app.geospatial.schemas import FeatureCategory
from app.geospatial.ingestion.schemas import NormalizedFeature

logger = logging.getLogger(__name__)

# Namespace for generating deterministic UUIDs when upstream ID is missing
SCOUT_GEO_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d")

# Category inference rules
INFRASTRUCTURE_TAGS = {
    "amenity": {"hospital", "clinic", "fire_station", "police", "shelter", "pharmacy", "school", "university", "townhall"},
    "healthcare": {"hospital", "clinic", "centre", "doctor"},
    "emergency": {"fire_station", "yes", "disaster_help_point", "emergency_ward_entrance"},
    "railway": {"station", "halt", "subway_entrance"},
    "aeroway": {"aerodrome", "helipad"},
    "power": {"substation", "generator", "plant"},
}

ROAD_TAGS = {
    "highway": {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "road", "track"},
}

VEGETATION_TAGS = {
    "landuse": {"forest", "meadow", "grass", "orchard", "vineyard", "scrub", "allotments"},
    "natural": {"wood", "scrub", "tree", "tree_row", "grassland", "heath"},
}

WATER_TAGS = {
    "waterway": {"river", "stream", "canal", "drain", "ditch"},
    "natural": {"water", "wetland", "glacier"},
    "water": {"river", "lake", "reservoir", "pond", "basin"},
}

SETTLEMENT_TAGS = {
    "landuse": {"residential", "commercial", "industrial", "retail", "institutional"},
    "place": {"city", "town", "suburb", "neighbourhood", "village", "hamlet", "isolated_dwelling"},
}


class FeatureNormalizationError(Exception):
    """Raised when a geographic feature fails schema or geometry validation."""
    pass


def infer_feature_category(properties: Dict[str, Any]) -> FeatureCategory:
    """
    Infers the canonical FeatureCategory from source feature properties or OSM tags.
    """
    # 1. Direct category match
    raw_cat = properties.get("category")
    if raw_cat:
        for cat in FeatureCategory:
            if cat.value.lower() == str(raw_cat).lower():
                return cat

    # 2. Infrastructure
    for key, values in INFRASTRUCTURE_TAGS.items():
        val = str(properties.get(key, "")).lower()
        if val in values:
            return FeatureCategory.INFRASTRUCTURE

    # 3. Roads
    for key, values in ROAD_TAGS.items():
        val = str(properties.get(key, "")).lower()
        if val in values:
            return FeatureCategory.ROAD

    # 4. Vegetation / Land cover
    for key, values in VEGETATION_TAGS.items():
        val = str(properties.get(key, "")).lower()
        if val in values:
            return FeatureCategory.VEGETATION

    # 5. Water bodies / Hydrology
    for key, values in WATER_TAGS.items():
        val = str(properties.get(key, "")).lower()
        if val in values:
            return FeatureCategory.WATER_BODY

    # 6. Settlements / Built-up areas
    for key, values in SETTLEMENT_TAGS.items():
        val = str(properties.get(key, "")).lower()
        if val in values:
            return FeatureCategory.SETTLEMENT

    # 7. Administrative
    if str(properties.get("boundary", "")).lower() == "administrative":
        return FeatureCategory.ADMINISTRATIVE

    return FeatureCategory.OTHER


def infer_hazard_relevance(
    category: FeatureCategory,
    properties: Dict[str, Any],
) -> List[str]:
    """
    Maps a geographic feature to relevant disaster categories (wildfire, flood, earthquake).
    Preserves explicitly tagged hazard_relevance when present.
    """
    explicit = properties.get("hazard_relevance")
    if isinstance(explicit, list) and explicit:
        return sorted(list({str(h).lower() for h in explicit}))

    relevance: Set[str] = set()

    # Wildfire: vegetation (fuel), roads (evacuation), settlements (assets), critical infrastructure
    if category == FeatureCategory.VEGETATION:
        relevance.add("wildfire")
    elif category in (FeatureCategory.SETTLEMENT, FeatureCategory.ROAD):
        relevance.add("wildfire")
    elif category == FeatureCategory.INFRASTRUCTURE:
        amenity = str(properties.get("amenity", "")).lower()
        if amenity in ("fire_station", "hospital", "clinic", "shelter") or properties.get("emergency") == "yes":
            relevance.add("wildfire")

    # Flood: water bodies, floodplains, low-lying infrastructure, roads, settlements
    if category == FeatureCategory.WATER_BODY:
        relevance.add("flood")
    elif category in (FeatureCategory.SETTLEMENT, FeatureCategory.ROAD, FeatureCategory.INFRASTRUCTURE):
        relevance.add("flood")

    # Earthquake: settlements, infrastructure, roads (critical lifeline connectivity)
    if category in (FeatureCategory.SETTLEMENT, FeatureCategory.INFRASTRUCTURE, FeatureCategory.ROAD):
        relevance.add("earthquake")

    # Fallback: if nothing matched, assign general exposure
    if not relevance:
        relevance.add("wildfire")
        relevance.add("flood")

    return sorted(list(relevance))


def validate_and_transform_geometry(
    raw_geometry: Dict[str, Any],
    source_crs: str = "EPSG:4326",
) -> Tuple[shapely.geometry.base.BaseGeometry, str, Tuple[float, float, float, float]]:
    """
    Validates, repairs, optionally transforms, and extracts bounding box for a geometry.
    Returns: (shapely_geom, geometry_type_str, (min_lon, min_lat, max_lon, max_lat))
    """
    if not isinstance(raw_geometry, dict) or "type" not in raw_geometry or "coordinates" not in raw_geometry:
        raise FeatureNormalizationError("Invalid GeoJSON geometry structure")

    try:
        geom = shapely.geometry.shape(raw_geometry)
    except Exception as exc:
        raise FeatureNormalizationError(f"Failed to parse geometry: {exc}")

    if geom.is_empty:
        raise FeatureNormalizationError("Geometry is empty")

    # Transform CRS if source is not EPSG:4326 or WGS84
    normalized_crs = source_crs.strip().upper()
    if normalized_crs not in ("EPSG:4326", "WGS84", "CRS84", "URN:OGC:DEF:CRS:OGC:1.3:CRS84"):
        try:
            transformer = pyproj.Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
            geom = transform(transformer.transform, geom)
        except Exception as exc:
            raise FeatureNormalizationError(f"Failed CRS transformation from {source_crs} to EPSG:4326: {exc}")

    # Validate and repair topological validity
    if not geom.is_valid:
        logger.warning(f"Repairing invalid geometry using make_valid/buffer(0)")
        try:
            geom = shapely.validation.make_valid(geom)
        except Exception:
            geom = geom.buffer(0)

        if not geom.is_valid or geom.is_empty:
            raise FeatureNormalizationError("Geometry is topologically invalid and could not be repaired")

    # Validate coordinate ranges (WGS84)
    minx, miny, maxx, maxy = geom.bounds
    if minx < -180.0 or maxx > 180.0:
        raise FeatureNormalizationError(f"Longitude out of WGS84 bounds [-180, 180]: [{minx}, {maxx}]")
    if miny < -90.0 or maxy > 90.0:
        raise FeatureNormalizationError(f"Latitude out of WGS84 bounds [-90, 90]: [{miny}, {maxy}]")

    geom_type = geom.geom_type
    return geom, geom_type, (minx, miny, maxx, maxy)


def normalize_feature(
    raw_feature: Dict[str, Any],
    layer_name: str,
    source_crs: str = "EPSG:4326",
) -> NormalizedFeature:
    """
    Converts a single raw GeoJSON Feature into a validated, normalized feature schema.
    """
    if not isinstance(raw_feature, dict):
        raise FeatureNormalizationError("Feature must be a dictionary")

    properties = raw_feature.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}

    # Extract geometry
    raw_geom = raw_feature.get("geometry")
    if not raw_geom:
        raise FeatureNormalizationError("Feature lacks a geometry")

    geom, geom_type, bbox = validate_and_transform_geometry(raw_geom, source_crs=source_crs)

    # Resolve upstream feature ID
    source_feature_id = (
        raw_feature.get("id")
        or properties.get("id")
        or properties.get("osm_id")
        or properties.get("@id")
    )
    if source_feature_id:
        source_feature_id = str(source_feature_id)
    else:
        # Generate stable UUID5 based on layer and WKT
        source_feature_id = str(uuid.uuid5(SCOUT_GEO_NAMESPACE, f"{layer_name}:{geom.wkt}"))

    # Resolve feature name
    name = (
        properties.get("name")
        or properties.get("name:en")
        or properties.get("label")
        or properties.get("title")
        or properties.get("description")
        or "Unnamed Feature"
    )
    name = str(name).strip()[:256]

    # Resolve canonical category & hazard relevance
    category = infer_feature_category(properties)
    hazard_relevance = infer_hazard_relevance(category, properties)

    return NormalizedFeature(
        source_feature_id=source_feature_id,
        layer_name=layer_name,
        category=category,
        name=name,
        properties=properties,
        geometry_wkt=geom.wkt,
        geometry_type=geom_type,
        source_crs="EPSG:4326",
        hazard_relevance=hazard_relevance,
        bbox_min_lon=bbox[0],
        bbox_min_lat=bbox[1],
        bbox_max_lon=bbox[2],
        bbox_max_lat=bbox[3],
    )
