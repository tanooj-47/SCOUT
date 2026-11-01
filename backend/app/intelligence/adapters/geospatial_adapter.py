"""
backend/app/intelligence/adapters/geospatial_adapter.py
Geospatial Subsystem Adapter for Milestones 08 & 10 Spatial Services.
Extracts geographic exposure context, infrastructure proximity,
and creates structured geospatial EvidenceItems.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.geospatial.exceptions import PostGISUnavailableError
from app.geospatial.schemas import (
    ExposureAnalysisRequest,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
)
from app.intelligence.context import ContextAggregator
from app.intelligence.evidence import EvidenceCollector
from app.intelligence.schemas import ContextSummary, CoordinateLocation, EvidenceItem
from app.services.geospatial_service import GeospatialService

logger = logging.getLogger(__name__)


class GeospatialModelAdapter:
    """
    Adapter encapsulating spatial exposure analysis and geographic feature queries.
    Seamlessly handles PostGIS persistent queries with fallback to in-memory/file catalogs.
    """

    def __init__(self, service: Optional[GeospatialService] = None) -> None:
        self.service = service or GeospatialService()

    def collect_evidence(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float = 5000.0,
        disaster_type: str = "wildfire",
        db: Optional[Session] = None,
    ) -> Tuple[EvidenceItem, ContextSummary]:
        """
        Executes spatial exposure query and constructs both an EvidenceItem and ContextSummary.
        """
        location = CoordinateLocation(latitude=latitude, longitude=longitude)
        request = ExposureAnalysisRequest(
            latitude=latitude,
            longitude=longitude,
            search_radius_meters=radius_meters,
            disaster_type=disaster_type,
            include_geometry=False,
        )

        try:
            assessment_resp: GeospatialAssessmentResponse = self.service.analyze_exposure(
                request=request,
                db=db,
            )

            features: List[GeographicFeatureItem] = assessment_resp.features or []
            missing_layers: List[str] = assessment_resp.missing_data_indicators or []
            data_provider: str = assessment_resp.data_provider or "local_vector_catalog"

            context_summary = ContextAggregator.aggregate(
                features=features,
                missing_layers=missing_layers,
                data_provider=data_provider,
            )

            raw_payload: Dict[str, Any] = {
                "total_features_found": len(features),
                "data_provider": data_provider,
                "missing_layers": missing_layers,
                "settlements_found": context_summary.settlements_found,
                "closest_settlement_distance_meters": context_summary.closest_settlement_distance_meters,
                "hospitals_found": context_summary.hospitals_found,
                "fire_stations_found": context_summary.fire_stations_found,
                "road_corridors_found": context_summary.road_corridors_found,
                "water_bodies_found": context_summary.water_bodies_found,
            }

            evidence_item = EvidenceCollector.create_geospatial_evidence(
                summary_dict=raw_payload,
                features_count=len(features),
                source=data_provider,
                location=location,
                missing_layers=missing_layers,
            )

            return evidence_item, context_summary

        except PostGISUnavailableError:
            # Strictly preserve M10 contract: do not swallow configured database failures
            logger.error("Persistent PostGIS query failed; propagating PostGISUnavailableError per M10 contract")
            raise
        except Exception as exc:
            logger.warning(f"Geospatial exposure query failed: {exc}")
            # Construct empty summary with failure note
            empty_summary = ContextSummary(
                settlements_found=0,
                hospitals_found=0,
                fire_stations_found=0,
                road_corridors_found=0,
                water_bodies_found=0,
                total_features_evaluated=0,
                spatial_coverage_notes=[f"Geospatial query error: {str(exc)}"],
            )
            evidence_item = EvidenceCollector.create_geospatial_evidence(
                summary_dict={"error": str(exc)},
                features_count=0,
                source="geospatial_error",
                location=location,
                missing_layers=["all_spatial_layers"],
            )
            return evidence_item, empty_summary
