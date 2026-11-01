"""
backend/app/geospatial/risk.py
Structured geographic risk assessment foundation.
Distinguishes objective spatial exposure from predictive hazard modeling.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import uuid

from app.geospatial.context import GeographicContextCatalog, default_context_catalog
from app.geospatial.coordinates import get_utm_epsg_for_coordinate, validate_coordinates
from app.geospatial.exposure import ExposureEngine
from app.geospatial.schemas import (
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
    IncidentSpatialContext,
    SpatialRelationship,
)
from app.geospatial.spatial_queries import validate_query_radius


class BaseRiskAssessor(ABC):
    """
    Abstract foundation for disaster-specific geographic risk assessments.
    Enforces clear separation between spatial exposure and speculative simulation.
    """

    @property
    @abstractmethod
    def supported_disaster_type(self) -> str:
        """The disaster category supported by this assessor."""
        pass

    @abstractmethod
    def evaluate(
        self,
        latitude: float,
        longitude: float,
        search_radius_meters: float,
        features: List[GeographicFeatureItem],
        exposure_summary: ExposureSummary,
        catalog: GeographicContextCatalog,
        incident_id: Optional[uuid.UUID] = None,
        disaster_metadata: Optional[Dict[str, Any]] = None,
        data_provider: str = "local_vector_catalog",
    ) -> GeospatialAssessmentResponse:
        """Constructs an explainable, fact-based assessment response."""
        pass


class WildfireRiskAssessor(BaseRiskAssessor):
    """
    Geospatial assessor for wildfire incidents.
    Focuses on vegetative fuel proximity, access route availability, and settlement adjacency.
    """

    @property
    def supported_disaster_type(self) -> str:
        return "wildfire"

    def evaluate(
        self,
        latitude: float,
        longitude: float,
        search_radius_meters: float,
        features: List[GeographicFeatureItem],
        exposure_summary: ExposureSummary,
        catalog: GeographicContextCatalog,
        incident_id: Optional[uuid.UUID] = None,
        disaster_metadata: Optional[Dict[str, Any]] = None,
        data_provider: str = "local_vector_catalog",
    ) -> GeospatialAssessmentResponse:
        coord = validate_coordinates(latitude, longitude)
        radius_m = validate_query_radius(search_radius_meters)
        utm_zone = get_utm_epsg_for_coordinate(coord.latitude, coord.longitude)

        contributing_factors: List[str] = []
        missing_indicators: List[str] = []
        limitations: List[str] = [
            "Proximity to features reflects static geographic adjacency only and does NOT simulate wildfire rate of spread or ember spotting.",
            "Weather, wind vectors, fuel moisture, and terrain slope are not modeled in this spatial exposure assessment.",
            "Features are limited to currently ingested geospatial catalog layers.",
        ]

        # 1. Evaluate settlements
        settlement_count = exposure_summary.category_counts.get(FeatureCategory.SETTLEMENT.value, 0)
        if settlement_count > 0:
            closest_settlement = next(
                (f for f in features if f.category == FeatureCategory.SETTLEMENT), None
            )
            dist_str = f"{closest_settlement.distance_meters:.0f}m" if closest_settlement else "nearby"
            contributing_factors.append(
                f"Identified {settlement_count} human settlement zone(s) within search radius. "
                f"Closest settlement ({closest_settlement.name if closest_settlement else 'unnamed'}) is {dist_str} from origin."
            )
        else:
            if not catalog.is_layer_available(FeatureCategory.SETTLEMENT):
                missing_indicators.append("settlement_boundary_layer_unavailable")

        # 2. Evaluate vegetation and forest canopy
        veg_count = exposure_summary.category_counts.get(FeatureCategory.VEGETATION.value, 0)
        if veg_count > 0:
            contributing_factors.append(
                f"Detected {veg_count} continuous forest/vegetation polygon(s) within {radius_m:.0f}m, indicating potential combustible fuel load."
            )
        else:
            if not catalog.is_layer_available(FeatureCategory.VEGETATION):
                missing_indicators.append("forest_canopy_and_fuel_layer_unavailable")

        # 3. Evaluate road networks (egress and access routes)
        road_count = exposure_summary.category_counts.get(FeatureCategory.ROAD.value, 0)
        if road_count > 0:
            contributing_factors.append(
                f"Identified {road_count} major roadway/access corridor(s) within the assessment perimeter."
            )
        else:
            if not catalog.is_layer_available(FeatureCategory.ROAD):
                missing_indicators.append("road_network_transportation_layer_unavailable")

        # 4. Evaluate water bodies (potential fire barriers or water extraction points)
        water_count = exposure_summary.category_counts.get(FeatureCategory.WATER_BODY.value, 0)
        if water_count > 0:
            contributing_factors.append(
                f"Identified {water_count} water body/reservoir feature(s) capable of serving as aerial suppression water sources or natural fuel breaks."
            )
        else:
            if not catalog.is_layer_available(FeatureCategory.WATER_BODY):
                missing_indicators.append("hydrology_and_water_body_layer_unavailable")

        # 5. Evaluate critical infrastructure
        infra_count = exposure_summary.category_counts.get(FeatureCategory.INFRASTRUCTURE.value, 0)
        if infra_count > 0:
            contributing_factors.append(
                f"Alert: {infra_count} critical infrastructure asset(s) (power grid, communications, or emergency facilities) situated within {radius_m:.0f}m."
            )
        else:
            if not catalog.is_layer_available(FeatureCategory.INFRASTRUCTURE):
                missing_indicators.append("critical_infrastructure_layer_unavailable")

        # Fallback if no features present
        if exposure_summary.total_features_found == 0:
            store_name = "persistent spatial database" if data_provider == "postgis_spatial_db" else "active catalog"
            contributing_factors.append(
                f"No registered geographic entities found within the specified search perimeter in the {store_name}."
            )

        context = IncidentSpatialContext(
            incident_id=incident_id,
            disaster_type="wildfire",
            latitude=coord.latitude,
            longitude=coord.longitude,
            srid=4326,
            utm_epsg=utm_zone,
            search_radius_meters=radius_m,
        )

        return GeospatialAssessmentResponse(
            assessment_id=f"assess-wildfire-{uuid.uuid4().hex[:12]}",
            incident_context=context,
            exposure_summary=exposure_summary,
            features=features,
            contributing_factors=contributing_factors,
            missing_data_indicators=missing_indicators,
            assessment_limitations=limitations,
            data_provider=data_provider,
        )


class FloodRiskAssessor(BaseRiskAssessor):
    """
    Geospatial assessor for flood incidents.
    Focuses on hydrology, drainage basins, and low-lying infrastructure.
    """

    @property
    def supported_disaster_type(self) -> str:
        return "flood"

    def evaluate(
        self,
        latitude: float,
        longitude: float,
        search_radius_meters: float,
        features: List[GeographicFeatureItem],
        exposure_summary: ExposureSummary,
        catalog: GeographicContextCatalog,
        incident_id: Optional[uuid.UUID] = None,
        disaster_metadata: Optional[Dict[str, Any]] = None,
        data_provider: str = "local_vector_catalog",
    ) -> GeospatialAssessmentResponse:
        coord = validate_coordinates(latitude, longitude)
        radius_m = validate_query_radius(search_radius_meters)
        utm_zone = get_utm_epsg_for_coordinate(coord.latitude, coord.longitude)

        contributing_factors: List[str] = []
        missing_indicators: List[str] = [
            "digital_elevation_model_raster_unavailable",
            "river_gauge_telemetry_unavailable",
        ]
        limitations: List[str] = [
            "Hydraulic flow modeling and bathymetry are not computed in this proximity-based assessment.",
            "Terrain elevation contours are required to establish actual flood inundation vulnerability.",
        ]

        water_count = exposure_summary.category_counts.get(FeatureCategory.WATER_BODY.value, 0)
        if water_count > 0:
            contributing_factors.append(
                f"Identified {water_count} water body/river channel feature(s) intersecting or within {radius_m:.0f}m."
            )

        settlement_count = exposure_summary.category_counts.get(FeatureCategory.SETTLEMENT.value, 0)
        if settlement_count > 0:
            contributing_factors.append(
                f"{settlement_count} human settlement zone(s) located within {radius_m:.0f}m of the flood observation point."
            )

        if exposure_summary.total_features_found == 0:
            store_name = "persistent spatial database" if data_provider == "postgis_spatial_db" else "active catalog"
            contributing_factors.append(
                f"No hydrological or settlement entities found within the specified search perimeter in the {store_name}."
            )

        context = IncidentSpatialContext(
            incident_id=incident_id,
            disaster_type="flood",
            latitude=coord.latitude,
            longitude=coord.longitude,
            srid=4326,
            utm_epsg=utm_zone,
            search_radius_meters=radius_m,
        )

        return GeospatialAssessmentResponse(
            assessment_id=f"assess-flood-{uuid.uuid4().hex[:12]}",
            incident_context=context,
            exposure_summary=exposure_summary,
            features=features,
            contributing_factors=contributing_factors,
            missing_data_indicators=missing_indicators,
            assessment_limitations=limitations,
            data_provider=data_provider,
        )


class EarthquakeRiskAssessor(BaseRiskAssessor):
    """
    Geospatial assessor for earthquake incidents.
    Focuses on epicentral proximity, population centers, and lifeline infrastructure.
    """

    @property
    def supported_disaster_type(self) -> str:
        return "earthquake"

    def evaluate(
        self,
        latitude: float,
        longitude: float,
        search_radius_meters: float,
        features: List[GeographicFeatureItem],
        exposure_summary: ExposureSummary,
        catalog: GeographicContextCatalog,
        incident_id: Optional[uuid.UUID] = None,
        disaster_metadata: Optional[Dict[str, Any]] = None,
        data_provider: str = "local_vector_catalog",
    ) -> GeospatialAssessmentResponse:
        coord = validate_coordinates(latitude, longitude)
        radius_m = validate_query_radius(search_radius_meters)
        utm_zone = get_utm_epsg_for_coordinate(coord.latitude, coord.longitude)

        contributing_factors: List[str] = []
        missing_indicators: List[str] = [
            "active_fault_trace_layer_unavailable",
            "soil_amplification_vs30_raster_unavailable",
        ]
        limitations: List[str] = [
            "Ground motion shaking intensity (MMI) and peak ground acceleration (PGA) are not modeled.",
            "Structural vulnerability of buildings is unknown.",
        ]

        infra_count = exposure_summary.category_counts.get(FeatureCategory.INFRASTRUCTURE.value, 0)
        if infra_count > 0:
            contributing_factors.append(
                f"{infra_count} critical infrastructure asset(s) within {radius_m:.0f}m of seismic epicenter/observation."
            )

        if exposure_summary.total_features_found == 0:
            store_name = "persistent spatial database" if data_provider == "postgis_spatial_db" else "active catalog"
            contributing_factors.append(
                f"No infrastructure or settlement entities found within the specified search perimeter in the {store_name}."
            )

        context = IncidentSpatialContext(
            incident_id=incident_id,
            disaster_type="earthquake",
            latitude=coord.latitude,
            longitude=coord.longitude,
            srid=4326,
            utm_epsg=utm_zone,
            search_radius_meters=radius_m,
        )

        return GeospatialAssessmentResponse(
            assessment_id=f"assess-earthquake-{uuid.uuid4().hex[:12]}",
            incident_context=context,
            exposure_summary=exposure_summary,
            features=features,
            contributing_factors=contributing_factors,
            missing_data_indicators=missing_indicators,
            assessment_limitations=limitations,
            data_provider=data_provider,
        )


# Factory registry for disaster assessors
ASSESSORS: Dict[str, BaseRiskAssessor] = {
    "wildfire": WildfireRiskAssessor(),
    "flood": FloodRiskAssessor(),
    "earthquake": EarthquakeRiskAssessor(),
}


def get_risk_assessor(disaster_type: str) -> BaseRiskAssessor:
    """Retrieves the appropriate disaster assessor or defaults to wildfire."""
    d_type = (disaster_type or "wildfire").lower().strip()
    return ASSESSORS.get(d_type, ASSESSORS["wildfire"])
