"""
backend/app/geospatial/acquisition/__init__.py
National Geographic Data Acquisition Subsystem.
"""

from app.geospatial.acquisition.manifest import (
    AcquisitionState,
    DatasetManifest,
    ProcessingStatus,
    ValidationStatus,
)
from app.geospatial.acquisition.downloader import (
    DownloadError,
    DownloadResult,
    InsufficientDiskSpaceError,
    ResumableDownloader,
    check_available_disk_space,
    compute_file_checksums,
)

__all__ = [
    "AcquisitionState",
    "DatasetManifest",
    "ProcessingStatus",
    "ValidationStatus",
    "DownloadError",
    "DownloadResult",
    "InsufficientDiskSpaceError",
    "ResumableDownloader",
    "check_available_disk_space",
    "compute_file_checksums",
]
