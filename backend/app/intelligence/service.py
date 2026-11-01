"""
backend/app/intelligence/service.py
Core orchestration service for SCOUT Multimodal Disaster Intelligence (Milestone 11).
Coordinates vision inference, atmospheric queries, geographic exposure analysis,
evidence fusion, heuristic threat assessment, and explanation generation.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from PIL import Image
from sqlalchemy.orm import Session

from app.intelligence.adapters.environmental_adapter import EnvironmentalModelAdapter
from app.intelligence.adapters.geospatial_adapter import GeospatialModelAdapter
from app.intelligence.adapters.vision_adapter import VisionModelAdapter
from app.intelligence.explanations import ExplanationGenerator
from app.intelligence.fusion import MultimodalFusionEngine
from app.intelligence.risk import HeuristicRiskAssessor
from app.intelligence.schemas import (
    ContextSummary,
    CoordinateLocation,
    DisasterAssessmentLevel,
    EvidenceItem,
    IncidentObservationInput,
    IncidentStatus,
    IntelligenceHealthResponse,
    MultimodalIntelligenceAssessment,
)
from app.schemas.incident import DisasterType

logger = logging.getLogger(__name__)


class MultimodalIntelligenceService:
    """
    Main orchestration service coordinating multimodal intelligence analysis.
    Decoupled from HTTP controllers for clean testability and service-level execution.
    """

    def __init__(
        self,
        vision_adapter: Optional[VisionModelAdapter] = None,
        environmental_adapter: Optional[EnvironmentalModelAdapter] = None,
        geospatial_adapter: Optional[GeospatialModelAdapter] = None,
    ) -> None:
        self.vision = vision_adapter or VisionModelAdapter()
        self.environmental = environmental_adapter or EnvironmentalModelAdapter()
        self.geospatial = geospatial_adapter or GeospatialModelAdapter()

    def analyze_observation(
        self,
        observation: IncidentObservationInput,
        image_bytes: Optional[bytes] = None,
        db: Optional[Session] = None,
    ) -> MultimodalIntelligenceAssessment:
        """
        Executes end-to-end multimodal intelligence workflow:
        Observation -> Evidence Collection -> Fusion -> Risk Assessment -> Explanation
        """
        lat = observation.latitude
        lon = observation.longitude
        loc = CoordinateLocation(latitude=lat, longitude=lon)
        radius = observation.search_radius_meters
        disaster_type = observation.disaster_type

        evidence_items: List[EvidenceItem] = []

        # 1. Computer Vision Modality
        image_source: Optional[Union[str, bytes, Image.Image]] = image_bytes or observation.image_path
        cv_item = self.vision.collect_evidence(
            image_input=image_source,
            location=loc,
        )
        evidence_items.append(cv_item)

        # 2. Environmental Modality
        env_item = self.environmental.collect_evidence(
            latitude=lat,
            longitude=lon,
            incident_id=observation.incident_id,
        )
        evidence_items.append(env_item)

        # 3. Geospatial Exposure Modality
        geo_item, context_summary = self.geospatial.collect_evidence(
            latitude=lat,
            longitude=lon,
            radius_meters=radius,
            disaster_type=disaster_type.value,
            db=db,
        )
        evidence_items.append(geo_item)

        # 4. Multimodal Fusion
        fusion = MultimodalFusionEngine.fuse(
            evidence_items=evidence_items,
            context_summary=context_summary,
        )

        # 5. Explainable Risk Assessment (Separating Hazard, Exposure, Consequence)
        (
            level,
            risk_index,
            hazard_eval,
            exposure_eval,
            consequence_eval,
            has_conflicts,
            uncertainty_qual,
        ) = HeuristicRiskAssessor.evaluate_detailed(
            disaster_type=disaster_type,
            fusion=fusion,
        )

        # 6. Explanation and Caveat Generation
        rationale = ExplanationGenerator.generate_rationale(
            disaster_type=disaster_type,
            level=level,
            risk_index=risk_index,
            fusion=fusion,
        )
        contributing = ExplanationGenerator.generate_contributing_factors(
            disaster_type=disaster_type,
            fusion=fusion,
        )
        mitigating = ExplanationGenerator.generate_mitigating_factors(
            disaster_type=disaster_type,
            fusion=fusion,
        )
        caveats = ExplanationGenerator.generate_caveats(
            disaster_type=disaster_type,
            fusion=fusion,
        )

        # 7. Operational Incident Status & Evidence Summary
        incident_status, incident_severity = HeuristicRiskAssessor.determine_incident_status(
            fusion.active_evidence_state,
            hazard_eval.hazard_level if hazard_eval else DisasterAssessmentLevel.LOW,
            is_corroborated=fusion.is_corroborated,
        )

        summary_parts = [
            f"Physical Incident Evidence: {incident_status.value} ({fusion.active_evidence_state.value})"
        ]
        if incident_severity is not None:
            summary_parts.append(f"Incident Severity: {incident_severity.value}")
        else:
            summary_parts.append("Incident Severity: UNASSESSED")
        if fusion.fire_weather_level:
            fwi_str = f", FWI={fusion.environmental_fwi:.1f}" if fusion.environmental_fwi is not None else ""
            summary_parts.append(f"Fire Weather: {fusion.fire_weather_level}{fwi_str}")
        else:
            summary_parts.append("Fire Weather: UNAVAILABLE")
        summary_parts.append(
            f"Exposure: {exposure_eval.exposure_level if exposure_eval else 'UNKNOWN'}"
        )
        if consequence_eval:
            summary_parts.append(f"Consequence: {consequence_eval.consequence_tier.value}")
        evidence_summary_text = "; ".join(summary_parts)

        uncertainty_text = uncertainty_qual
        if exposure_eval and "UNVERIFIED" in exposure_eval.exposure_level:
            unverified_note = "Exposure is UNVERIFIED (0 local features in catalog)"
            uncertainty_text = f"{uncertainty_qual}; {unverified_note}" if uncertainty_qual else unverified_note

        if uncertainty_text and (not caveats or caveats[0] != uncertainty_text):
            caveats.insert(0, uncertainty_text)

        return MultimodalIntelligenceAssessment(
            incident_id=observation.incident_id,
            disaster_type=disaster_type.value,
            coordinates=loc,
            assessment_level=level,
            heuristic_risk_index=risk_index,
            assessment_rationale=rationale,
            hazard_assessment=hazard_eval,
            exposure_assessment=exposure_eval,
            consequence_assessment=consequence_eval,
            active_incident_evidence=fusion.active_evidence_state,
            incident_status=incident_status,
            incident_severity=incident_severity,
            fire_weather_danger=fusion.fire_weather_level,
            fire_weather_danger_level=fusion.fire_weather_level,
            fire_weather_score=fusion.fire_weather_score,
            geographic_exposure=exposure_eval.exposure_level if exposure_eval else None,
            potential_consequences=consequence_eval.consequence_tier if consequence_eval else None,
            has_conflicting_evidence=has_conflicts,
            uncertainty=uncertainty_text,
            uncertainty_qualification=uncertainty_text,
            evidence_summary=evidence_summary_text,
            contributing_factors=contributing,
            mitigating_factors=mitigating,
            missing_evidence=fusion.missing_streams,
            conflicting_evidence=fusion.conflicting_streams,
            evidence_items=evidence_items,
            context_summary=context_summary,
            caveats_and_limitations=caveats,
        )

    def get_health(self, db: Optional[Session] = None) -> IntelligenceHealthResponse:
        """
        Probes operational readiness across all three underlying modalities.
        """
        # Check CV model weights loadability
        cv_ok = False
        try:
            self.vision.load_model()
            cv_ok = True
        except Exception:
            cv_ok = False

        # Check Environmental provider
        env_ok = True
        try:
            if not self.environmental.service:
                env_ok = False
        except Exception:
            env_ok = False

        # Check Geospatial catalog
        geo_ok = True
        try:
            if not self.geospatial.service:
                geo_ok = False
        except Exception:
            geo_ok = False

        status = "operational" if (cv_ok and env_ok and geo_ok) else "degraded"

        return IntelligenceHealthResponse(
            status=status,
            cv_model_available=cv_ok,
            environmental_service_available=env_ok,
            geospatial_service_available=geo_ok,
            supported_disaster_types=[d.value for d in DisasterType],
            version="1.0.0",
        )

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Exposes operational capabilities, model lineage, and known constraints.
        """
        return {
            "supported_disaster_types": [d.value for d in DisasterType],
            "calibrated_modalities": {
                "wildfire": {
                    "computer_vision": "BaselineCNN (M07 Champion, val_macro_f1=0.8387)",
                    "environmental": "Open-Meteo & NASA POWER with Canadian CFS-FWI Engine",
                    "geospatial": "M08/M10 Vector Catalog & Exposure Engine",
                    "status": "calibrated_heuristic",
                },
                "flood": {
                    "computer_vision": "unimplemented",
                    "environmental": "uncalibrated_reanalysis",
                    "geospatial": "hydrology_proximity_only",
                    "status": "uncalibrated_indicators_only",
                },
                "earthquake": {
                    "computer_vision": "unimplemented",
                    "environmental": "unapplicable",
                    "geospatial": "infrastructure_proximity_only",
                    "status": "uncalibrated_indicators_only",
                },
            },
            "freshness_thresholds_hours": {
                "computer_vision": 4.0,
                "environmental": 3.0,
                "geospatial": 720.0,
            },
            "core_constraints": [
                "Heuristic risk index is a 0.0 - 100.0 score, not an empirical probability.",
                "Missing data never defaults to zero risk; triggers INSUFFICIENT_DATA when critical streams are absent.",
                "Persistent PostGIS integration requires active database connectivity.",
            ],
        }
