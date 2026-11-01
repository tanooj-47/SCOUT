"""
backend/app/geospatial/persistent_context.py
Persistent Geospatial Context Service.
Bridges PostGIS spatial repository to M08 geospatial domain models and exposure engine.
Milestone 10: Persistent Geospatial Data Integration.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID
from geoalchemy2.shape import to_shape
import shapely.geometry
from sqlalchemy.orm import Session

from app.geospatial.coordinates import (
    geodesic_distance_meters,
    validate_coordinates,
)
from app.geospatial.geometry import geometry_to_geojson_dict
from app.geospatial.schemas import (
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    GeoJSONGeometry,
    SpatialRelationship,
)
from app.geospatial.repository import GeospatialFeatureRepository
from app.models.geospatial import GeographicFeature

logger = logging.getLogger(__name__)

# Expected canonical layers for a comprehensive multi-hazard assessment
EXPECTED_CANONICAL_LAYERS = {
    "critical_facilities",
    "hydrology",
    "transportation",
    "land_cover",
    "settlements",
}


def feature_to_domain_item(
    feature: GeographicFeature,
    distance_meters: float,
    radius_meters: float,
    include_geometry: bool = False,
) -> GeographicFeatureItem:
    """
    Transforms a persistent PostGIS GeographicFeature model into a GeographicFeatureItem domain model.
    """
    # 1. Determine topological relationship
    if distance_meters <= 0.001:
        relationship = SpatialRelationship.INTERSECTS
    elif distance_meters <= radius_meters:
        relationship = SpatialRelationship.WITHIN_RADIUS
    elif distance_meters <= radius_meters * 1.1:
        relationship = SpatialRelationship.ADJACENT
    else:
        relationship = SpatialRelationship.DISJOINT

    # 2. Map canonical category
    try:
        cat_enum = FeatureCategory(feature.category)
    except ValueError:
        cat_enum = FeatureCategory.OTHER

    # 3. Geometry extraction if requested
    geojson_geom: Optional[GeoJSONGeometry] = None
    if include_geometry and feature.geometry is not None:
        try:
            shp = to_shape(feature.geometry)
            raw_dict = geometry_to_geojson_dict(shp)
            geojson_geom = GeoJSONGeometry(
                type=raw_dict.get("type", "Point"),
                coordinates=raw_dict.get("coordinates", []),
            )
        except Exception as exc:
            logger.warning(f"Could not serialize feature {feature.id} geometry: {exc}")

    # 4. Construct metadata
    meta = dict(feature.properties or {})
    meta["source_feature_id"] = feature.source_feature_id
    meta["layer_name"] = feature.layer_name
    meta["geometry_type"] = feature.geometry_type
    meta["hazard_relevance"] = feature.hazard_relevance or []

    source_dataset_name = (
        feature.source.dataset_name if feature.source else feature.layer_name
    )

    return GeographicFeatureItem(
        id=str(feature.id),
        name=feature.name,
        category=cat_enum,
        distance_meters=round(float(distance_meters), 2),
        relationship=relationship,
        source_dataset=source_dataset_name,
        geometry=geojson_geom,
        metadata=meta,
    )


class PersistentGeospatialContextService:
    """
    Service providing persistent real-world geographic context querying,
    layer discovery, and spatial exposure analysis backed by PostgreSQL/PostGIS.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repository = GeospatialFeatureRepository(db)

    def query_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float = 5000.0,
        categories: Optional[List[FeatureCategory]] = None,
        layer_name: Optional[str] = None,
        hazard: Optional[str] = None,
        limit: int = 50,
        include_geometry: bool = False,
    ) -> List[GeographicFeatureItem]:
        """
        Queries persistent features within radius of coordinate.
        """
        validate_coordinates(latitude, longitude)
        cat_strs = [c.value for c in categories] if categories else None
        first_cat = cat_strs[0] if cat_strs and len(cat_strs) == 1 else None

        records = self.repository.query_within_radius(
            center_lon=longitude,
            center_lat=latitude,
            radius_meters=radius_meters,
            layer_name=layer_name,
            category=first_cat,
            hazard=hazard,
            limit=limit,
        )

        items: List[GeographicFeatureItem] = []
        for feat, dist in records:
            # If multiple categories were supplied, filter here if not filtered at SQL
            if cat_strs and feat.category not in cat_strs:
                continue
            item = feature_to_domain_item(
                feature=feat,
                distance_meters=dist,
                radius_meters=radius_meters,
                include_geometry=include_geometry,
            )
            items.append(item)

        return items

    def analyze_exposure(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float = 5000.0,
        disaster_type: str = "wildfire",
        include_geometry: bool = False,
    ) -> Tuple[ExposureSummary, List[GeographicFeatureItem], List[str], List[str]]:
        """
        Performs comprehensive exposure analysis on the persistent PostGIS database.
        Returns: (ExposureSummary, features, contributing_factors, missing_data_indicators)
        """
        features = self.query_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            hazard=disaster_type,
            limit=100,
            include_geometry=include_geometry,
        )

        # 1. Tally category counts and closest feature
        category_counts: Dict[str, int] = {}
        closest_distance: Optional[float] = None
        closest_name: Optional[str] = None

        for feat in features:
            cat_name = feat.category.value
            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

            if closest_distance is None or feat.distance_meters < closest_distance:
                closest_distance = feat.distance_meters
                closest_name = feat.name

        summary = ExposureSummary(
            total_features_found=len(features),
            category_counts=category_counts,
            closest_feature_distance_meters=closest_distance,
            closest_feature_name=closest_name,
            highlighted_exposed_features=features[:10],
        )

        # 2. Determine missing data indicators based on available layers in DB
        available_layers = {lyr["layer_name"] for lyr in self.repository.list_layers()}
        missing_indicators: List[str] = []
        for expected in sorted(EXPECTED_CANONICAL_LAYERS):
            if expected not in available_layers:
                missing_indicators.append(f"Missing geographic layer: {expected}")

        # 3. Derive explainable contributing factors
        contributing_factors: List[str] = []
        if disaster_type == "wildfire":
            veg_count = category_counts.get(FeatureCategory.VEGETATION.value, 0)
            if veg_count > 0:
                contributing_factors.append(
                    f"Identified {veg_count} vegetation/fuel patches within {int(radius_meters)}m radius."
                )
            infra_count = category_counts.get(FeatureCategory.INFRASTRUCTURE.value, 0)
            if infra_count > 0:
                contributing_factors.append(
                    f"Detected {infra_count} critical infrastructure assets exposed to fire perimeter."
                )
        elif disaster_type == "flood":
            water_count = category_counts.get(FeatureCategory.WATER_BODY.value, 0)
            if water_count > 0:
                contributing_factors.append(
                    f"Found {water_count} hydrological features/corridors prone to inundation."
                )
            settlement_count = category_counts.get(FeatureCategory.SETTLEMENT.value, 0)
            if settlement_count > 0:
                contributing_factors.append(
                    f"Identified {settlement_count} residential/settlement areas exposed to flood drainage."
                )
        elif disaster_type == "earthquake":
            settlement_count = category_counts.get(FeatureCategory.SETTLEMENT.value, 0)
            infra_count = category_counts.get(FeatureCategory.INFRASTRUCTURE.value, 0)
            contributing_factors.append(
                f"Assessed structural risk for {settlement_count} settlements and {infra_count} critical assets."
            )

        if not contributing_factors:
            contributing_factors.append(
                f"No immediate hazard-specific exposure detected within {int(radius_meters)}m buffer."
            )

        return summary, features, contributing_factors, missing_indicators
