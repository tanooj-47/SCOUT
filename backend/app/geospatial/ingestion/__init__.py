"""
backend/app/geospatial/ingestion/__init__.py
Geospatial ingestion subsystem.
"""

from app.geospatial.ingestion.schemas import (
    ConflictPolicy,
    IngestionOptions,
    IngestionRunSummary,
    IngestionStatus,
    NormalizedFeature,
    SourceRegistrationCreate,
    SourceRegistrationResponse,
)
from app.geospatial.ingestion.normalizer import (
    infer_feature_category,
    infer_hazard_relevance,
    normalize_feature,
    validate_and_transform_geometry,
    FeatureNormalizationError,
)
from app.geospatial.ingestion.pipeline import (
    GeospatialIngestionPipeline,
    GeospatialIngestionError,
)

__all__ = [
    "ConflictPolicy",
    "IngestionOptions",
    "IngestionRunSummary",
    "IngestionStatus",
    "NormalizedFeature",
    "SourceRegistrationCreate",
    "SourceRegistrationResponse",
    "infer_feature_category",
    "infer_hazard_relevance",
    "normalize_feature",
    "validate_and_transform_geometry",
    "FeatureNormalizationError",
    "GeospatialIngestionPipeline",
    "GeospatialIngestionError",
]
