"""
backend/app/geospatial/context.py
Geographic context extraction, feature representation, and spatial catalog indexing.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import shapely.geometry

logger = logging.getLogger(__name__)

from app.geospatial.coordinates import (
    geodesic_distance_meters,
    validate_coordinates,
)
from app.geospatial.geometry import (
    compute_geodesic_distance_to_geometry,
    geometry_to_geojson_dict,
)
from app.geospatial.schemas import (
    FeatureCategory,
    GeographicFeatureItem,
    GeoJSONGeometry,
    SpatialRelationship,
)
from app.geospatial.spatial_queries import validate_query_radius


class GeographicContextCatalog:
    """
    In-memory spatial index and feature catalog for geographic entities.
    Enforces scientific integrity:
    1. Only holds explicitly loaded features with known provenance.
    2. Enforces unique feature_id identity to prevent duplicate entities.
    3. Transparently reports missing layer indicators.
    """

    def __init__(self):
        self._feature_by_id: Dict[str, Dict[str, Any]] = {}
        self._available_layers: Set[str] = set()

    @property
    def _features(self) -> List[Dict[str, Any]]:
        """Returns list of registered features for backward compatibility."""
        return list(self._feature_by_id.values())

    def _recalculate_available_layers(self) -> None:
        """Synchronizes available layer set with currently registered features."""
        self._available_layers = {
            item["category"].value for item in self._feature_by_id.values()
        }

    def add_feature(
        self,
        feature_id: str,
        name: str,
        category: FeatureCategory,
        geometry: shapely.geometry.base.BaseGeometry,
        source_dataset: str,
        metadata: Optional[Dict[str, Any]] = None,
        overwrite: bool = True,
    ) -> bool:
        """
        Registers a verified geographic feature into the spatial catalog.

        Deduplication & Conflict Prevention:
        - If `feature_id` is new: Inserts feature, updates layer index, returns True.
        - If `feature_id` exists and `overwrite=True` (default):
            Deterministically replaces the existing feature with updated attributes.
            Recalculates category availability to maintain index consistency if category changed.
            Returns True.
        - If `feature_id` exists and `overwrite=False`:
            Rejects the conflicting addition, preserving the existing record unchanged.
            Returns False.

        Args:
            feature_id: Unique string identifier for the spatial entity.
            name: Human-readable feature name or label.
            category: Domain feature category.
            geometry: Valid Shapely geometry.
            source_dataset: Provenance / data registry name.
            metadata: Optional source-specific attributes.
            overwrite: Whether to overwrite an existing feature sharing the same ID (default True).

        Returns:
            bool: True if feature was inserted or updated; False if duplicate was rejected.
        """
        if not feature_id or not isinstance(feature_id, str):
            raise ValueError(f"feature_id must be a non-empty string, got {feature_id!r}")

        is_existing = feature_id in self._feature_by_id
        if is_existing and not overwrite:
            return False

        meta = dict(metadata or {})
        try:
            if "latitude" not in meta:
                meta["latitude"] = float(geometry.centroid.y)
            if "longitude" not in meta:
                meta["longitude"] = float(geometry.centroid.x)
        except Exception:
            pass

        self._feature_by_id[feature_id] = {
            "id": feature_id,
            "name": name,
            "category": category,
            "geometry": geometry,
            "source_dataset": source_dataset,
            "metadata": meta,
        }
        self._recalculate_available_layers()
        return True

    def remove_feature(self, feature_id: str) -> bool:
        """
        Removes a feature by ID if present.
        Maintains category index consistency.
        Returns True if removed, False if not found.
        """
        if feature_id in self._feature_by_id:
            del self._feature_by_id[feature_id]
            self._recalculate_available_layers()
            return True
        return False

    def get_feature(self, feature_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a feature dict by ID, or None if not found."""
        return self._feature_by_id.get(feature_id)

    def clear(self) -> None:
        """Clears all registered features and resets category indexing."""
        self._feature_by_id.clear()
        self._available_layers.clear()

    def __len__(self) -> int:
        """Returns total number of unique registered features."""
        return len(self._feature_by_id)

    def is_layer_available(self, category: FeatureCategory) -> bool:
        """Returns True if at least one feature exists for the category."""
        return category.value in self._available_layers

    def get_missing_layers(self, requested_categories: Optional[List[FeatureCategory]] = None) -> List[str]:
        """Identifies which feature categories have no registered geographic data."""
        target_cats = requested_categories or list(FeatureCategory)
        missing = []
        for cat in target_cats:
            if cat.value not in self._available_layers:
                missing.append(f"{cat.value}_layer_unavailable")
        return missing

    def query_nearby_features(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float,
        categories: Optional[List[FeatureCategory]] = None,
        limit: int = 50,
        include_geometry: bool = False,
    ) -> List[GeographicFeatureItem]:
        """
        Queries features within radius_meters from the origin coordinate.
        Calculates exact shortest geodesic distance in meters to each feature geometry.
        """
        coord = validate_coordinates(latitude, longitude)
        radius_m = validate_query_radius(radius_meters)

        target_cats = set(c.value for c in categories) if categories else None
        origin_pt = shapely.geometry.Point(coord.longitude, coord.latitude)

        results: List[GeographicFeatureItem] = []

        for item in self._feature_by_id.values():
            cat = item["category"]
            if target_cats and cat.value not in target_cats:
                continue

            geom = item["geometry"]
            distance_m = compute_geodesic_distance_to_geometry(
                origin_lat=coord.latitude,
                origin_lon=coord.longitude,
                target_geom=geom,
            )

            if distance_m <= radius_m:
                # Determine topological relationship
                if geom.intersects(origin_pt) or geom.contains(origin_pt):
                    rel = SpatialRelationship.INTERSECTS
                elif distance_m < 50.0:
                    rel = SpatialRelationship.ADJACENT
                else:
                    rel = SpatialRelationship.WITHIN_RADIUS

                geojson_geom = None
                if include_geometry:
                    g_dict = geometry_to_geojson_dict(geom)
                    geojson_geom = GeoJSONGeometry(type=g_dict["type"], coordinates=g_dict["coordinates"])

                results.append(
                    GeographicFeatureItem(
                        id=item["id"],
                        name=item["name"],
                        category=cat,
                        distance_meters=round(distance_m, 2),
                        relationship=rel,
                        source_dataset=item["source_dataset"],
                        geometry=geojson_geom,
                        metadata=item["metadata"],
                    )
                )

        # Sort by distance ascending
        results.sort(key=lambda f: f.distance_meters)
        return results[:limit]


