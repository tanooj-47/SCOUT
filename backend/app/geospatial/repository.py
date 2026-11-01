"""
backend/app/geospatial/repository.py
Database repository for persistent geographic features, data sources, and ingestion runs.
Powered by SQLAlchemy and PostGIS spatial operators.
Milestone 10: Persistent Geospatial Data Integration.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
from sqlalchemy import func, select, and_, desc, asc
from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_Intersects, ST_MakeEnvelope, ST_MakePoint, ST_SetSRID

from app.models.geospatial import (
    GeographicDataSource,
    GeographicIngestionRun,
    GeographicFeature,
)


class GeospatialFeatureRepository:
    """
    Data access layer for persistent geographic features and spatial datasets.
    Uses PostGIS spatial indexing (GiST) for fast bounding-box and geodesic radius searches.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, feature_id: Union[uuid.UUID, str]) -> Optional[GeographicFeature]:
        """Fetches a feature by its database UUID primary key."""
        if isinstance(feature_id, str):
            feature_id = uuid.UUID(feature_id)
        return self.session.get(GeographicFeature, feature_id)

    def get_by_source_and_feature_id(
        self,
        source_id: uuid.UUID,
        source_feature_id: str,
        layer_name: str,
    ) -> Optional[GeographicFeature]:
        """Fetches a feature by its upstream natural compound key."""
        stmt = select(GeographicFeature).where(
            and_(
                GeographicFeature.source_id == source_id,
                GeographicFeature.source_feature_id == source_feature_id,
                GeographicFeature.layer_name == layer_name,
            )
        )
        return self.session.scalars(stmt).first()

    def query_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        layer_name: Optional[str] = None,
        category: Optional[str] = None,
        hazard: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[GeographicFeature]:
        """
        Retrieves features intersecting a spatial bounding box envelope in EPSG:4326.
        Bounded by limit (max 500) and offset to prevent full-country memory load.
        """
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        conditions = [ST_Intersects(GeographicFeature.geometry, envelope)]

        if layer_name:
            conditions.append(GeographicFeature.layer_name == layer_name)
        if category:
            conditions.append(GeographicFeature.category == category)
        if hazard:
            conditions.append(GeographicFeature.hazard_relevance.contains([hazard]))

        stmt = select(GeographicFeature).where(and_(*conditions)).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def query_within_radius(
        self,
        center_lon: float,
        center_lat: float,
        radius_meters: float,
        layer_name: Optional[str] = None,
        category: Optional[str] = None,
        hazard: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Tuple[GeographicFeature, float]]:
        """
        Queries features within a geodesic radius (meters) from origin point.
        Calculates exact ellipsoidal distance using PostGIS geography casting.
        Returns list of (GeographicFeature, distance_meters) sorted nearest to farthest.
        """
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        origin_geom = ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)
        origin_geog = func.geography(origin_geom)
        feat_geog = func.geography(GeographicFeature.geometry)

        distance_expr = ST_Distance(feat_geog, origin_geog).label("distance_meters")

        conditions = [ST_DWithin(feat_geog, origin_geog, radius_meters)]

        if layer_name:
            conditions.append(GeographicFeature.layer_name == layer_name)
        if category:
            conditions.append(GeographicFeature.category == category)
        if hazard:
            conditions.append(GeographicFeature.hazard_relevance.contains([hazard]))

        stmt = (
            select(GeographicFeature, distance_expr)
            .where(and_(*conditions))
            .order_by(asc(distance_expr))
            .limit(limit)
            .offset(offset)
        )

        results = self.session.execute(stmt).all()
        return [(row[0], float(row[1])) for row in results]

    def list_layers(self) -> List[Dict[str, Any]]:
        """
        Aggregates registered layers with feature counts and distinct categories.
        """
        stmt = (
            select(
                GeographicFeature.layer_name,
                func.count(GeographicFeature.id).label("feature_count"),
            )
            .group_by(GeographicFeature.layer_name)
            .order_by(GeographicFeature.layer_name)
        )
        layer_rows = self.session.execute(stmt).all()
        result = []
        for row in layer_rows:
            layer = row[0]
            count = row[1]
            cat_stmt = (
                select(GeographicFeature.category)
                .where(GeographicFeature.layer_name == layer)
                .distinct()
            )
            categories = list(self.session.scalars(cat_stmt).all())
            result.append(
                {
                    "layer_name": layer,
                    "feature_count": count,
                    "categories": sorted(categories),
                }
            )
        return result

    def list_sources(self) -> List[GeographicDataSource]:
        """Lists all registered external geographic data sources."""
        stmt = select(GeographicDataSource).order_by(
            GeographicDataSource.provider, GeographicDataSource.dataset_name
        )
        return list(self.session.scalars(stmt).all())

    def get_source_by_id(self, source_id: uuid.UUID) -> Optional[GeographicDataSource]:
        """Fetches a data source by UUID."""
        return self.session.get(GeographicDataSource, source_id)

    def list_ingestion_runs(self, limit: int = 50) -> List[GeographicIngestionRun]:
        """Lists recent ingestion audit runs ordered by start time descending."""
        stmt = (
            select(GeographicIngestionRun)
            .order_by(desc(GeographicIngestionRun.started_at))
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def count_features(self, layer_name: Optional[str] = None) -> int:
        """Returns total features count, optionally filtered by layer."""
        stmt = select(func.count(GeographicFeature.id))
        if layer_name:
            stmt = stmt.where(GeographicFeature.layer_name == layer_name)
        return self.session.scalar(stmt) or 0
