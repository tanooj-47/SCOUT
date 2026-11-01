"""
backend/app/api/v1/endpoints/intelligence.py
FastAPI route controllers for SCOUT Multimodal Disaster Intelligence (Milestone 11).
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import SCOUTException
from app.db.session import get_db
from app.intelligence.schemas import (
    IncidentObservationInput,
    IntelligenceHealthResponse,
    MultimodalIntelligenceAssessment,
)
from app.intelligence.service import MultimodalIntelligenceService
from app.schemas.incident import DisasterType
from app.services.media_service import detect_image_format_magic

logger = logging.getLogger(__name__)

router = APIRouter()
intelligence_service = MultimodalIntelligenceService()


@router.get(
    "/health",
    response_model=IntelligenceHealthResponse,
    summary="Intelligence Engine Health & Subsystem Readiness",
    status_code=status.HTTP_200_OK,
)
def get_intelligence_health(db: Optional[Session] = Depends(get_db)) -> IntelligenceHealthResponse:
    """
    Returns operational readiness across the computer vision champion model,
    atmospheric weather provider, and geospatial catalog.
    """
    return intelligence_service.get_health(db=db)


@router.get(
    "/capabilities",
    summary="Intelligence Engine Capabilities & Limitations",
    status_code=status.HTTP_200_OK,
)
def get_intelligence_capabilities() -> Dict[str, Any]:
    """
    Exposes supported hazard categories, calibrated modalities, and scientific constraints.
    """
    return intelligence_service.get_capabilities()


@router.post(
    "/analyze",
    response_model=MultimodalIntelligenceAssessment,
    summary="Analyze Incident Observation (JSON Payload)",
    status_code=status.HTTP_200_OK,
)
def analyze_observation_endpoint(
    observation: IncidentObservationInput,
    db: Optional[Session] = Depends(get_db),
) -> MultimodalIntelligenceAssessment:
    """
    Executes an explainable multimodal analysis combining computer vision,
    environmental weather/FWI data, and geographic exposure context.
    """
    try:
        return intelligence_service.analyze_observation(
            observation=observation,
            image_bytes=None,
            db=db,
        )
    except SCOUTException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Intelligence observation analysis failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Intelligence analysis encountered an unexpected error: {str(exc)}",
        ) from exc


@router.post(
    "/analyze-with-image",
    response_model=MultimodalIntelligenceAssessment,
    summary="Analyze Incident Observation with Uploaded Imagery (Multipart Form)",
    status_code=status.HTTP_200_OK,
)
def analyze_with_image_endpoint(
    latitude: float = Form(..., ge=-90.0, le=90.0, description="Latitude [-90.0, 90.0]"),
    longitude: float = Form(..., ge=-180.0, le=180.0, description="Longitude [-180.0, 180.0]"),
    disaster_type: DisasterType = Form(default=DisasterType.WILDFIRE, description="Disaster category"),
    search_radius_meters: float = Form(default=5000.0, ge=100.0, le=100000.0, description="Search radius in meters"),
    source_description: str = Form(default="field_camera", description="Observation source"),
    image: Optional[UploadFile] = File(None, description="Optional raster image file (JPEG, PNG, WebP)"),
    db: Optional[Session] = Depends(get_db),
) -> MultimodalIntelligenceAssessment:
    """
    Accepts multipart form data with image file upload for direct field observation evaluation.
    Enforces chunked streaming validation against MAX_UPLOAD_SIZE_BYTES (10MB) and magic header checks.
    """
    image_bytes: Optional[bytes] = None
    if image is not None:
        chunk_size = 64 * 1024  # 64 KB chunks
        max_bytes = settings.MAX_UPLOAD_SIZE_BYTES
        total_bytes = 0
        buf = bytearray()
        initial_sniff_format: Optional[str] = None

        try:
            while True:
                chunk = image.file.read(chunk_size)
                if not chunk:
                    break

                if total_bytes == 0:
                    header = chunk[:12]
                    initial_sniff_format = detect_image_format_magic(header)
                    if initial_sniff_format is None:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Unsupported image format signature. Must be valid JPEG, PNG, or WebP raster imagery.",
                        )

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Image upload size exceeds {max_bytes} bytes limit (received {total_bytes} bytes).",
                    )
                buf.extend(chunk)

                if len(chunk) < chunk_size:
                    break

            if total_bytes == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded image file is empty (0 bytes).",
                )

            image_bytes = bytes(buf)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not read uploaded image file: {str(exc)}",
            ) from exc

    # Defensively unwrap Form defaults if called directly in tests outside FastAPI injection
    resolved_radius = (
        search_radius_meters.default
        if hasattr(search_radius_meters, "default")
        else search_radius_meters
    )
    resolved_source = (
        source_description.default
        if hasattr(source_description, "default")
        else source_description
    )
    resolved_type = (
        disaster_type.default
        if hasattr(disaster_type, "default")
        else disaster_type
    )

    obs = IncidentObservationInput(
        disaster_type=resolved_type,
        latitude=latitude,
        longitude=longitude,
        search_radius_meters=resolved_radius,
        source_description=resolved_source,
    )

    try:
        return intelligence_service.analyze_observation(
            observation=obs,
            image_bytes=image_bytes,
            db=db,
        )
    except SCOUTException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Intelligence multipart observation analysis failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Intelligence analysis encountered an unexpected error: {str(exc)}",
        ) from exc
