"""
backend/app/agents/nodes/risk_assessment.py
Risk Assessment Agent node for SCOUT LangGraph Multi-Agent Disaster Response Workflow (Milestone 12.3).
Synthesizes perception outputs (Intelligence, Weather, Geospatial) into an explainable,
evidence-grounded 5-dimensional disaster risk assessment without fabricating data or invoking LLMs.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from app.agents.schemas import (
    AgentExecutionRecord,
    RiskAssessmentAgentOutput,
    RiskAssessmentStatus,
    WorkflowError,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState

logger = logging.getLogger(__name__)


def risk_assessment_agent_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Agent 4: Risk Assessment Agent Node
    Responsibilities:
    - Consumes the already collected outputs from Intelligence Agent, Weather Agent, and Geospatial Agent.
    - Strictly avoids rerunning CV models, querying weather providers, or calling PostGIS directly.
    - Evaluates five distinct dimensions:
      1. Incident evidence & status (CONFIRMED, SUSPECTED, UNCONFIRMED, INSUFFICIENT_EVIDENCE, UNAVAILABLE)
      2. Incident severity (preserves existing severity, never invents levels when unassessed)
      3. Fire-weather danger (decoupled from active incident confirmation)
      4. Geographic exposure (distinguishes verified vs unverified catalog gaps vs unavailable)
      5. Potential consequences (consequence tier conditional on active hazard intersecting verified exposure)
    - Computes a transparent, bounded heuristic risk index with documented weights and explicit inputs.
    - Generates evidence-grounded rationale, key risk drivers, mitigating factors, and uncertainty caveats.
    - Concludes M12.3 workflow execution: sets status to COMPLETED (or FAILED if unrecoverable error).
    """
    start_time = datetime.now(timezone.utc)
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # 1. Ingest upstream perception outputs
    intel = state.get("intelligence_output") or {}
    weather = state.get("weather_output") or {}
    geo = state.get("geospatial_output") or {}

    # Check for complete absence of perception outputs
    if not intel and not weather and not geo:
        err = WorkflowError(
            code="MISSING_PERCEPTION_OUTPUTS",
            message="Cannot perform risk assessment: all perception agent outputs (intelligence, weather, geospatial) are absent.",
            stage=WorkflowStage.RISK_ASSESSMENT.value,
            agent="risk_assessment_agent",
            recoverable=False,
        ).model_dump(mode="json")
        errors.append(err)

        unavailable_out = RiskAssessmentAgentOutput(
            assessment_status=RiskAssessmentStatus.FAILED.value,
            incident_status="UNAVAILABLE",
            incident_severity=None,
            fire_weather_danger="UNAVAILABLE",
            geographic_exposure_status="UNAVAILABLE",
            potential_consequences_status="UNASSESSED_INSUFFICIENT_DATA",
            overall_threat_level="INSUFFICIENT_DATA",
            heuristic_risk_index=None,
            hazard_summary="Hazard assessment unavailable: intelligence agent output missing.",
            exposure_summary="Exposure assessment unavailable: geospatial agent output missing.",
            consequence_summary="Consequence assessment unavailable: all perception inputs missing.",
            fire_weather_summary="Fire weather assessment unavailable: weather agent output missing.",
            supporting_evidence=[],
            missing_evidence=["intelligence_output", "weather_output", "geospatial_output"],
            conflicting_evidence=[],
            uncertainty_qualification="Assessment failed: required perception agent outputs are missing.",
            assessment_rationale="Risk synthesis cannot proceed because no perception data was received from upstream agents.",
            key_risk_drivers=[],
            mitigating_factors=[],
            source_agent_provenance={"agent": "risk_assessment_agent", "status": "failed"},
        ).model_dump(mode="json")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        now_iso = end_time.isoformat()

        rec = AgentExecutionRecord(
            agent_name="risk_assessment_agent",
            stage=WorkflowStage.RISK_ASSESSMENT.value,
            status="failed",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details="Risk assessment failed: missing all perception agent outputs.",
        ).model_dump(mode="json")

        return {
            "status": WorkflowStatus.FAILED.value,
            "stage": WorkflowStage.TERMINATED_WITH_ERROR.value,
            "risk_assessment_output": unavailable_out,
            "errors": errors,
            "warnings": warnings,
            "execution_records": [rec],
            "updated_at": now_iso,
            "completed_at": now_iso,
        }

    # -------------------------------------------------------------------------
    # Dimension A: Incident Evidence & Status
    # -------------------------------------------------------------------------
    inc_status = intel.get("incident_status") or "UNAVAILABLE"
    active_evidence = intel.get("active_evidence_state") or "unavailable"
    visual_summary = intel.get("visual_evidence_summary")

    # -------------------------------------------------------------------------
    # Dimension B: Incident Severity
    # -------------------------------------------------------------------------
    inc_severity = intel.get("incident_severity")
    # If missing, stays None. Never invent levels.

    # -------------------------------------------------------------------------
    # Dimension C: Fire-Weather Danger
    # -------------------------------------------------------------------------
    wx_danger = weather.get("danger_rating") or "UNAVAILABLE"
    fwi = weather.get("fwi")
    is_wx_experimental = weather.get("is_experimental", True)
    missing_wx_params = list(weather.get("missing_parameters") or [])
    stale_wx = list(weather.get("stale_observations") or [])
    wx_explanation = weather.get("fire_weather_explanation") or "No atmospheric data available."

    # -------------------------------------------------------------------------
    # Dimension D: Geographic Exposure
    # -------------------------------------------------------------------------
    geo_level = geo.get("exposure_level") or "UNKNOWN"
    geo_score = geo.get("exposure_score")
    is_geo_verified = bool(geo.get("is_verified", False))
    settlements = geo.get("settlements_within_radius", 0)
    closest_dist = geo.get("closest_settlement_distance_meters")
    closest_name = geo.get("closest_settlement_name")
    hospitals = geo.get("hospitals_within_radius", 0)
    fire_stations = geo.get("fire_stations_within_radius", 0)
    corridors = geo.get("transport_corridors_count", 0)

    # Classify geographic exposure status
    if not geo or geo_level == "UNAVAILABLE":
        geo_exposure_status = "UNAVAILABLE"
    elif not is_geo_verified or "UNVERIFIED" in geo_level or geo_score is None:
        geo_exposure_status = "UNVERIFIED_CATALOG_GAP"
    elif geo_level == "CRITICAL" or (hospitals > 0 and closest_dist and closest_dist <= 2000):
        geo_exposure_status = "CRITICAL" if geo_level == "CRITICAL" else "HIGH"
    elif geo_level in ("HIGH", "MODERATE") or settlements > 0:
        geo_exposure_status = geo_level if geo_level in ("HIGH", "MODERATE") else "MODERATE"
    else:
        geo_exposure_status = "LOW"

    # -------------------------------------------------------------------------
    # Dimension E: Potential Consequences
    # -------------------------------------------------------------------------
    if inc_status in ("UNCONFIRMED", "no_supporting_visual_evidence") or active_evidence in (
        "no_supporting_visual_evidence",
        "neutral",
        "unconfirmed",
    ):
        potential_consequences_status = "NEGLIGIBLE"
        consequence_summary = (
            "Potential active impact is negligible: no direct visual or field evidence indicates an active fire front. "
            "Exposed assets remain at baseline vulnerability."
        )
    elif inc_status in ("CONFIRMED", "SUSPECTED"):
        if geo_exposure_status in ("UNVERIFIED_CATALOG_GAP", "UNAVAILABLE"):
            potential_consequences_status = "UNASSESSED_EXPOSURE_UNVERIFIED"
            consequence_summary = (
                f"Potential consequences of {inc_status.lower()} incident cannot be verified: "
                "local geographic catalog lacks verified infrastructure or population features."
            )
        elif geo_exposure_status in ("CRITICAL", "HIGH"):
            potential_consequences_status = (
                "CRITICAL"
                if (inc_status == "CONFIRMED" and inc_severity in ("HIGH", "CRITICAL"))
                else "HIGH"
            )
            consequence_summary = (
                f"High-consequence impact potential: {inc_status.lower()} incident front intersects verified critical "
                f"infrastructure ({hospitals} hospital(s), {settlements} settlement(s) within search radius)."
            )
        elif geo_exposure_status == "MODERATE":
            potential_consequences_status = "HIGH" if inc_status == "CONFIRMED" else "MODERATE"
            consequence_summary = (
                f"Moderate-to-high consequence potential: {inc_status.lower()} fire front intersects verified populated area "
                f"(closest settlement {closest_name or 'unnamed'} at {closest_dist:.0f}m)."
                if closest_dist
                else "Moderate consequence potential."
            )
        else:  # LOW
            potential_consequences_status = "LOW"
            consequence_summary = (
                f"Low consequence potential: {inc_status.lower()} incident in verified remote area with low settlement density."
            )
    else:  # INSUFFICIENT_EVIDENCE or UNAVAILABLE
        potential_consequences_status = "UNASSESSED_INSUFFICIENT_DATA"
        consequence_summary = "Potential consequences cannot be assessed: incident physical presence is unverified."

    # -------------------------------------------------------------------------
    # Assessment Status & Evidence Gaps
    # -------------------------------------------------------------------------
    missing_ev: List[str] = []
    if not intel or inc_status == "UNAVAILABLE":
        missing_ev.append("intelligence_output")
    if not weather or wx_danger == "UNAVAILABLE" or missing_wx_params:
        missing_ev.extend([f"weather_{p}" for p in missing_wx_params] or ["weather_data"])
    if not geo or geo_exposure_status in ("UNAVAILABLE", "UNVERIFIED_CATALOG_GAP"):
        missing_ev.append("verified_geospatial_exposure")

    conflicting_ev = list(intel.get("conflicting_streams") or [])
    if inc_status in ("CONFIRMED", "SUSPECTED") and wx_danger in ("LOW", "VERY_LOW"):
        conflicting_ev.append(
            f"Active incident ({inc_status}) reported despite low fire-weather danger ({wx_danger}"
            + (f", FWI={fwi:.1f}" if fwi is not None else "")
            + ")."
        )
    elif inc_status in ("CONFIRMED", "SUSPECTED") and weather.get("precipitation_mm", 0) > 5.0:
        conflicting_ev.append(
            f"Active incident ({inc_status}) reported during significant precipitation ({weather.get('precipitation_mm')}mm)."
        )

    # Assessment status
    if not intel or inc_status == "UNAVAILABLE":
        assessment_status = RiskAssessmentStatus.PARTIAL.value
        warnings.append("Intelligence assessment is unavailable; risk synthesis performed partially.")
    elif inc_status == "INSUFFICIENT_EVIDENCE":
        assessment_status = RiskAssessmentStatus.INSUFFICIENT_EVIDENCE.value
    elif missing_ev or conflicting_ev:
        assessment_status = RiskAssessmentStatus.PARTIAL.value
    else:
        assessment_status = RiskAssessmentStatus.COMPLETE.value

    # -------------------------------------------------------------------------
    # Overall Threat Level Qualitative Classification & Rules
    # -------------------------------------------------------------------------
    key_drivers: List[str] = []
    mitigating: List[str] = []

    # Case 1: Extreme weather, no active fire evidence
    if inc_status in ("UNCONFIRMED", "INSUFFICIENT_EVIDENCE") and wx_danger in ("EXTREME", "VERY_HIGH"):
        overall_threat = "ELEVATED_PREPAREDNESS"
        key_drivers.append(f"Extreme atmospheric fire-weather danger ({wx_danger}) promotes rapid ignition and spread.")
        mitigating.append("No active flame or smoke front identified in submitted observations.")
        rationale = (
            f"Extreme atmospheric fire-weather conditions ({wx_danger}"
            + (f", FWI={fwi:.1f}" if fwi is not None else "")
            + ") create extreme fire-weather danger without confirmed active fire. "
            "Direct observations confirm NO active wildfire. "
            "Threat classification represents elevated preparedness and pre-positioning concern, "
            "strictly decoupled from active incident confirmation."
        )

    # Case 2: Suspected fire, high exposure
    elif inc_status == "SUSPECTED" and geo_exposure_status in ("CRITICAL", "HIGH", "MODERATE"):
        overall_threat = "POTENTIAL_THREAT"
        key_drivers.append("Visual or remote sensing observations indicate suspected fire front.")
        key_drivers.append(f"Verified infrastructure in exposure zone ({geo_exposure_status}).")
        mitigating.append("Incident confirmation remains uncorroborated; field verification required.")
        rationale = (
            f"Suspected wildfire observation coincides with populated infrastructure ({geo_exposure_status}). "
            f"Atmospheric fire weather danger is {wx_danger}. Threat tier is POTENTIAL_THREAT "
            "demanding urgent ground reconnaissance without premature declaration of a confirmed disaster."
        )

    # Case 3: Confirmed fire, high exposure
    elif inc_status == "CONFIRMED" and geo_exposure_status in ("CRITICAL", "HIGH"):
        overall_threat = "CRITICAL_EMERGENCY"
        key_drivers.append("Confirmed active wildfire presence on-scene or cross-sensor verified.")
        key_drivers.append(f"High-density exposure zone: hospitals/settlements within {closest_dist or 2000:.0f}m.")
        if wx_danger in ("HIGH", "VERY_HIGH", "EXTREME"):
            key_drivers.append(f"Adverse fire weather ({wx_danger}) accelerating threat.")
        rationale = (
            f"Active confirmed wildfire incident threatens verified high-value infrastructure and settlements "
            f"(geographic exposure status: {geo_exposure_status}). Fire weather danger is {wx_danger}"
            + (f" (FWI={fwi:.1f})" if fwi is not None else "")
            + f". Severity rated {inc_severity or 'unassessed'}, warranting immediate tactical command response."
        )

    # Case 4: Confirmed fire, low exposure or unverified exposure
    elif inc_status == "CONFIRMED":
        overall_threat = "ACTIVE_THREAT"
        key_drivers.append(f"Confirmed active wildfire front (severity={inc_severity or 'unassessed'}).")
        if geo_exposure_status == "UNVERIFIED_CATALOG_GAP":
            mitigating.append("Local geographic catalog has no verified features; real-world exposure unassessed.")
        else:
            mitigating.append(f"Geographic exposure is {geo_exposure_status}.")
        rationale = (
            f"Active confirmed wildfire with {geo_exposure_status} exposure context. Active containment required "
            "while verifying surrounding infrastructure completeness."
        )

    # Case 5 & 8: Insufficient intelligence or unconfirmed without extreme weather
    elif inc_status == "UNCONFIRMED":
        overall_threat = "LOW_CONCERN"
        mitigating.append("Observations indicate absence of active flame or smoke signatures in inspected view.")
        rationale = (
            "Submitted observations indicate no active fire evidence. Weather and exposure parameters remain "
            "at baseline monitoring levels."
        )
    else:  # INSUFFICIENT_EVIDENCE or UNAVAILABLE
        overall_threat = "INSUFFICIENT_DATA"
        rationale = (
            "Observation data is insufficient to establish active fire presence or evaluate consequence risk. "
            "Additional sensory or field data required."
        )

    # Contextual mitigating factors
    if weather.get("precipitation_mm") and weather.get("precipitation_mm") > 0.0:
        mitigating.append(f"Recent precipitation ({weather['precipitation_mm']:.1f} mm) dampens fuel combustibility.")
    if geo.get("water_bodies_count") and geo.get("water_bodies_count") > 0:
        mitigating.append(f"Natural water bodies ({geo['water_bodies_count']}) may serve as firebreaks.")

    # -------------------------------------------------------------------------
    # Heuristic Risk Index Computation [0.0 - 100.0]
    # -------------------------------------------------------------------------
    h_comp: Optional[float] = None
    if inc_status == "CONFIRMED":
        if inc_severity == "CRITICAL":
            h_comp = 95.0
        elif inc_severity == "HIGH":
            h_comp = 80.0
        elif inc_severity == "MODERATE":
            h_comp = 60.0
        elif inc_severity == "LOW":
            h_comp = 40.0
        else:
            h_comp = 75.0
    elif inc_status == "SUSPECTED":
        if inc_severity == "CRITICAL":
            h_comp = 65.0  # Capped at HIGH per epistemic rules
        elif inc_severity == "HIGH":
            h_comp = 65.0
        elif inc_severity == "MODERATE":
            h_comp = 50.0
        elif inc_severity == "LOW":
            h_comp = 35.0
        else:
            h_comp = 50.0
    elif inc_status == "UNCONFIRMED":
        h_comp = 5.0
    else:
        h_comp = None

    w_comp: Optional[float] = None
    if fwi is not None:
        w_comp = min(100.0, max(0.0, fwi * 2.0))
    elif wx_danger == "EXTREME":
        w_comp = 90.0
    elif wx_danger == "VERY_HIGH":
        w_comp = 75.0
    elif wx_danger == "HIGH":
        w_comp = 60.0
    elif wx_danger == "MODERATE":
        w_comp = 40.0
    elif wx_danger == "LOW":
        w_comp = 20.0
    else:
        w_comp = None

    e_comp: Optional[float] = None
    if is_geo_verified and geo_score is not None:
        e_comp = float(geo_score)
    elif is_geo_verified:
        if geo_level == "CRITICAL":
            e_comp = 85.0
        elif geo_level == "HIGH":
            e_comp = 70.0
        elif geo_level == "MODERATE":
            e_comp = 50.0
        else:
            e_comp = 20.0
    else:
        e_comp = None

    heuristic_index: Optional[float] = None
    if h_comp is not None:
        if h_comp <= 5.0:
            # Active hazard is unconfirmed / zero: exposure cannot create active disaster!
            if w_comp is not None:
                heuristic_index = min(25.0, round(w_comp * 0.25, 1))
            else:
                heuristic_index = 5.0
        else:
            # Active hazard is present (CONFIRMED or SUSPECTED)
            if w_comp is not None and e_comp is not None:
                heuristic_index = round(0.50 * h_comp + 0.25 * w_comp + 0.25 * e_comp, 1)
            elif w_comp is not None:
                heuristic_index = round(0.65 * h_comp + 0.35 * w_comp, 1)
            elif e_comp is not None:
                heuristic_index = round(0.65 * h_comp + 0.35 * e_comp, 1)
            else:
                heuristic_index = round(h_comp, 1)
    elif w_comp is not None:
        # Physical hazard unassessed, but weather is available
        heuristic_index = min(30.0, round(w_comp * 0.30, 1))
    else:
        heuristic_index = None

    if heuristic_index is not None:
        heuristic_index = max(0.0, min(100.0, heuristic_index))

    # -------------------------------------------------------------------------
    # Uncertainty Qualification
    # -------------------------------------------------------------------------
    uncertainty_parts: List[str] = []
    if inc_status == "SUSPECTED":
        uncertainty_parts.append("Visual evidence is uncorroborated by field reports; incident status is SUSPECTED.")
    elif inc_status == "UNAVAILABLE":
        uncertainty_parts.append("Physical incident observation is unavailable.")
    if is_wx_experimental:
        uncertainty_parts.append("FWI calculation is an uninitialized instantaneous combustibility proxy.")
    if missing_wx_params or wx_danger == "UNAVAILABLE":
        uncertainty_parts.append(f"Meteorological weather observation data is missing or incomplete: {missing_wx_params or ['weather_data']}.")
    if stale_wx:
        uncertainty_parts.append("Atmospheric data exceeds freshness threshold (stale).")
    if geo_exposure_status == "UNVERIFIED_CATALOG_GAP":
        uncertainty_parts.append("Geographic exposure is UNVERIFIED (0 local features in catalog; absence of features is not zero exposure).")
    elif geo_exposure_status == "UNAVAILABLE":
        uncertainty_parts.append("Geospatial context is unavailable.")
    if conflicting_ev:
        uncertainty_parts.append(f"Conflicting evidence detected across perception streams: {conflicting_ev}.")

    uncertainty_qual = (
        "; ".join(uncertainty_parts)
        if uncertainty_parts
        else "All perception streams verified within standard calibration boundaries."
    )

    hazard_summary = (
        f"Incident status is {inc_status} with active evidence classification '{active_evidence}'"
        + (f" (severity={inc_severity})" if inc_severity else " (severity unassessed)")
        + f". {visual_summary or ''}"
    ).strip()

    if geo_exposure_status == "UNVERIFIED_CATALOG_GAP":
        exposure_summary = (
            f"Geographic exposure status is UNVERIFIED_CATALOG_GAP. "
            f"Evaluated {settlements} settlement(s), {hospitals} hospital(s), {fire_stations} fire station(s), "
            f"and {corridors} road corridor(s) within search radius. "
            "Absence of catalog features is not verified zero exposure."
        )
    else:
        exposure_summary = (
            f"Geographic exposure status is {geo_exposure_status}. "
            f"Evaluated {settlements} settlement(s), {hospitals} hospital(s), {fire_stations} fire station(s), "
            f"and {corridors} road corridor(s) within search radius."
        )

    fire_weather_summary = (
        f"Atmospheric danger rated as {wx_danger}"
        + (f" (FWI={fwi:.1f})" if fwi is not None else "")
        + f". {wx_explanation}"
    )

    supporting_ev: List[str] = []
    if inc_status in ("CONFIRMED", "SUSPECTED"):
        supporting_ev.append(f"Physical observation: {active_evidence}")
    if wx_danger != "UNAVAILABLE":
        supporting_ev.append(f"Fire weather: {wx_danger}" + (f", FWI={fwi:.1f}" if fwi is not None else ""))
    if is_geo_verified and settlements > 0:
        supporting_ev.append(f"Settlements exposed: {settlements} within radius")

    source_provenance = {
        "intelligence_agent": {
            "incident_status": inc_status,
            "incident_severity": inc_severity,
            "active_evidence_state": active_evidence,
            "assessment_id": intel.get("assessment_id"),
        },
        "weather_agent": {
            "danger_rating": wx_danger,
            "fwi": fwi,
            "is_experimental": is_wx_experimental,
            "source": weather.get("source"),
        },
        "geospatial_agent": {
            "exposure_level": geo_level,
            "is_verified": is_geo_verified,
            "data_provider": geo.get("data_provider"),
            "settlements_found": settlements,
        },
        "synthesis_engine": "HeuristicRiskSynthesis (M12.3)",
    }

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    risk_output = RiskAssessmentAgentOutput(
        assessment_status=assessment_status,
        incident_status=inc_status,
        incident_severity=inc_severity,
        fire_weather_danger=wx_danger,
        geographic_exposure_status=geo_exposure_status,
        potential_consequences_status=potential_consequences_status,
        overall_threat_level=overall_threat,
        heuristic_risk_index=heuristic_index,
        hazard_summary=hazard_summary,
        exposure_summary=exposure_summary,
        consequence_summary=consequence_summary,
        fire_weather_summary=fire_weather_summary,
        supporting_evidence=supporting_ev,
        missing_evidence=missing_ev,
        conflicting_evidence=conflicting_ev,
        uncertainty_qualification=uncertainty_qual,
        assessment_rationale=rationale,
        key_risk_drivers=key_drivers,
        mitigating_factors=mitigating,
        source_agent_provenance=source_provenance,
        generated_at=now_iso,
    ).model_dump(mode="json")

    has_errors = bool(state.get("status") == WorkflowStatus.FAILED.value or state.get("errors") or errors)
    final_status = WorkflowStatus.FAILED.value if has_errors else WorkflowStatus.COMPLETED.value
    final_stage = WorkflowStage.TERMINATED_WITH_ERROR.value if has_errors else WorkflowStage.COMPLETED.value

    rec = AgentExecutionRecord(
        agent_name="risk_assessment_agent",
        stage=WorkflowStage.RISK_ASSESSMENT.value,
        status="failed" if has_errors else "success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"Risk assessment synthesized: Threat={overall_threat}, "
            f"Index={heuristic_index}, Status={assessment_status}."
        ),
    ).model_dump(mode="json")

    return {
        "status": final_status,
        "stage": final_stage,
        "risk_assessment_output": risk_output,
        "warnings": warnings,
        "errors": errors,
        "execution_records": [rec],
        "updated_at": now_iso,
        "completed_at": now_iso,
    }
