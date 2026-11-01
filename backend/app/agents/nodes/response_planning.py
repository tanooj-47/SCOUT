"""
backend/app/agents/nodes/response_planning.py
Response Planning Agent node for SCOUT LangGraph Multi-Agent Disaster Response Workflow (Milestone 12.4).
Generates structured, explainable, evidence-grounded response recommendations and safety constraints
strictly as a decision-support advisory. Strictly deterministic; zero LLM hallucination, zero autonomous dispatch.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.agents.schemas import (
    ActionRecommendation,
    AgentExecutionRecord,
    HumanApprovalStatus,
    RecommendationPriority,
    ResponsePlanningAgentOutput,
    WorkflowError,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState, validate_state_transition

logger = logging.getLogger(__name__)


def response_planning_agent_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Agent 5: Response Planning Agent Node
    Responsibilities:
    - Ingests upstream risk assessment, intelligence, weather, and geospatial outputs.
    - Operates strictly as a decision-support system: NEVER executes real-world emergency actions,
      dispatches services, contacts authorities, or activates infrastructure.
    - Generates evidence-grounded, reviewable response recommendations covering life-safety,
      perimeter defense, structure triage, staging, and reconnaissance.
    - Handles deterministic logic for 7 mandatory cases:
        Case A: Confirmed Wildfire
        Case B: Suspected Wildfire
        Case C: Extreme Fire-Weather Danger without Active Incident
        Case D: Confirmed Incident with Unverified Geographic Exposure
        Case E: Insufficient Intelligence Evidence
        Case F: Missing Weather Information
        Case G: Conflicting Evidence
    - Specifies suggested resource categories (generic types only, never fabricated inventories).
    - Preserves responder safety constraints (LCES, escape routes, defensible space rules).
    - Marks initial plan status as PENDING awaiting human authorization.
    """
    start_time = datetime.now(timezone.utc)
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = list(state.get("warnings", []))

    # 1. Inspect upstream risk assessment output
    risk_output = state.get("risk_assessment_output")
    if not risk_output:
        err = WorkflowError(
            code="MISSING_RISK_ASSESSMENT",
            message="Cannot generate response plan: RiskAssessmentAgentOutput is missing from workflow state.",
            stage=WorkflowStage.RESPONSE_PLANNING.value,
            agent="response_planning_agent",
            recoverable=False,
        ).model_dump(mode="json")
        errors.append(err)

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        now_iso = end_time.isoformat()

        rec = AgentExecutionRecord(
            agent_name="response_planning_agent",
            stage=WorkflowStage.RESPONSE_PLANNING.value,
            status="failed",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details="Response planning halted: missing upstream risk assessment.",
        ).model_dump(mode="json")

        return {
            "status": WorkflowStatus.FAILED.value,
            "stage": WorkflowStage.TERMINATED_WITH_ERROR.value,
            "response_plan_output": None,
            "errors": errors,
            "warnings": warnings,
            "execution_records": [rec],
            "updated_at": now_iso,
        }

    # 2. Extract perception and risk inputs
    intel = state.get("intelligence_output") or {}
    weather = state.get("weather_output") or {}
    geo = state.get("geospatial_output") or {}

    incident_status = risk_output.get("incident_status", "UNCONFIRMED")
    overall_threat_level = risk_output.get("overall_threat_level", "ADVISORY_MONITORING")
    assessment_status = risk_output.get("assessment_status", "complete")
    conflicting_ev = list(risk_output.get("conflicting_evidence", []))
    missing_ev = list(risk_output.get("missing_evidence", []))
    key_risk_drivers = list(risk_output.get("key_risk_drivers", []))
    geo_status = risk_output.get("geographic_exposure_status", "")

    # Weather attributes
    fwi = weather.get("fwi")
    fwi_danger = weather.get("danger_rating")
    wind_speed = weather.get("wind_speed_kmh")
    missing_params = list(weather.get("missing_parameters", []))
    is_weather_missing = (
        not weather
        or fwi is None
        or len(missing_params) > 0
        or "UNAVAILABLE" in str(fwi_danger).upper()
        or any("weather" in m.lower() for m in missing_ev)
    )

    # Geospatial attributes
    settlements_count = geo.get("settlements_within_radius", 0)
    closest_settlement_name = geo.get("closest_settlement_name")
    closest_settlement_dist = geo.get("closest_settlement_distance_meters")
    hospitals_count = geo.get("hospitals_within_radius", 0)
    fire_stations_count = geo.get("fire_stations_within_radius", 0)
    corridors_count = geo.get("transport_corridors_count", 0)
    water_bodies_count = geo.get("water_bodies_count", 0)
    is_geo_verified = geo.get("is_verified", False)
    is_geo_unverified = (
        not geo
        or not is_geo_verified
        or "UNVERIFIED" in str(geo.get("exposure_level", "")).upper()
        or "UNVERIFIED" in str(geo_status).upper()
        or any("geo" in m.lower() or "exposure" in m.lower() for m in missing_ev)
    )

    # Intelligence attributes
    visual_state = intel.get("active_evidence_state", "NOT_DETECTED")
    conflicting_streams = list(intel.get("conflicting_streams", []))

    # 3. Determine Case Flags
    has_conflict = bool(conflicting_ev) or bool(conflicting_streams)
    is_extreme_weather_no_active_fire = (
        (incident_status in ("NONE", "INSUFFICIENT_EVIDENCE", "UNCONFIRMED", "UNAVAILABLE") or
         (incident_status == "SUSPECTED" and ("NOT_DETECTED" in visual_state or visual_state == "NO_EVIDENCE")))
        and (
            (fwi is not None and fwi >= 30.0)
            or str(fwi_danger).upper() in ("VERY_HIGH", "EXTREME")
            or any("weather" in k.lower() or "fwi" in k.lower() for k in key_risk_drivers)
        )
    )
    is_insufficient_intel = (
        not is_extreme_weather_no_active_fire
        and incident_status not in ("CONFIRMED", "SUSPECTED")
        and (
            assessment_status in ("insufficient_evidence", "failed")
            or incident_status in ("INSUFFICIENT_EVIDENCE", "UNCONFIRMED")
            or (not intel and not has_conflict)
        )
    )

    # Containers for plan artifacts
    recommendations: List[ActionRecommendation] = []
    suggested_resource_categories: List[str] = []
    safety_precautions: List[str] = [
        "Adhere strictly to 10 Standard Firefighting Orders and 18 Watch Out Situations.",
        "Establish and maintain LCES (Lookouts, Communications, Escape Routes, Safety Zones) prior to engagement.",
        "Maintain continuous situational awareness regarding erratic wind shifts and atmospheric instability.",
        "Do not deploy personnel into unanchored fire perimeters without verified escape corridors.",
    ]
    missing_information: List[str] = []
    operational_limitations: List[str] = [
        "This response plan is an advisory decision-support output. Real-world actions require human incident commander authorization.",
        "Suggested resource categories represent equipment/team types, not live inventory availability.",
    ]
    life_safety_notes: List[str] = []
    responder_information_gaps: List[str] = []
    evacuation_alert_guidance: Optional[str] = None
    overall_plan_status = "complete"
    priority_level = "HIGH"

    # ---------------------------------------------------------------------------
    # CASE G: Conflicting Evidence
    # ---------------------------------------------------------------------------
    if has_conflict:
        priority_level = "CRITICAL"
        overall_plan_status = "partial"
        operational_limitations.append(
            "CRITICAL EVIDENCE CONFLICT DETECTED: Upstream sensor, visual, and environmental inputs are discordant. "
            "All tactical recommendations carry high operational uncertainty and mandate immediate human commander verification."
        )
        life_safety_notes.append(
            "ALERT: Conflicting intelligence evidence detected across modalities. Exercise extreme caution. "
            "Do not commit personnel into high-risk suppression zones without prior ground-truth verification."
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-conf-{uuid4().hex[:6]}",
                category="VERIFICATION",
                title="Dispatch Expedited Ground/Air Reconnaissance to Resolve Intelligence Conflict",
                description=(
                    "Deploy an expedited reconnaissance unit to verify actual ground conditions and reconcile "
                    "contradictory visual classification and environmental observations."
                ),
                priority=RecommendationPriority.CRITICAL.value,
                intended_objective="Reconcile contradictory sensor/model inputs prior to committing tactical suppression assets",
                suggested_responsible_role="Incident Commander / Operations Section Chief",
                suggested_resource_categories=["command_recon_vehicle", "thermal_uas_team"],
                preconditions=["Airspace clearance established; coordinate with dispatch on report origins"],
                safety_constraints=["Reconnaissance team must maintain standoff distance from unverified smoke/fire columns"],
                evidence_references=[
                    "risk_assessment_agent:conflicting_evidence=True",
                    f"risk_assessment_agent:conflicting_evidence={conflicting_ev}",
                ],
                confidence_description="LOW - High uncertainty resulting from contradictory multimodal evidence",
                target_infrastructure=None,
                rationale="Conflicting evidence between visual detection and environmental factors requires rapid ground-truthing to prevent tactical entrapment or false alarm resource exhaustion.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        suggested_resource_categories.extend(["command_recon_vehicle", "thermal_uas_team"])

    # ---------------------------------------------------------------------------
    # CASE C: Extreme Fire-Weather Danger without Active Incident
    # ---------------------------------------------------------------------------
    elif is_extreme_weather_no_active_fire:
        priority_level = "HIGH"
        overall_plan_status = "preparedness_only"
        life_safety_notes.append(
            "PREPAREDNESS ONLY: No active wildfire confirmed. Plan focuses strictly on pre-positioning, "
            "ignition mitigation, and surveillance under extreme fire-weather conditions."
        )
        operational_limitations.append(
            "Preventative readiness posture: offensive wildfire suppression tactics are NOT applicable as no active ignition is confirmed."
        )

        fwi_val_str = f"{fwi:.1f}" if fwi is not None else "EXTREME"
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-prep-ban-{uuid4().hex[:6]}",
                category="PREPAREDNESS",
                title="Enforce Red Flag Fire-Weather Restrictions and Ignition Bans",
                description=(
                    f"Implement strict agricultural burning, campfire, and hot-work bans across the operational sector. "
                    f"Fire Weather Index is elevated ({fwi_val_str}) indicating explosive potential if an ignition occurs."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Eliminate preventable human-caused ignitions during peak fire-weather danger window",
                suggested_responsible_role="Fire Prevention Officer / Public Information Officer",
                suggested_resource_categories=["patrol_unit", "public_alert_system"],
                preconditions=["Public notification broadcast via municipal and forestry communication channels"],
                safety_constraints=["Field enforcement officers must follow standard agency safety procedures"],
                evidence_references=[
                    f"weather_agent:fwi={fwi_val_str}",
                    f"weather_agent:fwi_danger_level={fwi_danger}",
                    f"risk_assessment_agent:key_risk_drivers={key_risk_drivers}",
                ],
                confidence_description="HIGH - Grounded in empirical fire-weather indices",
                target_infrastructure=None,
                rationale="Extreme fire-weather indices correlate strongly with rapid initial flame spread; ignition restriction is the primary life-safety risk reduction measure.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-prep-pos-{uuid4().hex[:6]}",
                category="PREPAREDNESS",
                title="Pre-position Initial Attack Assets at Strategic Staging Corridors",
                description=(
                    "Pre-position wildland initial attack apparatus at designated staging pads near high-hazard interfaces "
                    "to achieve a sub-15-minute response time in the event of new ignitions."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Minimize response latency for rapid initial attack during extreme burning conditions",
                suggested_responsible_role="Duty Chief / Planning Section Chief",
                suggested_resource_categories=["initial_attack_wildland_engine", "patrol_scout"],
                preconditions=["Identify designated standby locations with continuous radio and cellular coverage"],
                safety_constraints=["Staged personnel must remain hydrated and monitored for heat exhaustion"],
                evidence_references=[
                    f"weather_agent:fwi={fwi_val_str}",
                    f"risk_assessment_agent:overall_threat_level={overall_threat_level}",
                ],
                confidence_description="HIGH - Pre-positioning strategy matches verified regional fire-weather hazard",
                target_infrastructure=None,
                rationale="High fire-weather indices reduce ignition delay and increase rate of spread; pre-positioning enables fast initial knockdown before fires escape initial attack capability.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-prep-surv-{uuid4().hex[:6]}",
                category="MONITORING",
                title="Activate High-Frequency Lookout Watch and Aerial Patrol Corridors",
                description=(
                    "Maintain continuous lookout surveillance and schedule periodic aerial reconnaissance flights "
                    "over high-fuel-load zones during peak daily burning hours."
                ),
                priority=RecommendationPriority.MEDIUM.value,
                intended_objective="Detect lightning or accidental ignitions at the earliest possible stage",
                suggested_responsible_role="Air Operations / Dispatch Supervisor",
                suggested_resource_categories=["aerial_patrol_recon", "lookout_observer"],
                preconditions=["Staff lookout stations and verify aircraft dispatch readiness"],
                safety_constraints=["Reconnaissance aircraft must monitor gust front turbulence"],
                evidence_references=[f"weather_agent:fwi={fwi_val_str}"],
                confidence_description="HIGH - Surveillance aligns with high fire-weather threat level",
                target_infrastructure=None,
                rationale="Immediate detection enables suppression during early ignition phases when containment probability is highest.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        suggested_resource_categories.extend([
            "patrol_unit",
            "public_alert_system",
            "initial_attack_wildland_engine",
            "patrol_scout",
            "aerial_patrol_recon",
            "lookout_observer",
        ])

    # ---------------------------------------------------------------------------
    # CASE E: Insufficient Intelligence Evidence
    # ---------------------------------------------------------------------------
    elif is_insufficient_intel:
        priority_level = "HIGH"
        overall_plan_status = "insufficient_evidence"
        missing_information.extend([
            "Validated optical or multispectral imagery of suspected incident",
            "Empirical verification of thermal anomalies or active flame front",
            "Confirmed spatial footprint of fire or smoke plume",
        ])
        responder_information_gaps.extend([
            "Is there an active ignition present at the reported coordinates?",
            "What is the actual perimeter size and predominant direction of spread?",
            "Are any residential structures or critical infrastructure directly threatened?",
        ])
        operational_limitations.append(
            "Response plan strictly restricted to reconnaissance. Offensive suppression tactics and large-scale "
            "evacuations cannot be recommended without confirmed incident intelligence."
        )
        life_safety_notes.append(
            "Evidence is insufficient to establish incident severity or extent. Prioritize ground-truth verification."
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-intel-recon-{uuid4().hex[:6]}",
                category="VERIFICATION",
                title="Deploy Targeted Ground/Air Reconnaissance to Resolve Intelligence Deficiencies",
                description=(
                    "Dispatch a field reconnaissance scout or UAS operator to verify whether an active disaster exists, "
                    "characterize fire behavior if present, and provide ground truth."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Obtain confirmed operational intelligence before committing emergency response assets",
                suggested_responsible_role="Situation Unit Leader / Intelligence Officer",
                suggested_resource_categories=["field_reconnaissance_unit", "thermal_uas_team"],
                preconditions=["Check accessibility and weather suitability prior to field scout deployment"],
                safety_constraints=["Scouts must not enter hazardous smoke plumes without self-contained escape routes"],
                evidence_references=[
                    f"risk_assessment_agent:assessment_status={assessment_status}",
                    f"risk_assessment_agent:incident_status={incident_status}",
                ],
                confidence_description="LOW - Severe intelligence data deficit prevents definitive tactical planning",
                target_infrastructure=None,
                rationale="Suppression operations require validated intelligence to avoid misallocating limited emergency assets or placing responders in unknown hazards.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        suggested_resource_categories.extend(["field_reconnaissance_unit", "thermal_uas_team"])

    # ---------------------------------------------------------------------------
    # CASE A: Confirmed Wildfire
    # ---------------------------------------------------------------------------
    elif incident_status == "CONFIRMED":
        priority_level = "CRITICAL" if overall_threat_level in ("CRITICAL_EMERGENCY", "HIGH_ALERT") else "HIGH"
        overall_plan_status = "complete" if is_geo_verified else "partial"

        life_safety_notes.append(
            "CRITICAL: Confirmed wildfire incident. Primary operational priority is life safety, population protection, "
            "and maintaining responder safety zones and egress corridors."
        )

        # 1. Life Safety & Population Protection Recommendation
        target_settlement = closest_settlement_name or "Proximate populated settlements"
        evacuation_alert_guidance = (
            f"Recommend Incident Commander evaluate pre-evacuation alert for {target_settlement} "
            f"located {closest_settlement_dist:.0f}m from incident" if closest_settlement_dist else
            "Recommend Incident Commander evaluate pre-evacuation warnings for vulnerable settlements downwind of incident perimeter."
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-conf-life-{uuid4().hex[:6]}",
                category="LIFE_SAFETY",
                title="Issue Pre-Evacuation Alert and Evacuation Corridor Preparation for Proximate Settlements",
                description=(
                    f"Prepare civilian evacuation advisories and verify traffic control points along primary egress routes "
                    f"servicing {target_settlement}. Human Incident Commander authorization is strictly required."
                ),
                priority=RecommendationPriority.CRITICAL.value,
                intended_objective="Protect civilian lives by facilitating orderly pre-evacuation readiness in vulnerable sectors",
                suggested_responsible_role="Incident Commander / Operations Section Chief",
                suggested_resource_categories=["law_enforcement_traffic_control", "public_alert_system", "evacuation_liaison"],
                preconditions=[
                    "Incident Commander review and explicit authorization required",
                    "Primary and secondary civilian egress routes verified open and unobstructed",
                ],
                safety_constraints=[
                    "Ensure emergency responder ingress routes do not conflict with civilian evacuation flow",
                    "Never direct civilian evacuation through unanchored fire perimeters",
                ],
                evidence_references=[
                    "risk_assessment_agent:incident_status=CONFIRMED",
                    f"risk_assessment_agent:overall_threat_level={overall_threat_level}",
                    f"geospatial_agent:settlements_within_radius={settlements_count}",
                ],
                confidence_description="HIGH - Grounded in confirmed incident status and spatial proximity",
                target_infrastructure=target_settlement,
                rationale="Confirmed active wildfire presents direct life-safety hazards to proximate civilian settlements; early evacuation corridor readiness prevents entrapment.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )

        # 2. Fire Perimeter Containment & Flank Defense
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-conf-contain-{uuid4().hex[:6]}",
                category="CONTAINMENT",
                title="Establish Defensible Anchor Points and Flank Containment Lines",
                description=(
                    "Deploy wildland suppression teams to secure flank anchor points using natural and manmade firebreaks "
                    "to halt lateral spread and flank expansion."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Anchor fire perimeter to defensible barriers and prevent lateral spread",
                suggested_responsible_role="Operations Section Chief / Division Supervisor",
                suggested_resource_categories=["type_3_engine", "wildland_brush_truck", "type_2_hand_crew"],
                preconditions=[
                    "Anchor points confirmed defensible by ground scouting",
                    "Continuous communication with lookouts established",
                ],
                safety_constraints=[
                    "Strict enforcement of LCES rules at all times",
                    "Do not attempt direct frontal attack under active crowning or high spread velocities",
                ],
                evidence_references=[
                    "risk_assessment_agent:incident_status=CONFIRMED",
                    f"risk_assessment_agent:key_risk_drivers={key_risk_drivers}",
                ],
                confidence_description="HIGH - Containment strategy follows standard wildland operational doctrine",
                target_infrastructure=None,
                rationale="Securing flank anchors is required to halt perimeter expansion and protect downwind exposures.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )

        # 3. Critical Infrastructure & Structure Defense (if present and verified)
        if hospitals_count > 0 or settlements_count > 0:
            target_asset = f"{hospitals_count} hospital(s) / {settlements_count} settlement(s)"
            recommendations.append(
                ActionRecommendation(
                    action_id=f"act-conf-struct-{uuid4().hex[:6]}",
                    category="STRUCTURE_PROTECTION",
                    title="Deploy Precautionary Structure Protection and Asset Triage",
                    description=(
                        f"Implement structure triage and prepare defensible perimeter defenses for {target_asset} "
                        f"identified within the response radius."
                    ),
                    priority=RecommendationPriority.HIGH.value,
                    intended_objective="Protect high-value civilian infrastructure and vulnerable institutional facilities",
                    suggested_responsible_role="Structure Protection Group Supervisor",
                    suggested_resource_categories=["structure_protection_unit", "water_tender"],
                    preconditions=[
                        "Perform structure triage (defensible vs non-defensible)",
                        "Establish continuous water supply backup",
                    ],
                    safety_constraints=[
                        "Do not commit crews to defend structures with zero defensible space or inadequate safety zones",
                        "Maintain clear engine egress facing outward",
                    ],
                    evidence_references=[
                        f"geospatial_agent:hospitals_within_radius={hospitals_count}",
                        f"geospatial_agent:settlements_within_radius={settlements_count}",
                    ],
                    confidence_description="HIGH - Direct geospatial confirmation of critical assets in threat zone",
                    target_infrastructure=target_asset,
                    rationale="Critical infrastructure and healthcare facilities require proactive defensible space preparation to avoid catastrophic asset loss.",
                    is_conditional=True,
                    condition_description="Contingent upon structure triage confirming defensibility",
                    requires_human_authorization=True,
                )
            )

        # 4. Water Drafting Reconnaissance (if water bodies nearby)
        if water_bodies_count > 0:
            recommendations.append(
                ActionRecommendation(
                    action_id=f"act-conf-water-{uuid4().hex[:6]}",
                    category="MONITORING",
                    title="Establish Water Drafting Points at Identified Hydrologic Features",
                    description=(
                        f"Reconnoiter identified water bodies ({water_bodies_count} mapped) to establish high-capacity "
                        f"drafting sites for continuous engine and water tender shuttling."
                    ),
                    priority=RecommendationPriority.MEDIUM.value,
                    intended_objective="Secure reliable, continuous water replenishment for active suppression operations",
                    suggested_responsible_role="Water Supply Unit Leader",
                    suggested_resource_categories=["water_tender", "portable_pump_kit"],
                    preconditions=["Verify access road load capacity and turning clearance for heavy tenders"],
                    safety_constraints=["Avoid soft-shoulder suction points that risk vehicle immobilization"],
                    evidence_references=[f"geospatial_agent:water_bodies_count={water_bodies_count}"],
                    confidence_description="HIGH - Verified hydrologic features mapped within response buffer",
                    target_infrastructure="Nearby hydrologic feature",
                    rationale="Sustained fire suppression requires established continuous water supply shuttle corridors.",
                    is_conditional=False,
                    requires_human_authorization=True,
                )
            )

        suggested_resource_categories.extend([
            "law_enforcement_traffic_control",
            "public_alert_system",
            "type_3_engine",
            "wildland_brush_truck",
            "type_2_hand_crew",
            "structure_protection_unit",
            "water_tender",
        ])

    # ---------------------------------------------------------------------------
    # CASE B: Suspected Wildfire
    # ---------------------------------------------------------------------------
    elif incident_status == "SUSPECTED":
        priority_level = "HIGH"
        overall_plan_status = "partial"

        life_safety_notes.append(
            "INCIDENT STATUS IS SUSPECTED. Do not issue unverified mandatory evacuation orders based on preliminary detection. "
            "Maintain pre-evacuation awareness for proximate settlements while expediting confirmation."
        )
        operational_limitations.append(
            "Visual evidence is consistent with fire/smoke but lacks independent empirical confirmation. "
            "Tactical resource dispatch is restricted to reconnaissance and standby readiness."
        )

        recommendations.append(
            ActionRecommendation(
                action_id=f"act-susp-recon-{uuid4().hex[:6]}",
                category="VERIFICATION",
                title="Dispatch Rapid Ground/UAS Reconnaissance to Confirm Incident Status",
                description=(
                    "Deploy aerial thermal drone or ground scout to verify fire presence, determine exact perimeter coordinates, "
                    "and assess rate of spread and fuel involvement."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Confirm or refute suspected wildfire detection with on-scene ground-truth evidence",
                suggested_responsible_role="Air Operations Branch / Scouting Leader",
                suggested_resource_categories=["thermal_infrared_uas", "wildland_reconnaissance_unit"],
                preconditions=["Flight authorization and airspace deconfliction established if deploying UAS"],
                safety_constraints=["Reconnaissance unit must maintain standoff distance from unverified smoke/flame columns"],
                evidence_references=[
                    "risk_assessment_agent:incident_status=SUSPECTED",
                    f"intelligence_agent:visual_evidence_state={visual_state}",
                ],
                confidence_description="MEDIUM - Incident is suspected from visual indicators; field validation pending",
                target_infrastructure=None,
                rationale="Confirmation is mandatory before committing large-scale offensive suppression forces or initiating costly civilian evacuations.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )

        recommendations.append(
            ActionRecommendation(
                action_id=f"act-susp-standby-{uuid4().hex[:6]}",
                category="PREPAREDNESS",
                title="Place Local Response Units on Precautionary Standby",
                description=(
                    "Alert nearby fire stations and wildland response crews to maintain standby readiness "
                    "for immediate deployment if incident confirmation is received."
                ),
                priority=RecommendationPriority.MEDIUM.value,
                intended_objective="Minimize initial attack delay upon incident confirmation while avoiding premature deployment",
                suggested_responsible_role="Duty Officer / Dispatch Coordinator",
                suggested_resource_categories=["type_3_engine", "wildland_brush_truck"],
                preconditions=["Units remain at station or assigned staging pads pending confirmation"],
                safety_constraints=["No offensive line construction until fire presence, location, and behavior are confirmed"],
                evidence_references=[
                    "risk_assessment_agent:incident_status=SUSPECTED",
                    f"risk_assessment_agent:overall_threat_level={overall_threat_level}",
                ],
                confidence_description="MEDIUM - Standby posture balances rapid response capability against premature deployment",
                target_infrastructure=None,
                rationale="Precautionary standby minimizes deployment latency if the suspected fire escalates or is rapidly verified.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        suggested_resource_categories.extend([
            "thermal_infrared_uas",
            "wildland_reconnaissance_unit",
            "type_3_engine",
            "wildland_brush_truck",
        ])

    # ---------------------------------------------------------------------------
    # FALLBACK / UNCONFIRMED
    # ---------------------------------------------------------------------------
    else:
        priority_level = "MEDIUM"
        overall_plan_status = "partial"
        operational_limitations.append(
            f"Incident status is '{incident_status}'. Plan is limited to routine monitoring and verification."
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-unconf-mon-{uuid4().hex[:6]}",
                category="MONITORING",
                title="Maintain Periodic Remote Surveillance",
                description="Continue monitoring satellite and sensor feeds for potential changes in fire activity.",
                priority=RecommendationPriority.MEDIUM.value,
                intended_objective="Track potential changes in detection status",
                suggested_responsible_role="Situation Unit Leader",
                suggested_resource_categories=["remote_sensing_analyst"],
                preconditions=[],
                safety_constraints=[],
                evidence_references=[f"risk_assessment_agent:incident_status={incident_status}"],
                confidence_description="LOW - Unconfirmed baseline",
                target_infrastructure=None,
                rationale="No confirmed or suspected active disaster; maintain situational watch.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )

    # ---------------------------------------------------------------------------
    # CASE D: Unverified Geographic Context
    # ---------------------------------------------------------------------------
    if is_geo_unverified and incident_status in ("CONFIRMED", "SUSPECTED"):
        overall_plan_status = "partial" if overall_plan_status == "complete" else overall_plan_status
        missing_information.extend([
            "Verified spatial footprint and structure inventory within search radius",
            "Empirical ground-truth verification of residential and infrastructure exposures",
        ])
        operational_limitations.append(
            "GEOSPATIAL EXPOSURE UNVERIFIED: Local catalog data is missing or incomplete (0 features or unverified source). "
            "Absence of catalog features is NOT proof of absence of vulnerable structures. Do NOT invent affected assets."
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-geo-survey-{uuid4().hex[:6]}",
                category="VERIFICATION",
                title="Conduct Rapid Exposure Survey and GIS Ground-Truthing",
                description=(
                    "Deploy field GIS personnel or activate high-resolution satellite imagery tasking to map structures, "
                    "roads, and exposures within the response radius. Do NOT assume zero exposure based on catalog gaps."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Verify exact presence and locations of structures and vulnerable populations",
                suggested_responsible_role="GIS Unit Leader / Situation Unit Leader",
                suggested_resource_categories=["field_gis_recon_team", "satellite_tasking_request"],
                preconditions=["Field team must operate from secured areas outside fire perimeter"],
                safety_constraints=["Do not commit survey teams into unmapped dead-end terrain or unanchored sectors"],
                evidence_references=[
                    f"geospatial_agent:is_verified={is_geo_verified}",
                    f"geospatial_agent:exposure_level={geo.get('exposure_level', 'UNVERIFIED')}",
                ],
                confidence_description="LOW - Geographic exposure layer lacks ground-truthed verification",
                target_infrastructure=None,
                rationale="Targeted structure defense and evacuation planning cannot be safely executed when spatial exposure layers are unverified.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        suggested_resource_categories.extend(["field_gis_recon_team", "satellite_tasking_request"])

    # ---------------------------------------------------------------------------
    # CASE F: Missing Weather Information
    # ---------------------------------------------------------------------------
    if is_weather_missing and incident_status in ("CONFIRMED", "SUSPECTED"):
        missing_information.extend([
            "Real-time on-site wind speed, wind direction, and gust envelope",
            "Current on-site relative humidity and temperature measurements",
            "Locally calibrated Fire Weather Index (FWI) components",
        ])
        operational_limitations.append(
            "WEATHER DATA DEFICIT: Weather observations are missing, uncalibrated, or based on fallback heuristics. "
            "Tactical spread velocity predictions and downwind evacuation arc projections are strictly omitted."
        )
        recommendations.append(
            ActionRecommendation(
                action_id=f"act-wx-spot-{uuid4().hex[:6]}",
                category="MONITORING",
                title="Request Incident Meteorologist (IMET) Spot Forecast and Deploy Portable Weather Station",
                description=(
                    "Deploy a portable meteorological station to staging and request an official spot-weather forecast "
                    "from the National Weather Service / meteorological authority to acquire local wind and RH data."
                ),
                priority=RecommendationPriority.HIGH.value,
                intended_objective="Establish reliable real-time meteorological baseline to guide safe tactical positioning",
                suggested_responsible_role="Safety Officer / Planning Section Chief",
                suggested_resource_categories=["portable_weather_station", "spot_forecast_request"],
                preconditions=["Position portable weather station in an open, unshielded staging area"],
                safety_constraints=[
                    "Exercise maximum safety margin; erratic wind shifts cannot be anticipated without real-time local wind data"
                ],
                evidence_references=[
                    f"weather_agent:danger_rating={fwi_danger}",
                    f"weather_agent:missing_data={is_weather_missing}",
                ],
                confidence_description="LOW - Local meteorological inputs are currently missing or uncalibrated",
                target_infrastructure=None,
                rationale="Wildland fire behavior is heavily driven by local wind velocity and relative humidity; suppression without local weather data risks catastrophic responder entrapment.",
                is_conditional=False,
                requires_human_authorization=True,
            )
        )
        suggested_resource_categories.extend(["portable_weather_station", "spot_forecast_request"])

    # Deduplicate suggested resource categories while preserving order
    unique_resource_categories: List[str] = []
    for r in suggested_resource_categories:
        if r not in unique_resource_categories:
            unique_resource_categories.append(r)

    # Compile source agent provenance
    source_provenance = {
        "risk_assessment_agent": risk_output.get("assessment_status", "unknown"),
        "intelligence_agent": intel.get("incident_status") if intel else "absent",
        "weather_agent": weather.get("data_quality") if weather else "absent",
        "geospatial_agent": geo.get("exposure_level") if geo else "absent",
    }

    # Assemble typed ResponsePlanningAgentOutput
    plan_out = ResponsePlanningAgentOutput(
        plan_id=f"plan-{uuid4().hex[:8]}",
        disaster_type="wildfire",
        incident_status=incident_status,
        assessed_threat_level=overall_threat_level,
        overall_plan_status=overall_plan_status,
        recommendations=recommendations,
        relevant_geographic_context={
            "settlements_within_radius": settlements_count,
            "closest_settlement_name": closest_settlement_name,
            "closest_settlement_distance_meters": closest_settlement_dist,
            "hospitals_within_radius": hospitals_count,
            "fire_stations_within_radius": fire_stations_count,
            "is_verified": is_geo_verified,
        },
        suggested_resource_categories=unique_resource_categories,
        safety_precautions=safety_precautions,
        missing_information=missing_information,
        operational_limitations=operational_limitations,
        human_approval_status=HumanApprovalStatus.PENDING.value,
        source_agent_provenance=source_provenance,
        priority_level=priority_level,
        life_safety_notes=life_safety_notes,
        responder_information_gaps=responder_information_gaps,
        evacuation_alert_guidance=evacuation_alert_guidance,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump(mode="json")

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    rec = AgentExecutionRecord(
        agent_name="response_planning_agent",
        stage=WorkflowStage.RESPONSE_PLANNING.value,
        status="success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"Response plan generated: Status={overall_plan_status}, "
            f"Recommendations={len(recommendations)}, ApprovalStatus=PENDING."
        ),
    ).model_dump(mode="json")

    return {
        "stage": WorkflowStage.RESPONSE_PLANNING.value,
        "response_plan_output": plan_out,
        "warnings": warnings,
        "errors": errors,
        "execution_records": [rec],
        "updated_at": now_iso,
    }
