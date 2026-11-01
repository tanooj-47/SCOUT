"""
backend/app/geospatial/acquisition/manifest.py
Machine-readable provenance and audit manifest schema for national geospatial datasets.
"""

from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AcquisitionState(str, Enum):
    SOURCE_DISCOVERED = "source_discovered"
    ACCESS_VERIFIED = "access_verified"
    DOWNLOAD_COMPLETED = "download_completed"
    CHECKSUM_VERIFIED = "checksum_verified"
    DATA_VALIDATED = "data_validated"
    PROCESSED_SUCCESSFULLY = "processed_successfully"
    INGESTED_INTO_STORAGE = "ingested_into_storage"


class ProcessingStatus(str, Enum):
    RAW = "raw"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    READY_FOR_INGESTION = "ready_for_ingestion"
    INGESTED = "ingested"
    RESTRICTED = "restricted"


class ValidationStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    INVALID = "invalid"


class DatasetManifest(BaseModel):
    """
    Standard metadata manifest recorded for every acquired national geographic dataset.
    Preserves upstream licensing, provenance, checksums, and operational boundaries.
    """
    dataset_id: str = Field(..., description="Unique slug for dataset (e.g. osm_india_pbf_latest)")
    dataset_name: str = Field(..., description="Human-readable title")
    provider: str = Field(..., description="Organization or service providing data")
    official_source_url: str = Field(..., description="Documentation or catalog URL")
    download_url: Optional[str] = Field(None, description="Direct download URL if available")
    product_name: str = Field(..., description="Specific product identifier")
    product_version: str = Field(..., description="Version or release epoch")
    acquisition_state: AcquisitionState = Field(default=AcquisitionState.SOURCE_DISCOVERED)
    acquisition_timestamp_utc: Optional[str] = Field(None, description="ISO 8601 UTC timestamp of acquisition")
    source_publication_date: Optional[str] = Field(None, description="Publication date from upstream source")
    reference_period: Optional[str] = Field(None, description="Observation or validity time period")
    geographic_coverage: str = Field(..., description="Geographic extent (e.g. 'India-wide (national)')")
    license: str = Field(..., description="Data license (e.g. 'ODbL-1.0', 'CC-BY-4.0')")
    attribution: str = Field(..., description="Mandatory attribution string")
    original_filename: str = Field(..., description="Filename as published by upstream provider")
    file_format: str = Field(..., description="Format (e.g. 'osm.pbf', 'geotiff', 'geojson', 'csv')")
    file_size_bytes: Optional[int] = Field(None, description="Exact file size in bytes")
    sha256: Optional[str] = Field(None, description="SHA-256 hexadecimal hash")
    md5: Optional[str] = Field(None, description="MD5 hash if supplied by provider")
    crs: str = Field(default="EPSG:4326", description="Coordinate Reference System")
    spatial_resolution: Optional[str] = Field(None, description="Spatial resolution (e.g. '10m', '30m', 'vector')")
    temporal_resolution: Optional[str] = Field(None, description="Temporal frequency if time-series")
    coordinate_bounds: List[float] = Field(default_factory=list, description="[min_lon, min_lat, max_lon, max_lat]")
    nodata_value: Optional[Any] = Field(None, description="Nodata value for rasters")
    processing_status: ProcessingStatus = Field(default=ProcessingStatus.RAW)
    validation_status: ValidationStatus = Field(default=ValidationStatus.UNVALIDATED)
    quality_notes: List[str] = Field(default_factory=list)
    operational_use_restrictions: Optional[str] = Field(None, description="Legal or operational restrictions")
    metadata_payload: Dict[str, Any] = Field(default_factory=dict)

    def save_to_directory(self, target_dir: Path) -> Path:
        """Saves manifest as formatted JSON in target directory."""
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{self.dataset_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2, sort_keys=False)
        return file_path

    @classmethod
    def load_from_file(cls, file_path: Path) -> "DatasetManifest":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
