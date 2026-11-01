"""
backend/app/intelligence/explanations.py
Explainable intelligence generation for multimodal incident assessments.
Provides transparent plain-English rationales, contributing/mitigating factor breakdowns,
and scientific caveat catalogs.
"""

from typing import List, Optional
from app.intelligence.fusion import FusionAnalysis
from app.intelligence.schemas import DisasterAssessmentLevel
from app.schemas.incident import DisasterType


class ExplanationGenerator:
    """
    Constructs explainable, audit-ready natural language breakdowns for multimodal assessments.
    """

    @classmethod
    def generate_rationale(
        cls,
        disaster_type: DisasterType,
        level: DisasterAssessmentLevel,
        risk_index: Optional[float],
        fusion: FusionAnalysis,
    ) -> str:
        """
        Synthesizes assessment findings into a concise, unambiguous executive rationale.
        """
        if disaster_type != DisasterType.WILDFIRE:
            return (
                f"Assessment for {disaster_type.value.capitalize()} yielded INSUFFICIENT_DATA because "
                f"calibrated predictive models and hazard-specific risk engines are not implemented for this category in Milestone 11."
            )

        if level == DisasterAssessmentLevel.INSUFFICIENT_DATA:
            missing_str = ", ".join(fusion.missing_streams) if fusion.missing_streams else "all primary modalities"
            return (
                f"Multimodal assessment could not be determined (INSUFFICIENT_DATA) due to missing critical observation streams: {missing_str}."
            )

        # Wildfire rationale
        idx_str = f"{risk_index:.1f}" if risk_index is not None else "N/A"
        elements = []

        if fusion.has_visual and fusion.visual_fire_probability is not None:
            if fusion.visual_fire_probability >= 0.70:
                elements.append(f"high computer vision flame detection (p={fusion.visual_fire_probability:.2f})")
            elif fusion.visual_smoke_probability and fusion.visual_smoke_probability >= 0.60:
                elements.append(f"significant smoke plume detection (p={fusion.visual_smoke_probability:.2f})")
            elif fusion.visual_fire_probability < 0.20:
                elements.append("neutral visual classification")

        if fusion.has_environmental and fusion.environmental_danger_rating:
            elements.append(f"{fusion.environmental_danger_rating.lower()} fire weather index conditions (FWI={fusion.environmental_fwi})")

        context = fusion.context_summary
        if context.settlements_found > 0 and context.closest_settlement_distance_meters is not None:
            if context.closest_settlement_distance_meters < 2000.0:
                elements.append(
                    f"human settlement '{context.closest_settlement_name or 'unnamed'}' within {context.closest_settlement_distance_meters:.0f}m"
                )

        summary_text = "; ".join(elements) if elements else "fused multi-factor evaluation"
        return f"Assessed at {level.value} threat tier (heuristic risk index {idx_str}/100.0) driven by {summary_text}."

    @classmethod
    def generate_contributing_factors(
        cls,
        disaster_type: DisasterType,
        fusion: FusionAnalysis,
    ) -> List[str]:
        """
        Enumerates all factors that elevated concern or threat level.
        """
        factors: List[str] = []

        if disaster_type != DisasterType.WILDFIRE:
            if fusion.context_summary.total_features_evaluated > 0:
                factors.append(
                    f"Identified {fusion.context_summary.total_features_evaluated} geographic features within search perimeter."
                )
            return factors

        # 1. Visual factors
        if fusion.has_visual:
            p_fire = fusion.visual_fire_probability or 0.0
            p_smoke = fusion.visual_smoke_probability or 0.0
            if p_fire >= 0.50:
                factors.append(
                    f"BaselineCNN detected active fire patterns with {p_fire * 100.0:.1f}% confidence."
                )
            if p_smoke >= 0.50:
                factors.append(
                    f"BaselineCNN detected atmospheric smoke plumes with {p_smoke * 100.0:.1f}% confidence."
                )

        # 2. Environmental factors
        if fusion.has_environmental:
            fwi = fusion.environmental_fwi
            rating = fusion.environmental_danger_rating
            if fwi is not None and fwi >= 11.2:
                factors.append(
                    f"Canadian Fire Weather Index is {fwi:.1f} ({rating} danger rating), indicating elevated fire propagation potential."
                )
            if fusion.temperature_c is not None and fusion.temperature_c >= 30.0:
                factors.append(
                    f"Elevated ambient temperature ({fusion.temperature_c:.1f}°C) accelerates combustible fuel desiccation."
                )
            if fusion.relative_humidity_pct is not None and fusion.relative_humidity_pct <= 30.0:
                factors.append(
                    f"Low relative humidity ({fusion.relative_humidity_pct:.0f}%) promotes rapid fine fuel ignition."
                )

        # 3. Spatial context factors
        context = fusion.context_summary
        if context.settlements_found > 0:
            dist_str = (
                f"{context.closest_settlement_distance_meters:.0f}m"
                if context.closest_settlement_distance_meters
                else "nearby"
            )
            factors.append(
                f"Proximity to {context.settlements_found} human settlement(s); closest is {dist_str} away."
            )

        if context.hospitals_found > 0:
            dist_str = (
                f"{context.closest_hospital_distance_meters:.0f}m"
                if context.closest_hospital_distance_meters
                else "nearby"
            )
            factors.append(
                f"Identified {context.hospitals_found} vulnerable healthcare facility/facilities within search zone (closest: {dist_str})."
            )

        return factors

    @classmethod
    def generate_mitigating_factors(
        cls,
        disaster_type: DisasterType,
        fusion: FusionAnalysis,
    ) -> List[str]:
        """
        Enumerates all factors that attenuated or reduced concern.
        """
        mitigations: List[str] = []

        if disaster_type != DisasterType.WILDFIRE:
            return mitigations

        # Visual mitigations
        if fusion.has_visual:
            p_fire = fusion.visual_fire_probability or 0.0
            p_smoke = fusion.visual_smoke_probability or 0.0
            if p_fire < 0.15 and p_smoke < 0.20:
                mitigations.append(
                    "Submitted imagery does not exhibit salient visual signatures of active flame or smoke."
                )

        # Environmental mitigations
        if fusion.has_environmental:
            fwi = fusion.environmental_fwi
            if fwi is not None and fwi < 5.2:
                mitigations.append(
                    f"Fire Weather Index is Low (FWI={fwi:.1f}), indicating low fuel combustibility and low spread potential."
                )
            if fusion.precipitation_mm is not None and fusion.precipitation_mm > 1.0:
                mitigations.append(
                    f"Recorded precipitation of {fusion.precipitation_mm:.1f} mm dampens surface fuel moisture."
                )
            if fusion.relative_humidity_pct is not None and fusion.relative_humidity_pct >= 65.0:
                mitigations.append(
                    f"High relative humidity ({fusion.relative_humidity_pct:.0f}%) suppresses fire ignition and ember transport."
                )

        # Spatial mitigations
        context = fusion.context_summary
        if context.water_bodies_found > 0:
            mitigations.append(
                f"Identified {context.water_bodies_found} water body/river feature(s) capable of serving as natural firebreaks or suppression water points."
            )

        if context.fire_stations_found > 0:
            dist_str = (
                f"{context.closest_fire_station_distance_meters:.0f}m"
                if context.closest_fire_station_distance_meters
                else "nearby"
            )
            mitigations.append(
                f"{context.fire_stations_found} fire station(s) situated within reach (closest: {dist_str})."
            )

        return mitigations

    @classmethod
    def generate_caveats(
        cls,
        disaster_type: DisasterType,
        fusion: FusionAnalysis,
    ) -> List[str]:
        """
        Compiles mandatory scientific caveats, calibration notes, and assumptions.
        """
        caveats: List[str] = [
            "Heuristic risk index is a rule-based composite indicator [0.0 - 100.0] and MUST NOT be interpreted as an empirical probability.",
            "Proximity to features reflects static Euclidean/geodesic distance and does NOT model dynamic wildfire rate of spread or ember spotting.",
        ]

        if disaster_type == DisasterType.WILDFIRE:
            caveats.append(
                "Canadian Forest Fire Weather Index (CFS-FWI) indices applied as an instantaneous combustibility indicator; not calibrated for Indian fuel complexes and lacks continuous multi-day moisture history tracking."
            )
            caveats.append(
                "Computer vision classification evaluates submitted 2D perspective only; occlusions, terrain folds, or smoke masking can degrade detection."
            )
            caveats.append(
                "Computer vision decision threshold (0.50) is an uncalibrated engineering heuristic, not an empirical Bayes-optimal risk boundary."
            )
        elif disaster_type in (DisasterType.FLOOD, DisasterType.EARTHQUAKE):
            caveats.append(
                f"Hydraulic, geotechnical, or ground-motion models for {disaster_type.value} are NOT integrated in Milestone 11."
            )

        if len(fusion.conflicting_streams) > 0:
            for conflict in fusion.conflicting_streams:
                caveats.append(f"Cross-modal contradiction: {conflict}")

        if "computer_vision_imagery" in fusion.missing_streams:
            caveats.append("No visual imagery was provided; analysis relies strictly on atmospheric and spatial proxies.")

        if "environmental_weather_and_fwi" in fusion.missing_streams:
            caveats.append("Atmospheric data was unavailable; assessment lacks weather and fuel dryness factors.")

        for note in fusion.context_summary.spatial_coverage_notes:
            if "incomplete" in note.lower() or "partial" in note.lower() or "unavailable" in note.lower():
                caveats.append(note)

        return caveats
