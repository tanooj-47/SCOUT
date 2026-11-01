"""
backend/app/intelligence/evidence.py
Evidence collection, normalization, freshness scoring, and validation.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.intelligence.exceptions import InvalidEvidenceError
from app.intelligence.schemas import (
    CoordinateLocation,
    EvidenceCategory,
    EvidenceItem,
    EvidenceQuality,
    EvidenceStatus,
)

logger = logging.getLogger(__name__)

# Operational freshness thresholds (in hours)
FRESHNESS_THRESHOLDS_HOURS = {
    EvidenceCategory.COMPUTER_VISION: 4.0,       # Field image or aerial frame
    EvidenceCategory.ENVIRONMENTAL: 3.0,         # Surface atmospheric conditions
    EvidenceCategory.GEOSPATIAL_CONTEXT: 720.0,  # Vector infrastructure catalog (30 days)
    EvidenceCategory.SOURCE_METADATA: 1.0,
    EvidenceCategory.SATELLITE_OBSERVATION: 6.0, # Satellite thermal anomaly (VIIRS/MODIS passes)
    EvidenceCategory.FIELD_REPORT: 2.0,          # Ground personnel field dispatch report
}


class EvidenceCollector:
    """
    Standardizes evidence collection across modalities.
    Enforces freshness evaluation, validation, and transparent failure tracking.
    """

    @staticmethod
    def evaluate_freshness(
        observation_time: Optional[datetime],
        category: EvidenceCategory,
        now_time: Optional[datetime] = None,
    ) -> tuple[bool, Optional[float]]:
        """
        Determines whether an observation is stale based on category freshness thresholds.
        Returns (is_stale, age_seconds).
        """
        if observation_time is None:
            return False, None

        ref_time = now_time or datetime.now(timezone.utc)
        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(tzinfo=timezone.utc)

        age_seconds = (ref_time - observation_time).total_seconds()
        if age_seconds < 0:
            # Timestamp in future (clock skew); treat age as 0
            age_seconds = 0.0

        threshold_hours = FRESHNESS_THRESHOLDS_HOURS.get(category, 24.0)
        threshold_seconds = threshold_hours * 3600.0
        is_stale = age_seconds > threshold_seconds

        return is_stale, age_seconds

    @classmethod
    def create_cv_evidence(
        cls,
        probabilities: Dict[str, float],
        model_name: str,
        checkpoint_path: str,
        observation_time: Optional[datetime] = None,
        location: Optional[CoordinateLocation] = None,
    ) -> EvidenceItem:
        """
        Constructs a verified Computer Vision EvidenceItem from model probabilities.
        """
        is_stale, age_seconds = cls.evaluate_freshness(
            observation_time, EvidenceCategory.COMPUTER_VISION
        )

        # Validate probabilities sum to ~1.0
        prob_sum = sum(probabilities.values())
        if abs(prob_sum - 1.0) > 0.05:
            raise InvalidEvidenceError(
                "cv_probability", f"Probabilities do not sum to 1.0 (got {prob_sum:.3f})"
            )

        top_class = max(probabilities.items(), key=lambda kv: kv[1])
        status = EvidenceStatus.STALE if is_stale else EvidenceStatus.VALID

        quality = EvidenceQuality(
            is_stale=is_stale,
            age_seconds=age_seconds,
            has_confidence_measure=True,
            confidence_scale="softmax_probability [0.0 - 1.0]",
            provider_type="deep_learning_vision_classifier",
        )

        provenance = {
            "model_architecture": model_name,
            "checkpoint": checkpoint_path,
            "champion_selection": "BaselineCNN (val_macro_f1=0.8387)",
            "top_predicted_class": top_class[0],
            "top_class_probability": round(top_class[1], 4),
            "raw_class_scores": {k: round(v, 4) for k, v in probabilities.items()},
            "decision_threshold": 0.50,
            "decision_threshold_status": "uncalibrated_engineering_heuristic",
        }

        caveats = [
            "Classification reflects visual features (flame texture, smoke plume) in the submitted image.",
            "Softmax output is an uncalibrated model score, NOT an empirical or calibrated real-world incident probability.",
            "The 0.50 decision threshold is an engineering heuristic, not a calibrated Bayes-optimal risk boundary.",
            "Ground view perspective may suffer from occlusions, viewpoint constraints, or lighting artifacts.",
        ]

        return EvidenceItem(
            id=f"ev-cv-{uuid4().hex[:8]}",
            category=EvidenceCategory.COMPUTER_VISION,
            source_name=model_name,
            status=status,
            observation_timestamp=observation_time or datetime.now(timezone.utc),
            location=location,
            raw_value=probabilities,
            confidence=round(top_class[1], 4),
            quality=quality,
            provenance=provenance,
            caveats=caveats,
        )

    @classmethod
    def create_unavailable_cv_evidence(cls, reason: str) -> EvidenceItem:
        """
        Records an explicit unavailable computer vision evidence item when imagery is missing or corrupt.
        """
        quality = EvidenceQuality(
            is_stale=False,
            age_seconds=None,
            has_confidence_measure=False,
            confidence_scale=None,
            provider_type="deep_learning_vision_classifier",
        )

        return EvidenceItem(
            id=f"ev-cv-unavailable-{uuid4().hex[:8]}",
            category=EvidenceCategory.COMPUTER_VISION,
            source_name="BaselineCNN",
            status=EvidenceStatus.UNAVAILABLE,
            observation_timestamp=datetime.now(timezone.utc),
            location=None,
            raw_value={"error": reason},
            confidence=None,
            quality=quality,
            provenance={"reason": reason},
            caveats=["No valid image evidence provided; visual modality excluded from fusion."],
        )

    @classmethod
    def create_environmental_evidence(
        cls,
        weather_data: Dict[str, Any],
        provider: str,
        model_or_dataset: str,
        is_stale: bool,
        observation_time: Optional[datetime] = None,
        location: Optional[CoordinateLocation] = None,
    ) -> EvidenceItem:
        """
        Constructs a verified Environmental EvidenceItem from weather observation and FWI indices.
        """
        eval_stale, age_seconds = cls.evaluate_freshness(
            observation_time, EvidenceCategory.ENVIRONMENTAL
        )
        final_stale = is_stale or eval_stale

        status = EvidenceStatus.STALE if final_stale else EvidenceStatus.VALID

        quality = EvidenceQuality(
            is_stale=final_stale,
            age_seconds=age_seconds,
            has_confidence_measure=False,
            confidence_scale=None,
            provider_type="numerical_weather_prediction_or_reanalysis",
        )

        fwi_available = weather_data.get("fwi_available", True if weather_data.get("fwi_indices") else False)

        provenance = {
            "provider": provider,
            "dataset_or_model": model_or_dataset,
            "fwi_engine": "Canadian Forest Fire Weather Index (Van Wagner 1985/1987)",
            "fwi_status": "instantaneous_indicator" if fwi_available else "fwi_unavailable",
        }

        caveats = [
            f"Weather data derived from {provider} ({model_or_dataset}); subject to atmospheric grid resolution.",
            "FWI calculation uses standard Canadian equations and has NOT been calibrated for Indian forest fuel types.",
            "Grid point may differ from microclimatic conditions at the specific point of origin.",
        ]

        if fwi_available:
            caveats.append(
                "Instantaneous single-reading FWI approximation (experimental_uninitialized_fwi); lacks 12:00 LST standardization, 24h rainfall history, and consecutive multi-day moisture code tracking (standard CFS-FWI requires consecutive daily tracking from snowmelt). Interpret strictly as an instantaneous atmospheric combustibility indicator."
            )
        else:
            caveats.append(
                "Complete CFS-FWI indices were NOT computed due to missing meteorological observation parameters; relying on raw temperature and humidity indicators if available."
            )

        return EvidenceItem(
            id=f"ev-env-{uuid4().hex[:8]}",
            category=EvidenceCategory.ENVIRONMENTAL,
            source_name=f"{provider}_{model_or_dataset}",
            status=status,
            observation_timestamp=observation_time or datetime.now(timezone.utc),
            location=location,
            raw_value=weather_data,
            confidence=None,
            quality=quality,
            provenance=provenance,
            caveats=caveats,
        )

    @classmethod
    def create_unavailable_environmental_evidence(cls, reason: str) -> EvidenceItem:
        """
        Records unavailable environmental evidence.
        """
        quality = EvidenceQuality(
            is_stale=False,
            age_seconds=None,
            has_confidence_measure=False,
            confidence_scale=None,
            provider_type="numerical_weather_prediction_or_reanalysis",
        )

        return EvidenceItem(
            id=f"ev-env-unavailable-{uuid4().hex[:8]}",
            category=EvidenceCategory.ENVIRONMENTAL,
            source_name="environmental_service",
            status=EvidenceStatus.UNAVAILABLE,
            observation_timestamp=datetime.now(timezone.utc),
            location=None,
            raw_value={"error": reason},
            confidence=None,
            quality=quality,
            provenance={"reason": reason},
            caveats=["Environmental data provider was unreachable; weather factors excluded."],
        )

    @classmethod
    def create_geospatial_evidence(
        cls,
        summary_dict: Dict[str, Any],
        features_count: int,
        source: str,
        location: Optional[CoordinateLocation] = None,
        missing_layers: Optional[List[str]] = None,
    ) -> EvidenceItem:
        """
        Constructs a verified Geospatial Context EvidenceItem.
        """
        quality = EvidenceQuality(
            is_stale=False,
            age_seconds=None,
            has_confidence_measure=False,
            confidence_scale=None,
            provider_type="gis_spatial_catalog",
        )

        provenance = {
            "spatial_source": source,
            "total_features_found": features_count,
            "missing_layers": missing_layers or [],
        }

        caveats = [
            "Proximity to features reflects static geographic adjacency only and does NOT simulate hazard propagation.",
            "Absence of nearby features in the catalog does not guarantee absence in the real physical world.",
            "Fire station and emergency facility layers are known to have partial national completeness.",
        ]

        return EvidenceItem(
            id=f"ev-geo-{uuid4().hex[:8]}",
            category=EvidenceCategory.GEOSPATIAL_CONTEXT,
            source_name=source,
            status=EvidenceStatus.VALID,
            observation_timestamp=datetime.now(timezone.utc),
            location=location,
            raw_value=summary_dict,
            confidence=None,
            quality=quality,
            provenance=provenance,
            caveats=caveats,
        )

    @classmethod
    def create_satellite_evidence(
        cls,
        satellite_data: Dict[str, Any],
        source_name: str = "MODIS_VIIRS_Thermal_Anomaly",
        observation_time: Optional[datetime] = None,
        location: Optional[CoordinateLocation] = None,
        brightness_temp_k: Optional[float] = None,
        frp_mw: Optional[float] = None,
    ) -> EvidenceItem:
        """
        Constructs a verified Satellite Thermal Radiometer EvidenceItem.
        """
        is_stale, age_seconds = cls.evaluate_freshness(
            observation_time, EvidenceCategory.SATELLITE_OBSERVATION
        )
        status = EvidenceStatus.STALE if is_stale else EvidenceStatus.VALID
        quality = EvidenceQuality(
            is_stale=is_stale,
            age_seconds=age_seconds,
            has_confidence_measure=True,
            confidence_scale="detection_confidence_pct [0, 100]",
            provider_type="satellite_radiometer_thermal_sensor",
        )
        provenance = {
            "sensor": source_name,
            "brightness_temperature_k": brightness_temp_k,
            "fire_radiative_power_mw": frp_mw,
            "payload": satellite_data,
        }
        caveats = [
            "Satellite thermal anomaly indicates radiative heat signature at sensor footprint scale (375m - 1km).",
            "Cloud cover, solar glint, or industrial flares may cause false negatives or false positives.",
        ]
        conf_val = satellite_data.get("confidence", 0.90)
        if isinstance(conf_val, (int, float)) and conf_val > 1.0:
            conf_val = conf_val / 100.0

        return EvidenceItem(
            id=f"ev-sat-{uuid4().hex[:8]}",
            category=EvidenceCategory.SATELLITE_OBSERVATION,
            source_name=source_name,
            status=status,
            observation_timestamp=observation_time or datetime.now(timezone.utc),
            location=location,
            raw_value=satellite_data,
            confidence=conf_val,
            quality=quality,
            provenance=provenance,
            caveats=caveats,
        )

    @classmethod
    def create_field_evidence(
        cls,
        report_data: Dict[str, Any],
        source_name: str = "Ground_Emergency_Personnel",
        observation_time: Optional[datetime] = None,
        location: Optional[CoordinateLocation] = None,
        is_confirmed: bool = True,
    ) -> EvidenceItem:
        """
        Constructs a verified Ground Field Observation EvidenceItem.
        """
        is_stale, age_seconds = cls.evaluate_freshness(
            observation_time, EvidenceCategory.FIELD_REPORT
        )
        status = EvidenceStatus.STALE if is_stale else EvidenceStatus.VALID
        quality = EvidenceQuality(
            is_stale=is_stale,
            age_seconds=age_seconds,
            has_confidence_measure=False,
            confidence_scale=None,
            provider_type="field_responder_observation",
        )
        provenance = {
            "reporter_type": source_name,
            "is_confirmed": is_confirmed,
            "payload": report_data,
        }
        caveats = [
            "Ground field observation represents on-scene human or sensor confirmation.",
            "Local observations may be subject to human observer bias or limited spatial visibility.",
        ]
        return EvidenceItem(
            id=f"ev-fld-{uuid4().hex[:8]}",
            category=EvidenceCategory.FIELD_REPORT,
            source_name=source_name,
            status=status,
            observation_timestamp=observation_time or datetime.now(timezone.utc),
            location=location,
            raw_value=report_data,
            confidence=1.0 if is_confirmed else 0.5,
            quality=quality,
            provenance=provenance,
            caveats=caveats,
        )
