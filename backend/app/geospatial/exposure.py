"""
backend/app/geospatial/exposure.py
Exposure analysis engine computing geographic proximity, intersections, and layer coverage.
"""

from collections import defaultdict
import math
from typing import Dict, List, Optional

from app.core.config import settings
from app.geospatial.context import GeographicContextCatalog, default_context_catalog
from app.geospatial.coordinates import validate_coordinates
from app.geospatial.schemas import (
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    SpatialRelationship,
)
from app.geospatial.spatial_queries import validate_query_radius


class ExposureEngine:
    """
    Computes objective spatial exposure metrics from available geographic features.
    
    Guarantees:
    - Pure evidence-based spatial aggregations (counts, shortest distances, topological relationships).
    - No speculative population claims without verified census data.
    - Explicit missing layer identification.
    - Configurable operational priority exposure distance threshold.
    """

    def __init__(
        self,
        catalog: Optional[GeographicContextCatalog] = None,
        priority_threshold_meters: Optional[float] = None,
    ):
        self.catalog = catalog or default_context_catalog
        if priority_threshold_meters is not None:
            if (
                not isinstance(priority_threshold_meters, (int, float))
                or not math.isfinite(priority_threshold_meters)
                or priority_threshold_meters <= 0.0
            ):
                raise ValueError(
                    f"priority_threshold_meters must be a positive finite number, got {priority_threshold_meters}"
                )
            self.priority_threshold_meters = float(priority_threshold_meters)
        else:
            self.priority_threshold_meters = settings.GEOSPATIAL_PRIORITY_THRESHOLD_METERS

    def analyze_exposure(
        self,
        latitude: float,
        longitude: float,
        search_radius_meters: float,
        categories: Optional[List[FeatureCategory]] = None,
        limit: int = 100,
        include_geometry: bool = False,
        priority_threshold_meters: Optional[float] = None,
    ) -> ExposureSummary:
        """
        Executes exposure analysis for a geographic point of origin.
        """
        coord = validate_coordinates(latitude, longitude)
        radius_m = validate_query_radius(search_radius_meters)

        # Operational high-priority exposure threshold (explicit argument override or configured default)
        if priority_threshold_meters is not None:
            threshold_m = float(priority_threshold_meters)
            if not (math.isfinite(threshold_m) and threshold_m > 0.0):
                raise ValueError(
                    f"priority_threshold_meters must be a positive finite number, got {threshold_m}"
                )
        else:
            threshold_m = self.priority_threshold_meters

        # Retrieve nearby features from catalog
        features = self.catalog.query_nearby_features(
            latitude=coord.latitude,
            longitude=coord.longitude,
            radius_meters=radius_m,
            categories=categories,
            limit=limit,
            include_geometry=include_geometry,
        )

        total_count = len(features)
        category_counts: Dict[str, int] = defaultdict(int)
        closest_distance: Optional[float] = None
        closest_name: Optional[str] = None
        highlighted: List[GeographicFeatureItem] = []

        for feat in features:
            category_counts[feat.category.value] += 1

            if closest_distance is None or feat.distance_meters < closest_distance:
                closest_distance = feat.distance_meters
                closest_name = feat.name

            # Highlight features within operational priority proximity or intersecting
            if (
                feat.relationship == SpatialRelationship.INTERSECTS
                or feat.distance_meters <= threshold_m
            ):
                if len(highlighted) < 10:  # Top 10 highlights
                    highlighted.append(feat)

        return ExposureSummary(
            total_features_found=total_count,
            category_counts=dict(category_counts),
            closest_feature_distance_meters=closest_distance,
            closest_feature_name=closest_name,
            highlighted_exposed_features=highlighted,
        )
