"""
backend/app/agents/nodes/weather.py
Weather Agent node for SCOUT LangGraph Multi-Agent Disaster Response Workflow (Milestone 12.2).
Interprets atmospheric conditions, Canadian FWI indices, and fire weather danger independently of incident confirmation.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from app.agents.schemas import (
    AgentExecutionRecord,
    WeatherAgentOutput,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState

logger = logging.getLogger(__name__)


def weather_agent_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Agent 2: Weather Agent Node
    Responsibilities:
    - Consumes actual environmental data from the M11 intelligence assessment.
    - Interprets temperature, relative humidity, wind speed, precipitation, and FWI indices.
    - Preserves observation timestamps, data sources, and provenance.
    - Identifies missing, stale, or experimental observations without generating synthetic defaults.
    - Explains atmospheric fire-weather danger independently of incident confirmation.
    - Returns a validated WeatherAgentOutput schema.
    """
    start_time = datetime.now(timezone.utc)
    warnings: List[str] = []

    m11_assessment = state.get("m11_assessment")

    # If M11 assessment is not available, emit explicit unavailable output
    if not m11_assessment:
        logger.warning(
            "Weather agent executed without valid M11 assessment in workflow %s",
            state.get("workflow_id"),
        )
        unavailable_output = WeatherAgentOutput(
            temperature_c=None,
            relative_humidity_pct=None,
            wind_speed_kmh=None,
            precipitation_mm=None,
            fwi=None,
            danger_rating="UNAVAILABLE",
            fire_weather_explanation="Environmental observations unavailable: M11 assessment was not provided.",
            is_experimental=True,
            stale_observations=[],
            missing_parameters=["all_meteorological_parameters"],
            observation_timestamp=None,
            source=None,
            provenance={"agent": "weather_agent", "status": "unavailable"},
        ).model_dump(mode="json")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        rec = AgentExecutionRecord(
            agent_name="weather_agent",
            stage=WorkflowStage.CONTEXT_INTERPRETATION.value,
            status="skipped" if state.get("status") == WorkflowStatus.FAILED.value else "success",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details="Environmental assessment unavailable: upstream M11 assessment missing.",
        ).model_dump(mode="json")

        return {
            "weather_output": unavailable_output,
            "execution_records": [rec],
            "updated_at": end_time.isoformat(),
        }

    # Locate environmental evidence item from M11 evidence stream
    evidence_items = m11_assessment.get("evidence_items", [])
    env_item = next(
        (item for item in evidence_items if item.get("category") == "environmental"),
        None,
    )

    temp_c: Optional[float] = None
    rh_pct: Optional[float] = None
    wind_kmh: Optional[float] = None
    precip_mm: Optional[float] = None
    fwi_val: Optional[float] = None
    danger_rating: Optional[str] = None
    missing_vars: List[str] = []
    stale_observations: List[str] = []
    obs_timestamp: Optional[str] = None
    source_name: Optional[str] = None
    provenance_details: Dict[str, Any] = {}

    if env_item:
        raw_val = env_item.get("raw_value") or {}
        if isinstance(raw_val, dict):
            temp_c = raw_val.get("temperature_c")
            rh_pct = raw_val.get("relative_humidity_pct")
            wind_kmh = raw_val.get("wind_speed_kmh")
            precip_mm = raw_val.get("precipitation_mm")
            fwi_indices = raw_val.get("fwi_indices") or {}
            if isinstance(fwi_indices, dict):
                fwi_val = fwi_indices.get("fire_weather_index_fwi")
                danger_rating = fwi_indices.get("danger_rating")
            missing_vars = list(raw_val.get("missing_meteorological_variables") or [])

        # Check evidence quality & freshness
        quality = env_item.get("quality") or {}
        if quality.get("is_stale"):
            stale_observations.append("environmental_observation")
            warnings.append("Environmental observations exceed freshness thresholds (stale observation).")

        obs_timestamp = env_item.get("observation_timestamp")
        source_name = env_item.get("source_name", "open-meteo")
        provenance_details = {
            "source_name": source_name,
            "observation_id": env_item.get("id"),
            "retrieval_timestamp": env_item.get("retrieval_timestamp"),
            "provider_type": quality.get("provider_type", "reanalysis_model"),
            "fwi_methodology": (
                raw_val.get("fwi_methodology", "instantaneous_weather_indicator")
                if isinstance(raw_val, dict)
                else "unknown"
            ),
        }
    else:
        missing_vars.append("environmental_evidence_stream")
        warnings.append("No environmental evidence item found in M11 assessment.")

    # Fallback to hazard assessment fire weather danger if not set from fwi_indices
    hazard_assessment = m11_assessment.get("hazard_assessment") or {}
    if not danger_rating:
        danger_rating = (
            hazard_assessment.get("fire_weather_level")
            or m11_assessment.get("fire_weather_danger")
            or "UNAVAILABLE"
        )

    # Explanation generation preserving epistemic distinction
    explanation = hazard_assessment.get("fire_weather_explanation")
    if not explanation or explanation == "No fire weather observation evaluated.":
        if danger_rating and danger_rating != "UNAVAILABLE":
            explanation = (
                f"Atmospheric fire-weather danger rated as {danger_rating}. "
                f"Represents instantaneous atmospheric combustibility proxy, "
                f"strictly independent of physical fire confirmation."
            )
        else:
            explanation = "Atmospheric fire-weather conditions are unavailable or incomplete."

    # Validate output schema
    weather_out = WeatherAgentOutput(
        temperature_c=temp_c,
        relative_humidity_pct=rh_pct,
        wind_speed_kmh=wind_kmh,
        precipitation_mm=precip_mm,
        fwi=fwi_val,
        danger_rating=danger_rating,
        fire_weather_explanation=explanation,
        is_experimental=True,  # Instantaneous Canadian FWI without multi-day history is experimental
        stale_observations=stale_observations,
        missing_parameters=missing_vars,
        observation_timestamp=obs_timestamp,
        source=source_name,
        provenance=provenance_details,
    ).model_dump(mode="json")

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    fwi_desc = f"FWI={fwi_val:.1f}" if fwi_val is not None else "FWI=None"
    rec = AgentExecutionRecord(
        agent_name="weather_agent",
        stage=WorkflowStage.CONTEXT_INTERPRETATION.value,
        status="success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"Weather data interpreted: Danger={danger_rating}, {fwi_desc}, "
            f"Temp={temp_c}°C, Missing={missing_vars}."
        ),
    ).model_dump(mode="json")

    return {
        "stage": WorkflowStage.CONTEXT_INTERPRETATION.value,
        "weather_output": weather_out,
        "warnings": warnings,
        "execution_records": [rec],
        "updated_at": now_iso,
    }
