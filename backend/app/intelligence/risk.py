"""
backend/app/intelligence/risk.py
Transparent heuristic risk assessment engine for multimodal disaster observations.
Separates active wildfire hazard from fire weather danger, spatial exposure, and consequences.
Weather-only data (even extreme FWI) never establishes an active wildfire incident.
Proximity to human settlements or infrastructure never inflates active wildfire hazard.
Accounts for cross-modal contradictions without suppressing life-safety warnings.
"""

import logging
from typing import List, Optional, Tuple

from app.intelligence.fusion import FusionAnalysis
from app.intelligence.schemas import (
    ConsequenceAssessment,
    DisasterAssessmentLevel,
    ExposureAssessment,
    HazardAssessment,
    IncidentEvidenceState,
    IncidentStatus,
    VisualEvidenceState,
)
from app.schemas.incident import DisasterType

logger = logging.getLogger(__name__)


class HeuristicRiskAssessor:
    """
    Transparent, explainable risk assessment engine.
    Calculates separate active hazard, fire weather danger, exposure, and consequence assessments.
    Never misrepresents heuristic scores as calibrated incident probabilities.
    """

    @classmethod
    def determine_incident_status(
        cls,
        active_state: IncidentEvidenceState,
        haz_level: Optional[DisasterAssessmentLevel] = None,
        is_corroborated: bool = False,
    ) -> Tuple[IncidentStatus, Optional[DisasterAssessmentLevel]]:
        """
        Maps physical incident evidence to explicit operational incident status and severity.
        Decoupled from atmospheric fire weather conditions.

        Semantics:
        - FIELD_CONFIRMED: human/field verification on-scene -> CONFIRMED, severity from hazard.
        - Corroborated remote sensing (e.g. vision + satellite thermal radiometer) -> CONFIRMED, severity from hazard.
        - Single-stream vision (fire or smoke prediction) -> SUSPECTED. Single image CANNOT independently
          establish CRITICAL incident severity (capped at HIGH).
        - Single-stream satellite thermal anomaly -> SUSPECTED (capped at HIGH if uncorroborated).
        - Diffuse / conflicting visual scores -> SUSPECTED (capped at HIGH).
        - Neutral prediction (NO_SUPPORTING_EVIDENCE) -> UNCONFIRMED, incident_severity is None (unassessed).
        - Missing evidence (MISSING_EVIDENCE) -> INSUFFICIENT_EVIDENCE, incident_severity is None (unassessed).
        """
        if active_state == IncidentEvidenceState.FIELD_CONFIRMED:
            return IncidentStatus.CONFIRMED, (haz_level or DisasterAssessmentLevel.HIGH)
        elif is_corroborated and active_state in (
            IncidentEvidenceState.SUPPORTING_FIRE,
            IncidentEvidenceState.SUPPORTING_SMOKE,
            IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY,
        ):
            return IncidentStatus.CONFIRMED, (haz_level or DisasterAssessmentLevel.HIGH)
        elif active_state in (
            IncidentEvidenceState.SUPPORTING_FIRE,
            IncidentEvidenceState.SUPPORTING_SMOKE,
            IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY,
            IncidentEvidenceState.UNCERTAIN_OR_CONFLICTING,
        ):
            # Uncorroborated single-stream prediction: SUSPECTED
            # Single-image prediction cannot independently establish CRITICAL severity (capped at HIGH)
            eff_severity = haz_level or DisasterAssessmentLevel.HIGH
            if eff_severity == DisasterAssessmentLevel.CRITICAL:
                eff_severity = DisasterAssessmentLevel.HIGH
            return IncidentStatus.SUSPECTED, eff_severity
        elif active_state == IncidentEvidenceState.NO_SUPPORTING_EVIDENCE:
            return IncidentStatus.UNCONFIRMED, None
        else:  # MISSING_EVIDENCE
            return IncidentStatus.INSUFFICIENT_EVIDENCE, None

    @classmethod
    def evaluate(
        cls,
        disaster_type: DisasterType,
        fusion: FusionAnalysis,
    ) -> Tuple[DisasterAssessmentLevel, Optional[float]]:
        """
        Evaluates fused evidence to produce a categorical threat tier and heuristic index.
        Maintains backward compatibility by returning (DisasterAssessmentLevel, Optional[float]).
        """
        level, index, _, _, _, _, _ = cls.evaluate_detailed(disaster_type, fusion)
        return level, index

    @classmethod
    def evaluate_detailed(
        cls,
        disaster_type: DisasterType,
        fusion: FusionAnalysis,
    ) -> Tuple[
        DisasterAssessmentLevel,
        Optional[float],
        Optional[HazardAssessment],
        Optional[ExposureAssessment],
        Optional[ConsequenceAssessment],
        bool,
        Optional[str],
    ]:
        """
        Executes a rigorous 4-pillar assessment:
        1. Active Hazard Assessment: derived strictly from physical incident evidence (imagery, satellite, field).
        2. Fire Weather Danger: atmospheric dryness and combustibility indicators (tracked independently).
        3. Spatial Exposure Assessment: human settlements, hospitals, roads, water barriers.
        4. Potential Consequence Assessment: impact conditional on active hazard intersecting exposure.

        Returns:
            (overall_threat_level, heuristic_risk_index, hazard_eval, exposure_eval, consequence_eval, has_conflicts, uncertainty_qualification)
        """
        # 1. Non-wildfire disaster categories
        if disaster_type != DisasterType.WILDFIRE:
            logger.info(
                "Disaster type '%s' lacks calibrated ML models in M11. Returning INSUFFICIENT_DATA.",
                disaster_type.value,
            )
            return (
                DisasterAssessmentLevel.INSUFFICIENT_DATA,
                None,
                None,
                None,
                None,
                False,
                "Hazard type unsupported in current model registry.",
            )

        # 2. Insufficient data guard: both primary physical observation and weather modalities missing
        if not fusion.has_visual and not fusion.has_satellite and not fusion.has_field_report and not fusion.has_environmental:
            logger.warning(
                "All observation modalities are missing. Assessment INSUFFICIENT_DATA."
            )
            return (
                DisasterAssessmentLevel.INSUFFICIENT_DATA,
                None,
                None,
                None,
                None,
                False,
                "Both physical incident and meteorological evidence streams are unavailable.",
            )

        # =========================================================================
        # PILLAR 1: ACTIVE HAZARD ASSESSMENT (Derived strictly from physical fire evidence)
        # Weather-only data (even extreme FWI) must NEVER establish an active wildfire incident.
        # Neutral imagery does NOT prove fire-free.
        # =========================================================================
        hazard_factors: List[str] = []
        visual_score: Optional[float] = None
        s_haz: float = 0.0
        haz_level: DisasterAssessmentLevel = DisasterAssessmentLevel.LOW

        if fusion.has_visual:
            p_fire = fusion.visual_fire_probability or 0.0
            p_smoke = fusion.visual_smoke_probability or 0.0
            visual_score = max(0.0, min(100.0, (p_fire * 100.0) + (p_smoke * 50.0)))

        # Evaluate active physical incident evidence state
        active_state = fusion.active_evidence_state
        if active_state == IncidentEvidenceState.FIELD_CONFIRMED:
            s_haz = fusion.active_incident_score or 95.0
            haz_level = DisasterAssessmentLevel.CRITICAL
            hazard_factors.append("Active wildfire incident confirmed on-scene by emergency field personnel.")
        elif active_state == IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY:
            s_haz = fusion.active_incident_score or 85.0
            haz_level = DisasterAssessmentLevel.CRITICAL if (fusion.is_corroborated or s_haz >= 80.0) else DisasterAssessmentLevel.HIGH
            hazard_factors.append("Satellite thermal radiometer detected high-intensity radiative heat anomaly.")
        elif active_state == IncidentEvidenceState.SUPPORTING_FIRE:
            s_haz = fusion.active_incident_score or round((fusion.visual_fire_probability or 0.0) * 100.0, 1)
            haz_level = DisasterAssessmentLevel.CRITICAL if (fusion.is_corroborated and s_haz >= 70.0) else DisasterAssessmentLevel.HIGH
            if not fusion.is_corroborated and s_haz < 50.0:
                haz_level = DisasterAssessmentLevel.MODERATE
            hazard_factors.append(f"Visual model detected active flame features ({s_haz:.1f}% confidence).")
        elif active_state == IncidentEvidenceState.SUPPORTING_SMOKE:
            s_haz = fusion.active_incident_score or round((fusion.visual_smoke_probability or 0.0) * 75.0, 1)
            haz_level = DisasterAssessmentLevel.HIGH if s_haz >= 45.0 else DisasterAssessmentLevel.MODERATE
            hazard_factors.append(f"Visual model detected smoke plume signatures ({s_haz:.1f}% confidence).")
        elif active_state == IncidentEvidenceState.UNCERTAIN_OR_CONFLICTING:
            s_haz = fusion.active_incident_score or round(visual_score or 0.0, 1)
            haz_level = DisasterAssessmentLevel.MODERATE if s_haz >= 20.0 else DisasterAssessmentLevel.LOW
            hazard_factors.append("Visual classifier outputs diffuse or conflicting class probabilities.")
        elif active_state == IncidentEvidenceState.NO_SUPPORTING_EVIDENCE:
            # Submitted imagery shows no fire/smoke in view; active hazard is 0.0.
            # Explicitly state that neutral imagery does NOT eliminate regional fire risk.
            s_haz = 0.0
            haz_level = DisasterAssessmentLevel.LOW
            hazard_factors.append(
                "Submitted imagery exhibits no flame or smoke features in view (no_supporting_visual_evidence; "
                "does not eliminate regional fire risk due to field of view constraints)."
            )
        else:  # MISSING_EVIDENCE
            s_haz = 0.0
            haz_level = DisasterAssessmentLevel.LOW
            hazard_factors.append("No direct physical incident imagery or field reports available to verify active fire presence.")

        s_haz = max(0.0, min(100.0, round(s_haz, 1)))

        # =========================================================================
        # PILLAR 2: FIRE WEATHER DANGER (Tracked independently from active hazard)
        # =========================================================================
        environmental_score: Optional[float] = fusion.fire_weather_score
        if fusion.has_environmental:
            if fusion.environmental_fwi is not None:
                hazard_factors.append(
                    f"Fire Weather Index is {fusion.environmental_fwi:.1f} ({fusion.environmental_danger_rating or 'unrated'})."
                )
            elif fusion.temperature_c is not None and fusion.relative_humidity_pct is not None:
                temp = fusion.temperature_c
                rh = fusion.relative_humidity_pct
                hazard_factors.append(f"Atmospheric conditions: {temp:.1f}°C, {rh:.0f}% RH.")

        incident_status, incident_severity = cls.determine_incident_status(
            active_state,
            haz_level,
            is_corroborated=fusion.is_corroborated,
        )

        hazard_eval = HazardAssessment(
            hazard_score=s_haz,
            hazard_level=haz_level,
            visual_score=round(visual_score, 1) if visual_score is not None else None,
            environmental_score=round(environmental_score, 1) if environmental_score is not None else None,
            visual_evidence_state=active_state,
            visual_explanation=fusion.visual_explanation or "No visual observation evaluated.",
            active_incident_score=s_haz if active_state not in (IncidentEvidenceState.NO_SUPPORTING_EVIDENCE, IncidentEvidenceState.MISSING_EVIDENCE) else None,
            active_incident_level=incident_severity,
            active_incident_evidence=active_state,
            active_incident_explanation=fusion.active_evidence_explanation or "No active incident evidence evaluated.",
            incident_status=incident_status,
            incident_severity=incident_severity,
            fire_weather_score=round(environmental_score, 1) if environmental_score is not None else None,
            fire_weather_level=fusion.fire_weather_level,
            fire_weather_explanation=fusion.fire_weather_explanation or "No fire weather observation evaluated.",
            factors=hazard_factors,
        )

        # =========================================================================
        # PILLAR 3: EXPOSURE ASSESSMENT (Derived strictly from spatial infrastructure)
        # =========================================================================
        context = fusion.context_summary
        settlement_dist = context.closest_settlement_distance_meters
        hosp_dist = context.closest_hospital_distance_meters
        fire_dist = context.closest_fire_station_distance_meters
        exposure_factors: List[str] = []

        if context.total_features_evaluated == 0:
            s_exp = None
            exp_level = "UNVERIFIED (NO_LOCAL_FEATURES)"
            exposure_factors.append(
                "Spatial catalog holds 0 local features; exposure level is UNVERIFIED (reflects spatial data availability limits, not verified absence of vulnerability)."
            )
        else:
            if settlement_dist is not None:
                if settlement_dist < 1000.0:
                    geo_base = 70.0
                    exposure_factors.append(f"Populated place '{context.closest_settlement_name or 'settlement'}' within immediate radius ({settlement_dist:.0f}m).")
                elif settlement_dist < 3000.0:
                    geo_base = 45.0
                    exposure_factors.append(f"Human settlement situated {settlement_dist:.0f}m from observation point.")
                elif settlement_dist < 5000.0:
                    geo_base = 25.0
                    exposure_factors.append(f"Settlement located in outer perimeter ({settlement_dist:.0f}m).")
                else:
                    geo_base = 10.0
            else:
                geo_base = 10.0

            if hosp_dist is not None and hosp_dist < 2000.0:
                geo_base += 15.0
                exposure_factors.append(f"Healthcare facility situated {hosp_dist:.0f}m away.")

            if context.road_corridors_found > 0:
                geo_base += 5.0
                exposure_factors.append(f"Identified {context.road_corridors_found} road transport corridor(s).")

            if context.water_bodies_found > 0:
                geo_base = max(5.0, geo_base - 10.0)
                exposure_factors.append(f"Natural water barrier present ({context.water_bodies_found} water feature(s)).")

            if fire_dist is not None and fire_dist < 3000.0:
                geo_base = max(5.0, geo_base - 5.0)
                exposure_factors.append(f"Emergency fire station within operational reach ({fire_dist:.0f}m).")

            s_exp = max(0.0, min(100.0, round(geo_base, 1)))

            if s_exp >= 70.0:
                exp_level = "CRITICAL"
            elif s_exp >= 45.0:
                exp_level = "HIGH"
            elif s_exp >= 20.0:
                exp_level = "MODERATE"
            else:
                exp_level = "LOW"

        exposure_eval = ExposureAssessment(
            exposure_score=s_exp,
            exposure_level=exp_level,
            settlement_distance_meters=settlement_dist,
            hospital_distance_meters=hosp_dist,
            factors=exposure_factors,
        )

        # =========================================================================
        # PILLAR 4: CONSEQUENCE ASSESSMENT (Conditional on active hazard intersecting exposure)
        # If active hazard is zero, potential consequence is zero regardless of proximity.
        # =========================================================================
        if s_haz == 0.0:
            s_con = 0.0
            con_tier = DisasterAssessmentLevel.LOW
            con_rationale = (
                "Negligible consequence: no active wildfire hazard detected in physical observations. "
                "Infrastructure proximity presents zero immediate threat."
            )
        elif s_exp is None or context.total_features_evaluated == 0:
            s_con = None
            con_tier = DisasterAssessmentLevel.INSUFFICIENT_DATA
            con_rationale = (
                f"Active hazard score is {s_haz:.1f}, but spatial exposure is UNVERIFIED (0 local features in catalog). "
                "Consequence calculation cannot be determined (INSUFFICIENT_DATA) pending PostGIS or verified spatial data."
            )
        else:
            s_con = round(s_haz * (s_exp / 100.0), 1)
            if s_con >= 65.0:
                con_tier = DisasterAssessmentLevel.CRITICAL
            elif s_con >= 35.0:
                con_tier = DisasterAssessmentLevel.HIGH
            elif s_con >= 10.0:
                con_tier = DisasterAssessmentLevel.MODERATE
            else:
                con_tier = DisasterAssessmentLevel.LOW

            con_rationale = (
                f"Potential consequence tier is {con_tier.value} based on active hazard score {s_haz:.1f} "
                f"intersecting spatial exposure score {s_exp:.1f}."
            )

        consequence_eval = ConsequenceAssessment(
            consequence_score=s_con,
            consequence_tier=con_tier,
            rationale=con_rationale,
        )

        # =========================================================================
        # COMPOSITE THREAT TIER & RISK INDEX (Non-additive formulation)
        # =========================================================================
        # Rule 1: Proximity alone must NEVER elevate overall wildfire threat.
        # Rule 2: Weather alone (even extreme FWI) with zero active fire must NEVER establish
        #         an active wildfire incident (threat is capped at MODERATE fire weather alert).
        if s_haz == 0.0:
            if environmental_score is not None and environmental_score >= 50.0:
                # Elevated atmospheric combustibility without active fire -> MODERATE (Fire Weather Alert)
                overall_threat = DisasterAssessmentLevel.MODERATE
                composite_index = min(40.0, round(environmental_score * 0.4, 1))
            else:
                overall_threat = DisasterAssessmentLevel.LOW
                composite_index = 0.0
        elif s_haz < 20.0:
            # Low hazard: proximity cannot elevate threat tier beyond LOW
            overall_threat = DisasterAssessmentLevel.LOW
            exp_factor = (s_exp / 100.0) if s_exp is not None else 0.0
            composite_index = min(24.9, round(s_haz * (0.8 + 0.2 * exp_factor), 1))
        else:
            # Moderate to Critical hazard: composite blends hazard (70%) and consequence (30%)
            if s_exp is None or s_con is None or context.total_features_evaluated == 0:
                # Spatial exposure is unverified; base composite risk index directly on active hazard
                composite_index = round(s_haz, 1)
            else:
                composite_index = round((0.70 * s_haz) + (0.30 * s_con), 1)

            if composite_index >= 75.0:
                candidate_threat = DisasterAssessmentLevel.CRITICAL
            elif composite_index >= 50.0:
                candidate_threat = DisasterAssessmentLevel.HIGH
            elif composite_index >= 25.0:
                candidate_threat = DisasterAssessmentLevel.MODERATE
            else:
                candidate_threat = DisasterAssessmentLevel.LOW

            overall_threat = candidate_threat

        # Critical Override: Overwhelming flame probability (>= 0.85) situated close to settlement (<= 1000m)
        if (
            fusion.visual_fire_probability is not None
            and fusion.visual_fire_probability >= 0.85
            and settlement_dist is not None
            and settlement_dist <= 1000.0
        ):
            overall_threat = DisasterAssessmentLevel.CRITICAL
            composite_index = max(75.0, composite_index)

        # Critical Override for Field Confirmed / Satellite Thermal Anomaly near settlements
        if (
            active_state in (IncidentEvidenceState.FIELD_CONFIRMED, IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY)
            and settlement_dist is not None
            and settlement_dist <= 2000.0
        ):
            overall_threat = DisasterAssessmentLevel.CRITICAL
            composite_index = max(75.0, composite_index)

        # =========================================================================
        # TASK 3: CONTRADICTION & CONFLICT POLICY (Life-Safety Warning Preservation)
        # Do NOT suppress or downgrade CRITICAL life-safety warnings merely because
        # a secondary stream disagrees. Preserve highest credible severity.
        # =========================================================================
        has_conflicts = len(fusion.conflicting_streams) > 0
        uncertainty_qualification: Optional[str] = None

        if has_conflicts:
            conflict_summary = "; ".join(fusion.conflicting_streams)
            # Life-safety policy: CRITICAL threat tier is preserved without downgrade.
            uncertainty_qualification = (
                f"ELEVATED_UNCERTAINTY: Contradictory evidence detected across observation streams: {conflict_summary}. "
                "Highest credible severity is preserved without downgrade for public safety; "
                "immediate ground verification and field reconnaissance are recommended."
            )

        return (
            overall_threat,
            composite_index,
            hazard_eval,
            exposure_eval,
            consequence_eval,
            has_conflicts,
            uncertainty_qualification,
        )
