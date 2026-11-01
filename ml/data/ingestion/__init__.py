"""SCOUT Dataset Ingestion & Validation Package.

Provides modular tools for source acquisition, archive extraction, image validation,
metadata profiling, perceptual hashing, deduplication, and scene grouping.
"""

from ml.data.ingestion.archive_extractor import SafeArchiveExtractor, extract_archive_safely
from ml.data.ingestion.hasher import (
    compute_sha256,
    compute_dhash,
    compute_ahash,
    hamming_distance,
    hash_hex_to_int,
)
from ml.data.ingestion.image_validator import (
    ValidationResult,
    validate_image_file,
    sanitize_and_save_image,
)
from ml.data.ingestion.metadata_extractor import ImageMetadata, extract_image_metadata
from ml.data.ingestion.scene_grouper import SceneGrouper, SceneGroup

__all__ = [
    "SafeArchiveExtractor",
    "extract_archive_safely",
    "compute_sha256",
    "compute_dhash",
    "compute_ahash",
    "hamming_distance",
    "hash_hex_to_int",
    "ValidationResult",
    "validate_image_file",
    "sanitize_and_save_image",
    "ImageMetadata",
    "extract_image_metadata",
    "SceneGrouper",
    "SceneGroup",
]