def load_calibration_dehradun_features(
    catalog: GeographicContextCatalog,
    file_path: Optional[Path] = None,
) -> int:
    """
    Explicit calibration & test fixture loader for Dehradun synthetic features.
    
    SAFETY & INTEGRITY CONSTRAINT:
    calibration_dehradun_features.geojson contains features explicitly marked:
        "synthetic_test_fixture": True, "operational_use": False
    This function MUST NEVER be invoked during default operational initialization.
    Preserved strictly for reproducible synthetic integration testing and assessor calibration.
    """
    if file_path is None:
        candidates = [
            Path("data/geospatial/calibration_dehradun_features.geojson"),
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "geospatial" / "calibration_dehradun_features.geojson",
        ]
        for c in candidates:
            if c.exists():
                file_path = c
                break

    if not file_path or not file_path.exists():
        logger.info("No calibration GeoJSON fixture file found at %s", file_path)
        return 0

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        features = data.get("features", [])
        count = 0
        for f in features:
            props = f.get("properties", {})
            f_id = str(f.get("id") or props.get("id") or f"feat-{count}")
            cat_str = props.get("category", "")
            amenity = props.get("amenity", "")
            healthcare = props.get("healthcare", "")

            # Category resolution
            if cat_str == "infrastructure" or amenity in ("hospital", "fire_station") or healthcare == "hospital":
                cat = FeatureCategory.INFRASTRUCTURE
            elif cat_str == "settlement":
                cat = FeatureCategory.SETTLEMENT
            elif cat_str == "road":
                cat = FeatureCategory.ROAD
            elif cat_str == "water_body":
                cat = FeatureCategory.WATER_BODY
            elif cat_str == "vegetation":
                cat = FeatureCategory.VEGETATION
            elif cat_str == "administrative":
                cat = FeatureCategory.ADMINISTRATIVE
            else:
                try:
                    cat = FeatureCategory(cat_str)
                except ValueError:
                    cat = FeatureCategory.OTHER

            geom = shapely.geometry.shape(f["geometry"])
            name = props.get("name") or amenity or f_id

            catalog.add_feature(
                feature_id=f_id,
                name=name,
                category=cat,
                geometry=geom,
                source_dataset="calibration_dehradun_features",
                metadata=props,
                overwrite=True,
            )
            count += 1
        logger.info("Loaded %d CALIBRATION features from %s (operational_use=False)", count, file_path.name)
        return count
    except Exception as exc:
        logger.warning("Failed to load calibration GeoJSON features: %s", exc)
        return 0


