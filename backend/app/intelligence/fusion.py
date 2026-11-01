"""
backend/app/intelligence/fusion.py
Multimodal evidence fusion, cross-stream coherence evaluation, and conflict detection.
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.schemas import (
    ContextSummary,
    EvidenceCategory,
    EvidenceItem,
    EvidenceStatus,
    IncidentEvidenceState,
    VisualEvidenceState,
)

logger = logging.getLogger(__name__)


class FusionAnalysis(BaseModel):
    """Container for the fused multi-stream observation state."""

    model_config = ConfigDict(extra="forbid")

    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    missing_streams: List[str] = Field(default_factory=list)
    stale_streams: List[str] = Field(default_factory=list)
    conflicting_streams: List[str] = Field(default_factory=list)
    has_visual: bool = Field(default=False)
    has_environmental: bool = Field(default=False)
    has_geospatial: bool = Field(default=False)
    has_satellite: bool = Field(default=False)
    has_field_report: bool = Field(default=False)
    satellite_confidence: Optional[float] = Field(None)
    field_report_confirmed: Optional[bool] = Field(None)
    is_corroborated: bool = Field(
        default=False,
        description="True if physical incident evidence is corroborated across independent sensors or by verified ground personnel",
    )
    corroboration_sources: List[str] = Field(
        default_factory=list,
        description="List of independent streams confirming active incident presence",
    )
    active_evidence_state: IncidentEvidenceState = Field(default=IncidentEvidenceState.MISSING_EVIDENCE)
    active_incident_score: Optional[float] = Field(None)
    active_evidence_explanation: Optional[str] = Field(None)
    visual_evidence_state: VisualEvidenceState = Field(default=VisualEvidenceState.MISSING_EVIDENCE)
    visual_explanation: Optional[str] = Field(None)
    visual_fire_probability: Optional[float] = Field(None)
    visual_smoke_probability: Optional[float] = Field(None)
    environmental_fwi: Optional[float] = Field(None)
    environmental_danger_rating: Optional[str] = Field(None)
    temperature_c: Optional[float] = Field(None)
    relative_humidity_pct: Optional[float] = Field(None)
    precipitation_mm: Optional[float] = Field(None)
    fire_weather_score: Optional[float] = Field(None)
    fire_weather_level: Optional[str] = Field(None)
    fire_weather_explanation: Optional[str] = Field(None)
    context_summary: ContextSummary


class MultimodalFusionEngine:
    """
    Combines evidence streams, detects cross-modal contradictions,
    and structures unified context for risk evaluation.
    """

    @classmethod
    def fuse(
        cls,
        evidence_items: List[EvidenceItem],
        context_summary: ContextSummary,
    ) -> FusionAnalysis:
        """
        Processes evidence items and context summary into a consolidated FusionAnalysis.
        Separates active physical incident evidence from fire weather danger.
        """
        missing_streams: List[str] = []
        stale_streams: List[str] = []
        conflicting_streams: List[str] = []

        cv_item: Optional[EvidenceItem] = None
        env_item: Optional[EvidenceItem] = None
        geo_item: Optional[EvidenceItem] = None
        sat_item: Optional[EvidenceItem] = None
        fld_item: Optional[EvidenceItem] = None

        for item in evidence_items:
            cat = item.category
            if cat == EvidenceCategory.COMPUTER_VISION:
                cv_item = item
            elif cat == EvidenceCategory.ENVIRONMENTAL:
                env_item = item
            elif cat == EvidenceCategory.GEOSPATIAL_CONTEXT:
                geo_item = item
            elif cat == EvidenceCategory.SATELLITE_OBSERVATION:
                sat_item = item
            elif cat == EvidenceCategory.FIELD_REPORT:
                fld_item = item

        # 1. Computer Vision modality tracking
        has_visual = False
        vis_fire: Optional[float] = None
        vis_smoke: Optional[float] = None

        if cv_item is None or cv_item.status == EvidenceStatus.UNAVAILABLE:
            missing_streams.append("computer_vision_imagery")
        else:
            has_visual = True
            if cv_item.status == EvidenceStatus.STALE:
                stale_streams.append("computer_vision_imagery")
            if isinstance(cv_item.raw_value, dict):
                vis_fire = cv_item.raw_value.get("fire")
                vis_smoke = cv_item.raw_value.get("smoke")

        # 2. Environmental modality tracking
        has_env = False
        env_fwi: Optional[float] = None
        env_rating: Optional[str] = None
        temp_c: Optional[float] = None
        rh_pct: Optional[float] = None
        rain_mm: Optional[float] = None

        if env_item is None or env_item.status == EvidenceStatus.UNAVAILABLE:
            missing_streams.append("environmental_weather_and_fwi")
        else:
            has_env = True
            if env_item.status == EvidenceStatus.STALE:
                stale_streams.append("environmental_weather_and_fwi")
            if isinstance(env_item.raw_value, dict):
                temp_c = env_item.raw_value.get("temperature_c")
                rh_pct = env_item.raw_value.get("relative_humidity_pct")
                rain_mm = env_item.raw_value.get("precipitation_mm")
                fwi_data = env_item.raw_value.get("fwi_indices", {})
                if isinstance(fwi_data, dict):
                    env_fwi = fwi_data.get("fire_weather_index_fwi")
                    env_rating = fwi_data.get("danger_rating")

        # 3. Geospatial context modality tracking
        has_geo = geo_item is not None and geo_item.status != EvidenceStatus.UNAVAILABLE
        if not has_geo:
            missing_streams.append("geospatial_exposure_catalog")

        # 4. Satellite Observation modality tracking
        has_satellite = False
        sat_confidence: Optional[float] = None
        if sat_item is not None and sat_item.status != EvidenceStatus.UNAVAILABLE:
            has_satellite = True
            sat_confidence = sat_item.confidence
            if sat_item.status == EvidenceStatus.STALE:
                stale_streams.append("satellite_observation")

        # 5. Field Report modality tracking
        has_field_report = False
        field_confirmed: Optional[bool] = None
        if fld_item is not None and fld_item.status != EvidenceStatus.UNAVAILABLE:
            has_field_report = True
            if isinstance(fld_item.raw_value, dict):
                field_confirmed = fld_item.raw_value.get("is_confirmed", True)
            else:
                field_confirmed = True
            if fld_item.status == EvidenceStatus.STALE:
                stale_streams.append("field_report")

        # 6. Epistemic classification of active physical incident evidence
        # Independent corroboration requires either:
        #  a) Explicit verified field confirmation (human ground truth on-scene), or
        #  b) Concordant independent physical detections across distinct sensor streams
        #     (e.g., optical camera detection + spaceborne satellite thermal radiometer anomaly).
        active_state = IncidentEvidenceState.MISSING_EVIDENCE
        active_score: Optional[float] = None
        active_exp = "No physical incident imagery or field reports provided; active incident status cannot be confirmed or refuted."
        is_corroborated = False
        corroboration_sources: List[str] = []

        has_vis_fire = has_visual and ((vis_fire or 0.0) >= 0.50)
        has_vis_smoke = has_visual and ((vis_smoke or 0.0) >= 0.50)
        has_sat_thermal = has_satellite and (sat_confidence is None or sat_confidence >= 0.50)
        has_fld_conf = has_field_report and bool(field_confirmed)

        if has_fld_conf:
            is_corroborated = True
            corroboration_sources.append("field_report")
            if has_vis_fire or has_vis_smoke:
                corroboration_sources.append("computer_vision")
            if has_sat_thermal:
                corroboration_sources.append("satellite_observation")
            active_state = IncidentEvidenceState.FIELD_CONFIRMED
            active_score = 95.0
            active_exp = "Ground emergency personnel confirmed active wildfire incident on-scene."
        elif (has_vis_fire or has_vis_smoke) and has_sat_thermal:
            is_corroborated = True
            corroboration_sources = ["computer_vision", "satellite_observation"]
            active_state = (
                IncidentEvidenceState.SUPPORTING_FIRE
                if has_vis_fire
                else IncidentEvidenceState.SUPPORTING_SMOKE
            )
            score_base = (vis_fire or 0.0) * 100.0 if has_vis_fire else (vis_smoke or 0.0) * 75.0
            active_score = max(min(100.0, score_base), 85.0)
            active_exp = (
                "Independent physical corroboration established: visual camera detection corroborated by "
                "spaceborne satellite thermal radiometer anomaly."
            )
        elif has_sat_thermal:
            # Satellite thermal anomaly alone without ground or camera corroboration
            is_corroborated = False
            corroboration_sources = ["satellite_observation"]
            active_state = IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY
            active_score = 85.0
            conf_str = f" (confidence={sat_confidence*100.0:.0f}%)" if sat_confidence else ""
            active_exp = (
                f"Satellite radiometer detected significant thermal radiative anomaly{conf_str} "
                "(uncorroborated single-sensor observation)."
            )
        elif has_visual:
            p_fire = vis_fire or 0.0
            p_smoke = vis_smoke or 0.0
            raw_dict = cv_item.raw_value if (cv_item and isinstance(cv_item.raw_value, dict)) else {}
            p_neutral = raw_dict.get("neutral", 0.0)

            top_prob = max(p_fire, p_smoke, p_neutral)
            if top_prob < 0.45 or (abs(p_fire - p_neutral) < 0.10 and p_fire > 0.30):
                active_state = IncidentEvidenceState.UNCERTAIN_OR_CONFLICTING
                active_score = min(100.0, (p_fire * 100.0) + (p_smoke * 50.0))
                active_exp = (
                    f"Visual classifier probabilities are diffuse/uncertain (fire={p_fire:.2f}, smoke={p_smoke:.2f}, neutral={p_neutral:.2f}). "
                    "Features do not provide decisive visual evidence."
                )
            elif p_fire >= 0.50:
                active_state = IncidentEvidenceState.SUPPORTING_FIRE
                active_score = min(100.0, p_fire * 100.0)
                active_exp = (
                    f"Visual model detected active flame features with {p_fire * 100.0:.1f}% confidence "
                    "(uncorroborated single-image prediction; consistent with suspected fire)."
                )
            elif p_smoke >= 0.50:
                active_state = IncidentEvidenceState.SUPPORTING_SMOKE
                active_score = min(100.0, p_smoke * 75.0)
                active_exp = (
                    f"Visual model detected smoke plume signatures with {p_smoke * 100.0:.1f}% confidence "
                    "(uncorroborated single-image prediction; consistent with suspected fire/smoke)."
                )
            else:
                active_state = IncidentEvidenceState.NO_SUPPORTING_EVIDENCE
                active_score = 0.0
                active_exp = (
                    "Submitted imagery does not exhibit salient flame or smoke features in its field of view (no_supporting_visual_evidence). "
                    "Note: Absence of visual evidence in this image does NOT prove that no wildfire exists in the surrounding area due to potential "
                    "occlusions, smoke dispersion, or camera viewing orientation."
                )

        # 7. Independent Fire Weather Danger Evaluation
        fire_weather_score: Optional[float] = None
        fire_weather_level: Optional[str] = None
        fire_weather_exp: Optional[str] = None

        if has_env:
            if env_fwi is not None:
                fire_weather_score = max(0.0, min(100.0, env_fwi * 2.5))
                fire_weather_level = env_rating or "Unrated"
                fire_weather_exp = (
                    f"Canadian FWI index is {env_fwi:.1f} ({fire_weather_level} danger rating); "
                    "instantaneous atmospheric combustibility indicator."
                )
            elif temp_c is not None and rh_pct is not None:
                if temp_c > 35.0 and rh_pct < 20.0:
                    fire_weather_score = 80.0
                    fire_weather_level = "VERY_HIGH"
                elif temp_c > 30.0 and rh_pct < 35.0:
                    fire_weather_score = 55.0
                    fire_weather_level = "HIGH"
                elif temp_c > 25.0 and rh_pct < 50.0:
                    fire_weather_score = 35.0
                    fire_weather_level = "MODERATE"
                else:
                    fire_weather_score = 15.0
                    fire_weather_level = "LOW"
                fire_weather_exp = (
                    f"Atmospheric weather observations indicate {fire_weather_level} combustibility "
                    f"({temp_c:.1f}°C, {rh_pct:.0f}% RH)."
                )
            else:
                fire_weather_exp = "Meteorological parameters insufficient for fire weather rating."
        else:
            fire_weather_exp = "Atmospheric weather data unavailable."

        # 8. Cross-modal conflict evaluation
        if (has_visual or has_satellite or has_field_report) and has_env:
            # Conflict A: Active flame detected while heavy precipitation (> 10mm)
            is_fire_detected = (
                (vis_fire is not None and vis_fire > 0.80)
                or active_state in (IncidentEvidenceState.SUPPORTING_FIRE, IncidentEvidenceState.FIELD_CONFIRMED)
            )
            if is_fire_detected and rain_mm is not None and rain_mm > 10.0:
                conflicting_streams.append(
                    f"Visual/physical evidence indicates active flames, but current meteorological data records substantial rainfall ({rain_mm:.1f} mm)."
                )

            # Conflict B: Active flames in freezing conditions (< -5 C) with high humidity (> 90%)
            if (
                is_fire_detected
                and temp_c is not None
                and temp_c < -5.0
                and rh_pct is not None
                and rh_pct > 90.0
            ):
                conflicting_streams.append(
                    f"Physical evidence indicates active flames under sub-zero, high-humidity atmospheric conditions ({temp_c:.1f}°C, {rh_pct:.0f}% RH)."
                )

            # Conflict C: Extreme FWI fire danger (> 40.0) but visual model is overwhelmingly neutral (> 0.95) with 0 smoke
            if (
                env_fwi is not None
                and env_fwi > 40.0
                and vis_fire is not None
                and vis_fire < 0.05
                and vis_smoke is not None
                and vis_smoke < 0.05
            ):
                conflicting_streams.append(
                    f"Atmospheric fire danger is Extreme (FWI={env_fwi:.1f}), yet submitted imagery shows no flame or smoke features (neutral p={1.0 - (vis_fire or 0.0) - (vis_smoke or 0.0):.2f})."
                )

        return FusionAnalysis(
            evidence_items=evidence_items,
            missing_streams=missing_streams,
            stale_streams=stale_streams,
            conflicting_streams=conflicting_streams,
            has_visual=has_visual,
            has_environmental=has_env,
            has_geospatial=has_geo,
            has_satellite=has_satellite,
            has_field_report=has_field_report,
            satellite_confidence=sat_confidence,
            field_report_confirmed=field_confirmed,
            is_corroborated=is_corroborated,
            corroboration_sources=corroboration_sources,
            active_evidence_state=active_state,
            active_incident_score=active_score,
            active_evidence_explanation=active_exp,
            visual_evidence_state=active_state,
            visual_explanation=active_exp,
            visual_fire_probability=vis_fire,
            visual_smoke_probability=vis_smoke,
            environmental_fwi=env_fwi,
            environmental_danger_rating=env_rating,
            temperature_c=temp_c,
            relative_humidity_pct=rh_pct,
            precipitation_mm=rain_mm,
            fire_weather_score=fire_weather_score,
            fire_weather_level=fire_weather_level,
            fire_weather_explanation=fire_weather_exp,
            context_summary=context_summary,
        )