# Backward-compatible alias for existing test suites
load_default_geojson_features = load_calibration_dehradun_features


def load_operational_geojson_layers(
    catalog: GeographicContextCatalog,
    base_dir: Optional[Path] = None,
) -> int:
    """
    Populates spatial catalog with verified real-world operational layers
    from data/processed/geospatial/ with confirmed provenance and validation status.
    
    Layers loaded:
    - india_populated_places.geojson (Natural Earth 10m, GENERALIZED_NATIONAL)
    - india_fire_stations_clipped.geojson (OSM Sovereign Clipped, PARTIAL)
    - india_major_rivers.geojson (Natural Earth 10m, GENERALIZED_NATIONAL)
    """
    if base_dir is None:
        candidates = [
            Path("data/processed/geospatial"),
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "processed" / "geospatial",
        ]
        for c in candidates:
            if c.exists():
                base_dir = c
                break

    if not base_dir or not base_dir.exists():
        logger.info("No processed geospatial operational directory found at %s", base_dir)
        return 0

    operational_layer_specs = [
        (
            base_dir / "settlements" / "india_populated_places.geojson",
            FeatureCategory.SETTLEMENT,
            "ne_10m_populated_places",
            "GENERALIZED_NATIONAL: Macro-urban hubs (Tier 1-3 cities); does not include rural villages.",
        ),
        (
            base_dir / "fire_stations" / "india_fire_stations_clipped.geojson",
            FeatureCategory.INFRASTRUCTURE,
            "osm_fire_stations_clipped",
            "PARTIAL: Sovereign-clipped exploratory sample; incomplete national coverage.",
        ),
        (
            base_dir / "rivers" / "india_major_rivers.geojson",
            FeatureCategory.WATER_BODY,
            "ne_10m_rivers",
            "GENERALIZED_NATIONAL: 1:10m generalized macro-channels.",
        ),
    ]

    total_loaded = 0
    for layer_path, default_cat, src_id, limitation in operational_layer_specs:
        if not layer_path.exists():
            continue
        try:
            data = json.loads(layer_path.read_text(encoding="utf-8"))
            features = data.get("features", [])
            for f in features:
                props = f.get("properties", {})
                f_id = str(f.get("id") or props.get("id") or f"{src_id}-{total_loaded}")
                name = props.get("name") or props.get("NAME") or props.get("amenity") or f_id

                # Metadata enrichment
                meta = dict(props)
                meta["coverage_classification"] = limitation
                meta["operational_use"] = True
                meta["synthetic_test_fixture"] = False

                geom = shapely.geometry.shape(f["geometry"])
                catalog.add_feature(
                    feature_id=f_id,
                    name=name,
                    category=default_cat,
                    geometry=geom,
                    source_dataset=src_id,
                    metadata=meta,
                    overwrite=True,
                )
                total_loaded += 1
            logger.info("Loaded operational layer %s (%d features)", layer_path.name, len(features))
        except Exception as exc:
            logger.warning("Failed loading operational layer %s: %s", layer_path.name, exc)

    return total_loaded


# Global operational catalog instance
# STARTS CLEAN AND EMPTY BY DEFAULT per scientific safety rules.
# Synthetic calibration fixtures (operational_use=False) are NEVER auto-loaded.
default_context_catalog = GeographicContextCatalog()
