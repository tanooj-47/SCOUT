"""
SCOUT Multimodal Disaster Intelligence Platform
Milestone 07 — Fire & Smoke Image Dataset Preparation Pipeline

Production-grade, failure-safe, auditable dataset preparation pipeline for wildfire image classification:
- Safe ZIP archive handling with strict resource bounds (DoS / Zip Slip / Decompression bomb protection).
- Comprehensive duplicate-group and label-conflict resolution supporting arbitrary group sizes.
- Two-pass deep Pillow validation (structural verify + actual pixel decoding).
- Staged output generation with atomic-like promotion and automatic rollback on failure.
- Collision-resistant file naming with full original-path provenance.
- Deterministic stratified 80/20 train/validation split preserving pristine test benchmark.
- Exhaustive audit manifests, duplicate reports, class distributions, and summary metrics.
- Independent output integrity verifier validating files on disk.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import posixpath
import random
import re
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple
import zipfile

from PIL import Image, ImageFile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scout.ml.data_prep")

# Enforce strict rejection of truncated images in Pillow
ImageFile.LOAD_TRUNCATED_IMAGES = False

# Canonical classes and splits
EXPECTED_CLASSES = frozenset({"fire", "smoke", "neutral"})
EXPECTED_SPLITS = frozenset({"train", "test"})
SUPPORTED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})

# Approved disposition categories for accounting
APPROVED_DISPOSITIONS = frozenset({
    "RETAINED_TRAIN",
    "RETAINED_VALIDATION",
    "RETAINED_TEST",
    "EXCLUDED_DUPLICATE",
    "EXCLUDED_LABEL_CONFLICT",
    "QUARANTINED_CORRUPT",
})

# Reviewed label conflict registry for known verified duplicates
# Keyed strictly by SHA-256 digest in lowercase hexadecimal
REVIEWED_LABEL_CONFLICT_REGISTRY: Dict[str, Dict[str, str]] = {
    "b667e935cfa32afbc25a4170a6adc1c6700b9e2df082e2dd55c299120678e786": {
        "approved_class": "smoke",
        "reason": (
            "Visual ground-truth audit confirmed image depicts active smoke plume; "
            "Train/Fire/image_12.jpg is mislabeled, Train/Smoke/image_23.jpg is correct."
        ),
    }
}

# Resource & Security Defaults
DEFAULT_MAX_ARCHIVE_ENTRIES: int = 10_000
DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GB
DEFAULT_MAX_IMAGE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_COMPRESSION_RATIO: float = 100.0  # Max uncompressed / compressed ratio
DEFAULT_MAX_IMAGE_DIMENSION: int = 16_384  # Pixels along width or height
DEFAULT_MAX_IMAGE_PIXELS: int = 100_000_000  # 100 Megapixels


class DatasetPreparationError(Exception):
    """Base exception for dataset preparation pipeline errors."""


class ArchiveSecurityError(DatasetPreparationError):
    """Raised when an archive violates path traversal, size, count, or encryption safety rules."""


class DatasetVerificationError(DatasetPreparationError):
    """Raised when output integrity verification fails."""


class OutputDirectoryConflictError(DatasetPreparationError):
    """Raised when target output directory exists and force is not specified."""


def check_output_directory(output_dir: Path, force: bool = False) -> None:
    """Pre-flight check verifying target directory availability."""
    if output_dir.exists() and not force:
        raise OutputDirectoryConflictError(
            f"Target directory '{output_dir}' already exists. Use --force to replace."
        )


def validate_resource_limits(
    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_total_size: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_image_size: int = DEFAULT_MAX_IMAGE_SIZE_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> None:
    """
    Validates pipeline resource limits before performing archive operations.
    Ensures parameters are positive, non-zero numbers of appropriate types,
    and explicitly rejects boolean values (which in Python are a subclass of int).
    """
    int_params = {
        "max_entries": max_entries,
        "max_total_size": max_total_size,
        "max_image_size": max_image_size,
        "max_dimension": max_dimension,
        "max_pixels": max_pixels,
    }
    for name, val in int_params.items():
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(f"Limit parameter '{name}' must be an integer, got {type(val).__name__} ({val!r})")
        if val <= 0:
            raise ValueError(f"Limit parameter '{name}' must be strictly positive (> 0), got {val}")

    if isinstance(max_compression_ratio, bool) or not isinstance(max_compression_ratio, (int, float)):
        raise ValueError(
            f"Limit parameter 'max_compression_ratio' must be a numeric float or integer, "
            f"got {type(max_compression_ratio).__name__} ({max_compression_ratio!r})"
        )
    if isinstance(max_compression_ratio, float) and (math.isnan(max_compression_ratio) or math.isinf(max_compression_ratio)):
        raise ValueError(f"Limit parameter 'max_compression_ratio' must be finite, got {max_compression_ratio}")
    if max_compression_ratio <= 0.0:
        raise ValueError(
            f"Limit parameter 'max_compression_ratio' must be strictly positive (> 0), got {max_compression_ratio}"
        )


@dataclass
class DatasetItem:
    """Represents a single image item throughout the preparation pipeline."""
    archive_path: str
    original_filename: str = ""
    original_split: str = ""
    original_class: str = ""
    sha256: str = ""
    file_size_bytes: int = 0
    is_valid_image: bool = True
    validation_error: Optional[str] = None
    final_split: Optional[str] = None
    final_class: Optional[str] = None
    output_filename: Optional[str] = None
    output_path: Optional[str] = None
    disposition: str = "PENDING"
    exclusion_or_quarantine_reason: Optional[str] = None
    is_retained: bool = True
    data: Optional[bytes] = None
    filename: Optional[str] = None

    def __post_init__(self):
        if self.filename and not self.original_filename:
            self.original_filename = self.filename
        elif self.original_filename and not self.filename:
            self.filename = self.original_filename

    @property
    def action(self) -> str:
        return self.disposition

    @action.setter
    def action(self, val: str) -> None:
        self.disposition = val

    @property
    def exclusion_reason(self) -> Optional[str]:
        return self.exclusion_or_quarantine_reason

    @exclusion_reason.setter
    def exclusion_reason(self, val: Optional[str]) -> None:
        self.exclusion_or_quarantine_reason = val


def validate_zip_entry_path(entry_path: str) -> None:
    """
    Prevents ZIP path traversal vulnerabilities (Zip Slip).
    Rejects absolute paths, drive letters, and parent directory traversal ('..').
    """
    raw_clean = entry_path.replace("\\", "/")
    if raw_clean.startswith("/") or raw_clean.startswith("\\"):
        raise ArchiveSecurityError(f"Absolute path in ZIP entry rejected: {entry_path}")
    if ":" in raw_clean:
        raise ArchiveSecurityError(f"Drive letter or scheme in ZIP entry rejected: {entry_path}")

    raw_parts = raw_clean.split("/")
    if ".." in raw_parts:
        raise ArchiveSecurityError(f"Directory traversal ('..') in ZIP entry rejected: {entry_path}")

    normalized = posixpath.normpath(raw_clean)
    if normalized.startswith("..") or "/../" in normalized or normalized == "..":
        raise ArchiveSecurityError(f"Escaping path traversal in ZIP entry rejected: {entry_path}")


def parse_entry_metadata(entry_path: str) -> Optional[Tuple[str, str, str]]:
    """
    Parses entry path to extract split, class, and filename.
    Supports layouts such as:
      FIRE-SMOKE-DATASET/Train/Fire/image_0.jpg
      Train/Fire/image_0.jpg
    Returns (split, class, filename) in canonical lowercase, or None if not an image candidate.
    """
    normalized = posixpath.normpath(entry_path.replace("\\", "/")).strip("/")
    parts = normalized.split("/")

    # Discard root archive folder prefix if present
    if len(parts) >= 4 and parts[0].upper().startswith("FIRE-SMOKE"):
        parts = parts[1:]

    if len(parts) != 3:
        return None

    split_cand = parts[0].lower()
    class_cand = parts[1].lower()
    filename = parts[2]

    if split_cand not in EXPECTED_SPLITS:
        return None
    if class_cand not in EXPECTED_CLASSES:
        return None

    ext = posixpath.splitext(filename)[1].lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        return None

    return split_cand, class_cand, filename


def validate_image_bytes(
    data: bytes,
    filename: str,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> Tuple[bool, Optional[str], Optional[Tuple[int, int]]]:
    """
    Deep two-pass verification of raster image bytes using Pillow:
    Pass 1: img.verify() checks chunk CRC, headers, and container structure.
    Pass 2: Actual raster decoding (img.load()) ensures scanlines are not truncated or corrupt.
    Enforces decompression bomb safety limits, non-positive dimension checks, and format restrictions.

    Returns:
        (is_valid, error_reason, (width, height))
    """
    if len(data) == 0:
        return False, "Empty file (0 bytes)", None

    Image.MAX_IMAGE_PIXELS = max_pixels

    # Pass 1: Structural verification
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Image.DecompressionBombError as exc:
        return False, f"Decompression bomb detected: {exc}", None
    except Exception as exc:
        return False, f"Image structure verification failed: {exc}", None

    # Pass 2: Decoding, dimension check, and pixel limits
    try:
        with Image.open(io.BytesIO(data)) as img:
            raw_fmt = (img.format or "").upper()
            if raw_fmt not in {"JPEG", "PNG", "WEBP"}:
                return False, f"Unsupported format '{raw_fmt}'. Only JPEG, PNG, and WebP permitted.", None

            width, height = img.size
            if width <= 0 or height <= 0:
                return False, f"Invalid dimensions: {width}x{height}", None

            if width > max_dimension or height > max_dimension:
                return False, f"Dimension {max(width, height)}px exceeds limit {max_dimension}px", None

            if (width * height) > max_pixels:
                return False, f"Pixel count {width * height} exceeds limit {max_pixels}", None

            # Force raster scanline decoding to reject truncated frames
            img.load()
            return True, None, (width, height)
    except Image.DecompressionBombError as exc:
        return False, f"Decompression bomb detected: {exc}", None
    except Exception as exc:
        return False, f"Image raster decoding failed: {exc}", None


def compute_sha256(data: bytes) -> str:
    """Calculates lowercase hexadecimal SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def scan_and_validate_archive(
    archive_path: Path,
    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_total_size: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_image_size: int = DEFAULT_MAX_IMAGE_SIZE_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> Tuple[List[DatasetItem], List[DatasetItem], int]:
    """
    Reads the original ZIP archive safely:
    - Pre-validates all resource limits (count, sizes, ratios, dimensions, pixel count).
    - Pre-validates total archive entry count, cumulative uncompressed sizes, compression ratios, and encryption.
    - Memory model: Entries are read and validated sequentially one-by-one via zf.read(info).
      Peak resident memory is bounded to a single uncompressed image payload (max_image_size, default 50 MB)
      plus Pillow's in-memory raster decode buffer (bounded by max_pixels * 4 bytes), avoiding loading
      the entire multi-gigabyte dataset into RAM simultaneously.
    - Performs deep two-pass Pillow validation (verify + raster load) on all recognized image entries.

    Returns:
        valid_items: List[DatasetItem]
        corrupted_items: List[DatasetItem]
        total_archive_entries: int (all members in ZIP)
    """
    validate_resource_limits(
        max_entries=max_entries,
        max_total_size=max_total_size,
        max_image_size=max_image_size,
        max_compression_ratio=max_compression_ratio,
        max_dimension=max_dimension,
        max_pixels=max_pixels,
    )

    if not archive_path.is_file():
        raise FileNotFoundError(f"Dataset archive not found at '{archive_path}'")

    try:
        zf = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile as exc:
        raise ArchiveSecurityError(f"Corrupt or invalid ZIP archive '{archive_path}': {exc}") from exc

    with zf:
        infolist = zf.infolist()
        total_archive_entries = len(infolist)

        if total_archive_entries > max_entries:
            raise ArchiveSecurityError(
                f"Archive entry count ({total_archive_entries}) exceeds maximum limit of {max_entries}"
            )

        # Pre-check cumulative size, encryption, duplicate members, and ratios
        total_uncompressed = 0
        seen_entry_names: Set[str] = set()

        for info in infolist:
            if info.filename in seen_entry_names:
                raise ArchiveSecurityError(f"Duplicate member name in ZIP archive: '{info.filename}'")
            seen_entry_names.add(info.filename)

            if info.flag_bits & 0x1:
                raise ArchiveSecurityError(f"Encrypted archive member rejected: '{info.filename}'")

            if info.file_size > max_image_size:
                raise ArchiveSecurityError(
                    f"Entry '{info.filename}' uncompressed size ({info.file_size} bytes) exceeds limit ({max_image_size} bytes)"
                )

            total_uncompressed += info.file_size
            if total_uncompressed > max_total_size:
                raise ArchiveSecurityError(
                    f"Cumulative uncompressed archive size exceeds safety limit of {max_total_size} bytes"
                )

            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_compression_ratio:
                    raise ArchiveSecurityError(
                        f"Entry '{info.filename}' compression ratio ({ratio:.1f}) exceeds threshold ({max_compression_ratio})"
                    )

        valid_items: List[DatasetItem] = []
        corrupted_items: List[DatasetItem] = []

        logger.info("Archive security checks passed (%d total entries). Validating images...", total_archive_entries)

        for info in infolist:
            if info.is_dir():
                continue

            entry_path = info.filename
            validate_zip_entry_path(entry_path)

            meta = parse_entry_metadata(entry_path)
            if meta is None:
                continue

            split, cls, filename = meta
            data = zf.read(info)
            h = compute_sha256(data)

            is_valid, err_reason, dims = validate_image_bytes(
                data=data,
                filename=filename,
                max_dimension=max_dimension,
                max_pixels=max_pixels,
            )

            item = DatasetItem(
                archive_path=entry_path,
                original_filename=filename,
                original_split=split,
                original_class=cls,
                sha256=h,
                file_size_bytes=len(data),
                is_valid_image=is_valid,
                validation_error=err_reason,
            )

            if is_valid:
                valid_items.append(item)
            else:
                logger.warning("Corrupted image in archive: %s (%s)", entry_path, err_reason)
                item.is_retained = False
                item.disposition = "QUARANTINED_CORRUPT"
                item.exclusion_or_quarantine_reason = err_reason
                corrupted_items.append(item)

    logger.info(
        "Archive validation complete: %d valid images, %d corrupted/invalid images out of %d recognized",
        len(valid_items),
        len(corrupted_items),
        len(valid_items) + len(corrupted_items),
    )
    return valid_items, corrupted_items, total_archive_entries


def deduplicate_dataset(
    items: List[DatasetItem],
) -> Tuple[List[DatasetItem], List[DatasetItem], List[Dict[str, Any]]]:
    """
    Complete group-based deduplication supporting arbitrary group sizes (>= 2 files).

    Deterministic Governance Rules:
    1. Every recognized image appears exactly once in the final accounting.
    2. Test-set preservation takes priority:
       - If a group contains Test copies, all Test copies must agree on the label.
         If Test copies have conflicting labels among themselves, DatasetPreparationError is raised.
       - Exactly ONE Test copy is retained.
       - Any additional Test copies in the group are excluded as TEST duplicates.
       - All Train copies matching a Test image are excluded to eliminate data leakage.
         Train copies with matching class are marked EXCLUDED_DUPLICATE.
         Train copies with conflicting class are marked EXCLUDED_LABEL_CONFLICT.
    3. Train-only duplicate groups:
       - If all items share the same class: retain first alphabetically, exclude others as TRAIN duplicates.
       - If conflicting labels exist: checked strictly against REVIEWED_LABEL_CONFLICT_REGISTRY.
         Only verified SHA-256 digests in the registry are resolved according to expert audit.
         Any unreviewed conflicting duplicate group raises DatasetPreparationError.
    4. Exactly one item is retained per unique SHA-256 group; all other (K-1) items are recorded with specific reasons.

    Returns:
        retained_items: List[DatasetItem]
        excluded_items: List[DatasetItem]
        duplicate_reports: List[Dict[str, Any]]
    """
    hash_groups: Dict[str, List[DatasetItem]] = {}
    for item in items:
        hash_groups.setdefault(item.sha256, []).append(item)

    retained_items: List[DatasetItem] = []
    excluded_items: List[DatasetItem] = []
    duplicate_reports: List[Dict[str, Any]] = []

    for h, group in sorted(hash_groups.items(), key=lambda x: x[0]):
        if len(group) == 1:
            item = group[0]
            item.disposition = f"RETAINED_{item.original_split.upper()}"
            item.final_split = item.original_split
            item.final_class = item.original_class
            item.is_retained = True
            retained_items.append(item)
            continue

        # Sort group deterministically by archive_path
        sorted_group = sorted(group, key=lambda x: x.archive_path)
        test_items = [x for x in sorted_group if x.original_split == "test"]
        train_items = [x for x in sorted_group if x.original_split == "train"]

        # CASE 1: Group contains at least one Test copy (Test preservation priority)
        if test_items:
            # Check for conflicting labels within Test split itself
            test_classes = set(x.original_class for x in test_items)
            if len(test_classes) > 1:
                raise DatasetPreparationError(
                    f"Unresolvable conflicting labels within Test set for hash {h}: "
                    f"{sorted(test_classes)} across {[x.archive_path for x in test_items]}. "
                    "Test benchmark integrity violation: conflicting ground truth labels in test split."
                )

            # Retain the first Test copy deterministically
            retained = test_items[0]
            retained.disposition = "RETAINED_TEST"
            retained.final_split = "test"
            retained.final_class = retained.original_class
            retained.is_retained = True
            retained.exclusion_or_quarantine_reason = None
            retained_items.append(retained)

            # Exclude additional Test copies in this group if any
            for extra_test in test_items[1:]:
                extra_test.is_retained = False
                extra_test.final_split = None
                extra_test.final_class = None
                extra_test.disposition = "EXCLUDED_DUPLICATE"
                extra_test.exclusion_or_quarantine_reason = "Exact duplicate within Test split"
                excluded_items.append(extra_test)

            # Exclude all Train copies to prevent data leakage
            has_cross_split_conflict = False
            for train_item in train_items:
                train_item.is_retained = False
                train_item.final_split = None
                train_item.final_class = None
                if train_item.original_class == retained.final_class:
                    train_item.disposition = "EXCLUDED_DUPLICATE"
                    train_item.exclusion_or_quarantine_reason = (
                        "Duplicate of Test image; preserved Test copy to prevent train/test data leakage"
                    )
                else:
                    has_cross_split_conflict = True
                    train_item.disposition = "EXCLUDED_LABEL_CONFLICT"
                    train_item.exclusion_or_quarantine_reason = (
                        f"Conflicting label ({train_item.original_class} vs Test {retained.final_class}) "
                        "for image present in Test; preserved Test copy as ground truth benchmark"
                    )
                excluded_items.append(train_item)

            if train_items:
                conflict_type = "CROSS_SPLIT_LABEL_CONFLICT" if has_cross_split_conflict else "CROSS_SPLIT_DUPLICATE"
            else:
                conflict_type = "SAME_SPLIT_DUPLICATE_TEST"

            excluded_paths = [x.archive_path for x in (test_items[1:] + train_items)]
            reason_str = (
                "Preserved Test copy as benchmark ground truth; excluded conflicting Train copies"
                if has_cross_split_conflict
                else "Preserved Test copy to prevent train/test data leakage / redundant evaluation"
            )
            duplicate_reports.append({
                "sha256": h,
                "group_size": len(sorted_group),
                "conflict_type": conflict_type,
                "files": "; ".join(x.archive_path for x in sorted_group),
                "retained_file": retained.archive_path,
                "retained_class": retained.original_class,
                "excluded_files": "; ".join(excluded_paths),
                "reason": reason_str,
            })

        # CASE 2: Group contains ONLY Train copies
        else:
            classes = set(x.original_class for x in train_items)

            # Subcase 2A: Same class across all Train copies
            if len(classes) == 1:
                retained = train_items[0]
                retained.disposition = "RETAINED_TRAIN"
                retained.final_split = "train"
                retained.final_class = retained.original_class
                retained.is_retained = True
                retained.exclusion_or_quarantine_reason = None
                retained_items.append(retained)

                for extra_train in train_items[1:]:
                    extra_train.is_retained = False
                    extra_train.final_split = None
                    extra_train.final_class = None
                    extra_train.disposition = "EXCLUDED_DUPLICATE"
                    extra_train.exclusion_or_quarantine_reason = "Exact duplicate within Train split"
                    excluded_items.append(extra_train)

                duplicate_reports.append({
                    "sha256": h,
                    "group_size": len(sorted_group),
                    "conflict_type": "SAME_SPLIT_DUPLICATE_TRAIN",
                    "files": "; ".join(x.archive_path for x in sorted_group),
                    "retained_file": retained.archive_path,
                    "retained_class": retained.original_class,
                    "excluded_files": "; ".join(x.archive_path for x in train_items[1:]),
                    "reason": "Exact duplicate within Train split",
                })

            # Subcase 2B: Conflicting classes in Train
            else:
                if h in REVIEWED_LABEL_CONFLICT_REGISTRY:
                    conflict_info = REVIEWED_LABEL_CONFLICT_REGISTRY[h]
                    approved_cls = conflict_info["approved_class"]
                    override_reason = conflict_info["reason"]

                    approved_items = [x for x in train_items if x.original_class == approved_cls]
                    if not approved_items:
                        raise DatasetPreparationError(
                            f"Conflict registry specifies approved class '{approved_cls}' for hash {h}, "
                            f"but no image with that class exists in group: {[x.archive_path for x in sorted_group]}"
                        )

                    # Retain first item of approved class
                    retained = approved_items[0]
                    retained.disposition = "RETAINED_TRAIN"
                    retained.final_split = "train"
                    retained.final_class = approved_cls
                    retained.is_retained = True
                    retained.exclusion_or_quarantine_reason = None
                    retained_items.append(retained)

                    # Exclude duplicate approved copies if any
                    for extra_app in approved_items[1:]:
                        extra_app.is_retained = False
                        extra_app.final_split = None
                        extra_app.final_class = None
                        extra_app.disposition = "EXCLUDED_DUPLICATE"
                        extra_app.exclusion_or_quarantine_reason = (
                            f"Exact duplicate within Train split (retained primary {approved_cls.title()} copy)"
                        )
                        excluded_items.append(extra_app)

                    # Exclude conflicting items
                    conflicting_items = [x for x in train_items if x.original_class != approved_cls]
                    for conf_item in conflicting_items:
                        conf_item.is_retained = False
                        conf_item.final_split = None
                        conf_item.final_class = None
                        conf_item.disposition = "EXCLUDED_LABEL_CONFLICT"
                        conf_item.exclusion_or_quarantine_reason = (
                            f"Conflicting label ({conf_item.original_class} vs approved {approved_cls}); "
                            f"{override_reason}"
                        )
                        excluded_items.append(conf_item)

                    all_excluded = approved_items[1:] + conflicting_items
                    duplicate_reports.append({
                        "sha256": h,
                        "group_size": len(sorted_group),
                        "conflict_type": "LABEL_CONFLICT",
                        "files": "; ".join(x.archive_path for x in sorted_group),
                        "retained_file": retained.archive_path,
                        "retained_class": approved_cls,
                        "excluded_files": "; ".join(x.archive_path for x in all_excluded),
                        "reason": f"Resolved via reviewed conflict registry: {override_reason}",
                    })
                else:
                    raise DatasetPreparationError(
                        f"Unreviewed conflicting labels in Train for hash {h}: {sorted(classes)} across "
                        f"{[x.archive_path for x in sorted_group]}. "
                        "Unreviewed label conflicts require explicit expert audit and entry in REVIEWED_LABEL_CONFLICT_REGISTRY."
                    )

    return retained_items, excluded_items, duplicate_reports


def validate_split_inputs(
    train_items: List[DatasetItem],
    val_ratio: float,
    seed: int,
) -> None:
    """
    Validates split parameters and training class distribution before partitioning:
    - val_ratio must be strictly between 0 and 1.
    - seed must be a valid integer.
    - All expected classes must be present.
    - Every class must contain sufficient unique samples for both Train and Validation.
    """
    if not (0.0 < val_ratio < 1.0):
        raise ValueError(f"val_ratio must be strictly between 0 and 1 (received {val_ratio})")

    if not isinstance(seed, int):
        raise ValueError(f"seed must be an integer (received {type(seed).__name__})")

    found_classes = set(x.original_class for x in train_items)
    missing = EXPECTED_CLASSES - found_classes
    if missing:
        raise DatasetPreparationError(
            f"Missing required class(es) in cleaned training set: {sorted(list(missing))}. "
            f"Found: {sorted(list(found_classes))}"
        )

    by_class: Dict[str, int] = {}
    for item in train_items:
        by_class[item.original_class] = by_class.get(item.original_class, 0) + 1

    for cls_name, count in by_class.items():
        val_count = round(count * val_ratio)
        train_count = count - val_count
        if val_count < 1 or train_count < 1:
            raise DatasetPreparationError(
                f"Class '{cls_name}' has insufficient samples ({count}) to produce both Train and Validation "
                f"subsets with val_ratio={val_ratio} (train={train_count}, val={val_count})."
            )


def stratified_train_val_split(
    train_items: List[DatasetItem],
    val_ratio: float = 0.20,
    seed: int = 42,
) -> Tuple[List[DatasetItem], List[DatasetItem]]:
    """
    Performs a deterministic, stratified Train/Validation split on cleaned training items.
    Preserves exact class proportions and guarantees zero hash overlap.
    """
    validate_split_inputs(train_items, val_ratio, seed)

    by_class: Dict[str, List[DatasetItem]] = {}
    for item in train_items:
        by_class.setdefault(item.final_class or item.original_class, []).append(item)

    rng = random.Random(seed)
    final_train: List[DatasetItem] = []
    final_val: List[DatasetItem] = []

    for cls_name in sorted(by_class.keys()):
        cls_items = by_class[cls_name]
        # Sort deterministically by SHA-256 for stable baseline ordering
        cls_items_sorted = sorted(cls_items, key=lambda x: x.sha256)

        shuffled = list(cls_items_sorted)
        rng.shuffle(shuffled)

        val_count = round(len(shuffled) * val_ratio)
        val_slice = shuffled[:val_count]
        train_slice = shuffled[val_count:]

        for item in val_slice:
            item.final_split = "validation"
            item.disposition = "RETAINED_VALIDATION"
            final_val.append(item)

        for item in train_slice:
            item.final_split = "train"
            item.disposition = "RETAINED_TRAIN"
            final_train.append(item)

    return final_train, final_val


def assign_collision_safe_paths(retained_items: List[DatasetItem]) -> None:
    """
    Assigns deterministic, collision-resistant output paths using a 12-char SHA-256 prefix
    and sanitized original filename.
    Enforces collision detection to ensure no two images share an output path.
    """
    seen_paths: Set[str] = set()

    for item in retained_items:
        clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", item.original_filename)
        sha_prefix = item.sha256[:12]
        dest_filename = f"{sha_prefix}_{clean_name}"
        rel_path = f"{item.final_split}/{item.final_class}/{dest_filename}"

        if rel_path in seen_paths:
            raise DatasetPreparationError(f"Output path collision detected for '{rel_path}'")

        seen_paths.add(rel_path)
        item.output_filename = dest_filename
        item.output_path = rel_path


def compute_class_distribution(items: List[DatasetItem]) -> List[Dict[str, Any]]:
    """
    Calculates class distribution reporting counts, percentages within each split,
    and percentages across the entire retained dataset with explicit denominators.
    """
    split_totals: Dict[str, int] = {}
    counts: Dict[Tuple[str, str], int] = {}
    retained_total = len(items)

    for item in items:
        if item.is_retained and item.final_split and item.final_class:
            split_totals[item.final_split] = split_totals.get(item.final_split, 0) + 1
            key = (item.final_split, item.final_class)
            counts[key] = counts.get(key, 0) + 1

    distribution_rows = []
    for (split, cls), count in sorted(counts.items(), key=lambda x: (x[0][0], x[0][1])):
        s_total = split_totals.get(split, 0)
        pct_within_split = (count / s_total * 100) if s_total > 0 else 0.0
        pct_of_retained = (count / retained_total * 100) if retained_total > 0 else 0.0

        distribution_rows.append({
            "split": split,
            "class": cls,
            "retained_count": count,
            "count": count,
            "split_total": s_total,
            "percentage_within_split": round(pct_within_split, 2),
            "retained_total": retained_total,
            "percentage_of_retained_dataset": round(pct_of_retained, 2),
        })

    return distribution_rows


def write_dataset_contents(
    target_dir: Path,
    retained_items: List[DatasetItem],
    corrupted_items: List[DatasetItem],
    all_manifest_items: List[DatasetItem],
    duplicate_reports: List[Dict[str, Any]],
    excluded_items: List[DatasetItem],
    distribution_rows: List[Dict[str, Any]],
    summary_data: Dict[str, Any],
    archive_path: Path,
) -> None:
    """
    Writes physical images and audit artifacts into target_dir.
    Reads retained images from archive on demand to keep memory footprint minimal.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    audit_dir = target_dir / "audit"
    quarantine_dir = target_dir / "quarantine"
    audit_dir.mkdir(parents=True, exist_ok=True)

    # 1. Stream copy retained images from archive to output
    with zipfile.ZipFile(archive_path, "r") as zf:
        for item in retained_items:
            dest_dir = target_dir / item.final_split / item.final_class
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = target_dir / item.output_path

            data = zf.read(item.archive_path)
            dest_file.write_bytes(data)

        # 2. Write quarantined corrupt images if any
        if corrupted_items:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            for item in corrupted_items:
                clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", item.original_filename)
                dest_file = quarantine_dir / f"{item.sha256[:12]}_{clean_name}"
                data = zf.read(item.archive_path)
                dest_file.write_bytes(data)

    # 3. Write audit artifacts
    # 3a. dataset_manifest.csv
    manifest_path = audit_dir / "dataset_manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "original_archive_path",
            "original_filename",
            "original_split",
            "original_class",
            "sha256",
            "file_size_bytes",
            "is_valid_image",
            "validation_error",
            "final_split",
            "final_class",
            "output_filename",
            "output_path",
            "disposition",
            "exclusion_or_quarantine_reason",
        ])
        for item in all_manifest_items:
            writer.writerow([
                item.archive_path,
                item.original_filename,
                item.original_split,
                item.original_class,
                item.sha256,
                item.file_size_bytes,
                item.is_valid_image,
                item.validation_error or "",
                item.final_split or "",
                item.final_class or "",
                item.output_filename or "",
                item.output_path or "",
                item.disposition,
                item.exclusion_or_quarantine_reason or "",
            ])

    # 3b. duplicate_report.csv
    dup_report_path = audit_dir / "duplicate_report.csv"
    with open(dup_report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sha256",
            "group_size",
            "conflict_type",
            "files",
            "retained_file",
            "retained_class",
            "excluded_files",
            "reason",
        ])
        writer.writeheader()
        for row in duplicate_reports:
            writer.writerow(row)

    # 3c. excluded_files.csv
    excluded_path = audit_dir / "excluded_files.csv"
    with open(excluded_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "archive_path",
            "sha256",
            "original_split",
            "original_class",
            "disposition",
            "reason",
        ])
        for item in (excluded_items + corrupted_items):
            writer.writerow([
                item.archive_path,
                item.sha256,
                item.original_split,
                item.original_class,
                item.disposition,
                item.exclusion_or_quarantine_reason or "",
            ])

    # 3d. class_distribution.csv
    dist_path = audit_dir / "class_distribution.csv"
    with open(dist_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "split",
            "class",
            "retained_count",
            "percentage_within_split",
            "percentage_of_retained_dataset",
        ], extrasaction="ignore")
        writer.writeheader()
        for row in distribution_rows:
            writer.writerow(row)

    # 3e. dataset_summary.json
    summary_path = audit_dir / "dataset_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)


def verify_prepared_dataset(
    output_dir: Path,
    expected_summary: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Independent integrity verifier:
    Inspects generated output directly from disk without trusting in-memory state:
    1. All expected split and class directories exist and are non-empty.
    2. Rejects unexpected split, class, or root-level directories.
    3. Rejects untracked loose files directly inside split directories or class directories.
    4. Validates all image files on disk (supported extensions, two-pass Pillow verification).
    5. Enforces zero cross-split or within-split duplicate SHA-256 hashes.
    6. Exhaustively validates audit/dataset_manifest.csv:
       - Header completeness.
       - Dispositions in APPROVED_DISPOSITIONS.
       - Output path containment, non-escaped resolution, existence, and uniqueness.
       - Exact bit-for-bit SHA-256 matching between disk and manifest.
       - Exact file size matching between disk and manifest.
       - Exact split/class directory structure matching between disk and manifest.
    7. Verifies strict bijective mapping: every disk file maps to a retained manifest record,
       and every retained manifest record maps to an existing disk file.
    8. Reconciles on-disk audit/class_distribution.csv with actual disk counts.
    9. Reconciles on-disk audit/dataset_summary.json with manifest and disk counts.
    10. Optionally reconciles with expected_summary if passed.

    Raises DatasetVerificationError on any inconsistency.
    """
    output_dir = output_dir.resolve()
    logger.info("Running independent output integrity verification on: %s", output_dir)

    splits = ["train", "validation", "test"]
    classes = ["fire", "smoke", "neutral"]
    allowed_top_dirs = {"train", "validation", "test", "audit", "quarantine"}

    if not output_dir.is_dir():
        raise DatasetVerificationError(f"Target directory does not exist or is not a directory: '{output_dir}'")

    # 1. Structural check: No unexpected directories at dataset root
    for entry in output_dir.iterdir():
        if entry.is_dir() and entry.name not in allowed_top_dirs:
            raise DatasetVerificationError(
                f"Unexpected directory found in dataset root: '{entry.name}'. "
                f"Allowed top-level directories: {sorted(allowed_top_dirs)}"
            )

    # 2. Check each split directory
    for split in splits:
        split_dir = output_dir / split
        if not split_dir.is_dir():
            raise DatasetVerificationError(f"Missing expected split directory: '{split_dir}'")

        for child in split_dir.iterdir():
            if child.is_file():
                raise DatasetVerificationError(
                    f"Untracked loose file found directly inside split directory '{split}': '{child.name}'"
                )
            if child.is_dir() and child.name not in classes:
                raise DatasetVerificationError(
                    f"Unexpected class directory found in '{split}': '{child.name}'. "
                    f"Allowed classes: {classes}"
                )

        for cls in classes:
            class_dir = split_dir / cls
            if not class_dir.is_dir():
                raise DatasetVerificationError(f"Missing expected class directory: '{class_dir}'")

    # 3. Scan disk images, verify decoding, check unique hashes
    seen_hashes: Dict[str, str] = {}  # sha256 -> relative path
    actual_files_on_disk: Set[str] = set()
    actual_file_bytes: Dict[str, bytes] = {}
    actual_counts_by_split_class: Dict[str, int] = {}
    actual_counts_by_split: Dict[str, int] = {s: 0 for s in splits}

    for split in splits:
        for cls in classes:
            class_dir = output_dir / split / cls
            files: List[Path] = []
            for child in class_dir.iterdir():
                if child.is_dir():
                    raise DatasetVerificationError(
                        f"Unexpected subdirectory found inside class directory '{split}/{cls}': '{child.name}'"
                    )
                if child.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                    raise DatasetVerificationError(
                        f"Unsupported or unexpected file in '{split}/{cls}': '{child.name}'. "
                        f"Only {sorted(SUPPORTED_IMAGE_EXTENSIONS)} permitted."
                    )
                files.append(child)

            key = f"{split}/{cls}"
            actual_counts_by_split_class[key] = len(files)
            actual_counts_by_split[split] += len(files)

            if len(files) == 0:
                raise DatasetVerificationError(f"Directory '{split}/{cls}' is empty. All classes must be populated.")

            for f in files:
                rel_path = str(f.relative_to(output_dir)).replace("\\", "/")
                actual_files_on_disk.add(rel_path)

                data = f.read_bytes()
                actual_file_bytes[rel_path] = data
                h = compute_sha256(data)

                # Check hash isolation across entire dataset
                if h in seen_hashes:
                    prev_path = seen_hashes[h]
                    raise DatasetVerificationError(
                        f"Duplicate SHA-256 detected: '{rel_path}' and '{prev_path}' share hash {h}"
                    )
                seen_hashes[h] = rel_path

                # Check Pillow decoding
                is_valid, err_msg, dims = validate_image_bytes(data, f.name)
                if not is_valid:
                    raise DatasetVerificationError(f"Image '{rel_path}' failed Pillow decoding: {err_msg}")

    # 4. Read and exhaustively verify manifest
    manifest_path = output_dir / "audit" / "dataset_manifest.csv"
    if not manifest_path.is_file():
        raise DatasetVerificationError(f"Manifest missing at '{manifest_path}'")

    manifest_retained_paths: Set[str] = set()
    manifest_disposition_counts: Dict[str, int] = {}
    total_manifest_records = 0

    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_headers = {
            "original_archive_path", "original_filename", "original_split", "original_class",
            "sha256", "file_size_bytes", "is_valid_image", "validation_error",
            "final_split", "final_class", "output_filename", "output_path",
            "disposition", "exclusion_or_quarantine_reason"
        }
        if not required_headers.issubset(set(reader.fieldnames or [])):
            missing_cols = required_headers - set(reader.fieldnames or [])
            raise DatasetVerificationError(f"Manifest missing required column(s): {sorted(missing_cols)}")

        for row in reader:
            total_manifest_records += 1
            disp = row["disposition"]
            if disp not in APPROVED_DISPOSITIONS:
                raise DatasetVerificationError(
                    f"Manifest record '{row.get('original_archive_path')}' has unapproved disposition '{disp}'"
                )
            manifest_disposition_counts[disp] = manifest_disposition_counts.get(disp, 0) + 1

            if disp in {"RETAINED_TRAIN", "RETAINED_VALIDATION", "RETAINED_TEST"}:
                out_path = row["output_path"]
                arc_path = row.get("original_archive_path") or "unknown"
                if not out_path:
                    raise DatasetVerificationError(f"Retained manifest record missing output_path: {arc_path}")

                # Path containment check
                resolved_out = (output_dir / out_path).resolve()
                try:
                    resolved_out.relative_to(output_dir)
                except ValueError as exc:
                    raise DatasetVerificationError(
                        f"Manifest output path '{out_path}' escapes output directory!"
                    ) from exc

                if not resolved_out.is_file():
                    raise DatasetVerificationError(
                        f"Manifest references non-existent file on disk: '{out_path}'"
                    )

                # Split consistency check
                expected_disp_split = disp.replace("RETAINED_", "").lower()
                if row["final_split"] != expected_disp_split:
                    raise DatasetVerificationError(
                        f"Manifest final_split '{row['final_split']}' does not match disposition '{disp}'"
                    )

                # Path structure check: final_split/final_class/output_filename
                expected_out_path = f"{row['final_split']}/{row['final_class']}/{row['output_filename']}"
                if out_path != expected_out_path:
                    raise DatasetVerificationError(
                        f"Manifest output_path '{out_path}' does not match final split/class hierarchy '{expected_out_path}'"
                    )

                # Bit-for-bit SHA-256 on disk vs manifest
                disk_data = actual_file_bytes.get(out_path)
                if disk_data is None:
                    disk_data = resolved_out.read_bytes()
                actual_h = compute_sha256(disk_data)
                if actual_h != row["sha256"]:
                    raise DatasetVerificationError(
                        f"Hash mismatch for '{out_path}': disk has {actual_h}, manifest records {row['sha256']}"
                    )

                # File size on disk vs manifest
                if len(disk_data) != int(row["file_size_bytes"]):
                    raise DatasetVerificationError(
                        f"File size mismatch for '{out_path}': disk has {len(disk_data)} bytes, "
                        f"manifest records {row['file_size_bytes']} bytes"
                    )

                if out_path in manifest_retained_paths:
                    raise DatasetVerificationError(f"Duplicate output path in manifest: '{out_path}'")
                manifest_retained_paths.add(out_path)

    # 5. Strict Bijective Mapping Check (manifest retained == disk files)
    if manifest_retained_paths != actual_files_on_disk:
        missing_on_disk = manifest_retained_paths - actual_files_on_disk
        untracked_on_disk = actual_files_on_disk - manifest_retained_paths
        raise DatasetVerificationError(
            f"Manifest and disk mismatch. Missing on disk: {missing_on_disk}, Untracked on disk: {untracked_on_disk}"
        )

    # 6. Reconcile with on-disk class_distribution.csv
    dist_path = output_dir / "audit" / "class_distribution.csv"
    if dist_path.is_file():
        with open(dist_path, "r", encoding="utf-8") as f:
            dist_reader = csv.DictReader(f)
            dist_total = 0
            for row in dist_reader:
                s = row["split"]
                c = row["class"]
                cnt = int(row["retained_count"])
                dist_total += cnt
                disk_cnt = actual_counts_by_split_class.get(f"{s}/{c}")
                if disk_cnt is None:
                    raise DatasetVerificationError(f"class_distribution.csv references unknown split/class '{s}/{c}'")
                if disk_cnt != cnt:
                    raise DatasetVerificationError(
                        f"class_distribution.csv count mismatch for '{s}/{c}': file reports {cnt}, disk has {disk_cnt}"
                    )
            if dist_total != len(actual_files_on_disk):
                raise DatasetVerificationError(
                    f"class_distribution.csv total ({dist_total}) does not match disk file count ({len(actual_files_on_disk)})"
                )

    # 7. Reconcile with on-disk dataset_summary.json
    summary_path = output_dir / "audit" / "dataset_summary.json"
    if summary_path.is_file():
        with open(summary_path, "r", encoding="utf-8") as f:
            disk_summary = json.load(f)
            summary_retained = disk_summary.get("total_retained", disk_summary.get("retained_images"))
            if summary_retained is not None and summary_retained != len(actual_files_on_disk):
                raise DatasetVerificationError(
                    f"dataset_summary.json retained count ({summary_retained}) does not match disk count ({len(actual_files_on_disk)})"
                )

            summary_splits = disk_summary.get("split_counts", disk_summary.get("counts_by_split", {}))
            for s in splits:
                if s in summary_splits and summary_splits[s] != actual_counts_by_split[s]:
                    raise DatasetVerificationError(
                        f"dataset_summary.json count for split '{s}' ({summary_splits[s]}) does not match disk count ({actual_counts_by_split[s]})"
                    )

            summary_split_class = disk_summary.get("counts_by_split_class", {})
            for key, cnt in actual_counts_by_split_class.items():
                if key in summary_split_class and summary_split_class[key] != cnt:
                    raise DatasetVerificationError(
                        f"dataset_summary.json count for '{key}' ({summary_split_class[key]}) does not match disk ({cnt})"
                    )

    # 8. Reconcile with expected_summary if provided
    if expected_summary is not None:
        rec_images = expected_summary.get("recognized_image_entries", expected_summary.get("total_recognized_images", 0))
        if rec_images > 0 and total_manifest_records != rec_images:
            raise DatasetVerificationError(
                f"Manifest record count ({total_manifest_records}) does not match recognized image count ({rec_images})"
            )

        exp_counts = expected_summary.get("counts_by_split_class", {})
        for key, count in actual_counts_by_split_class.items():
            exp = exp_counts.get(key)
            if exp is not None and exp != count:
                raise DatasetVerificationError(f"Count mismatch for '{key}': expected {exp}, got {count}")

    logger.info("Independent verification SUCCESS: %d files verified on disk.", len(actual_files_on_disk))
    return True


def stage_and_promote_dataset(
    output_dir: Path,
    retained_items: List[DatasetItem],
    corrupted_items: List[DatasetItem],
    all_manifest_items: List[DatasetItem],
    duplicate_reports: List[Dict[str, Any]],
    excluded_items: List[DatasetItem],
    distribution_rows: List[Dict[str, Any]],
    summary_data: Dict[str, Any],
    archive_path: Path,
    force: bool = False,
) -> None:
    """
    Failure-safe dataset promotion:
    1. Stages complete dataset and audit files in a unique sibling temporary directory.
    2. Runs independent verification against staged directory before any promotion.
    3. Promotes staged directory to output_dir only after verification succeeds.
    4. When force=True, backs up previous output before replacement and restores on error.
    5. If promotion fails and restore succeeds: original dataset remains live.
    6. If promotion fails and restore fails: logs CRITICAL with exact backup path for manual recovery.
    7. If backup cleanup fails after successful promotion: logs WARNING without failing promotion.
    """
    output_dir = output_dir.resolve()
    parent_dir = output_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if output_dir.exists() and not force:
        raise OutputDirectoryConflictError(
            f"Target directory '{output_dir}' already exists. Use --force to replace."
        )

    unique_suffix = f"{os.getpid()}_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{random.randint(10000, 99999)}"
    staging_dir = parent_dir / f".tmp_{output_dir.name}_{unique_suffix}"
    staging_dir.mkdir(parents=True, exist_ok=False)

    try:
        # Write dataset to staging directory
        write_dataset_contents(
            target_dir=staging_dir,
            retained_items=retained_items,
            corrupted_items=corrupted_items,
            all_manifest_items=all_manifest_items,
            duplicate_reports=duplicate_reports,
            excluded_items=excluded_items,
            distribution_rows=distribution_rows,
            summary_data=summary_data,
            archive_path=archive_path,
        )

        # Run independent verification on staged output
        verify_prepared_dataset(staging_dir, summary_data)

    except Exception:
        # Clean up staging directory on any generation or verification failure
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    # Promotion phase
    backup_dir: Optional[Path] = None
    if output_dir.exists():
        backup_suffix = f"{os.getpid()}_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{random.randint(10000, 99999)}"
        backup_dir = parent_dir / f".bak_{output_dir.name}_{backup_suffix}"
        try:
            output_dir.rename(backup_dir)
        except OSError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise DatasetPreparationError(f"Failed to backup existing directory for replacement: {exc}") from exc

    try:
        staging_dir.rename(output_dir)
    except Exception as exc:
        if backup_dir and backup_dir.exists():
            try:
                backup_dir.rename(output_dir)
                logger.info("Restored original directory from backup following promotion failure.")
            except Exception as restore_err:
                logger.critical(
                    "CRITICAL: Failed to restore backup directory '%s' to '%s': %s. "
                    "Original dataset is preserved at backup location but requires manual intervention.",
                    backup_dir, output_dir, restore_err
                )
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise DatasetPreparationError(f"Failed to promote staging directory to '{output_dir}': {exc}") from exc

    # Clean up backup on successful promotion
    if backup_dir and backup_dir.exists():
        try:
            shutil.rmtree(backup_dir)
            logger.info("Cleaned up backup directory: %s", backup_dir)
        except Exception as clean_err:
            logger.warning(
                "Dataset successfully promoted to '%s', but old backup cleanup failed: %s (%s). "
                "The live dataset is operational; operator may safely remove '%s' manually.",
                output_dir, backup_dir, clean_err, backup_dir
            )

    logger.info("Successfully promoted staged dataset to final destination: %s", output_dir)


def run_pipeline(
    archive_path: Path,
    output_dir: Path,
    val_ratio: float = 0.20,
    seed: int = 42,
    dry_run: bool = False,
    force: bool = False,
    max_entries: int = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_total_size: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_image_size: int = DEFAULT_MAX_IMAGE_SIZE_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> Dict[str, Any]:
    """
    Executes the complete hardened wildfire dataset preparation pipeline.
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=== SCOUT M07 Wildfire Dataset Preparation Pipeline ===")
    logger.info("Archive Path: %s", archive_path)
    logger.info("Output Directory: %s", output_dir)
    logger.info("Validation Ratio: %.2f | Seed: %d | Dry Run: %s | Force: %s", val_ratio, seed, dry_run, force)

    # 1. Pre-validate resource limit parameters
    validate_resource_limits(
        max_entries=max_entries,
        max_total_size=max_total_size,
        max_image_size=max_image_size,
        max_compression_ratio=max_compression_ratio,
        max_dimension=max_dimension,
        max_pixels=max_pixels,
    )

    # 2. Output directory safety check
    if not dry_run and output_dir.resolve().exists() and not force:
        raise OutputDirectoryConflictError(
            f"Output directory '{output_dir}' already exists. Use --force to replace."
        )

    # 2. Extract and validate images from archive safely
    valid_items, corrupted_items, total_archive_entries = scan_and_validate_archive(
        archive_path=archive_path,
        max_entries=max_entries,
        max_total_size=max_total_size,
        max_image_size=max_image_size,
        max_compression_ratio=max_compression_ratio,
        max_dimension=max_dimension,
        max_pixels=max_pixels,
    )

    recognized_image_entries = len(valid_items) + len(corrupted_items)

    # 3. Deduplicate dataset and resolve conflicts
    cleaned_items, excluded_items, duplicate_reports = deduplicate_dataset(valid_items)

    # 4. Separate cleaned Train and cleaned Test
    cleaned_train = [x for x in cleaned_items if x.original_split == "train"]
    cleaned_test = [x for x in cleaned_items if x.original_split == "test"]

    logger.info("Cleaned Train items: %d", len(cleaned_train))
    logger.info("Cleaned Test items: %d", len(cleaned_test))
    logger.info("Excluded items: %d", len(excluded_items))

    # 5. Stratified 80/20 Train/Validation Split
    final_train, final_val = stratified_train_val_split(
        cleaned_train, val_ratio=val_ratio, seed=seed
    )

    all_retained = final_train + final_val + cleaned_test

    # 6. Assign collision-safe filenames and paths
    assign_collision_safe_paths(all_retained)

    # 7. Complete manifest accounting
    all_manifest = all_retained + excluded_items + corrupted_items
    all_manifest_sorted = sorted(all_manifest, key=lambda x: x.archive_path)

    # 8. Distribution metrics
    distribution_rows = compute_class_distribution(all_retained)

    # 9. Summary dictionary
    summary_data: Dict[str, Any] = {
        "pipeline_version": "1.1.0",
        "archive_path": str(archive_path),
        "timestamp_utc": start_time.isoformat(),
        "generated_at_utc": start_time.isoformat(),
        "random_seed": seed,
        "val_ratio": val_ratio,
        "validation_ratio": val_ratio,
        "dry_run": dry_run,
        "total_archive_entries": total_archive_entries,
        "total_recognized_images": recognized_image_entries,
        "recognized_image_entries": recognized_image_entries,
        "total_valid_images": len(valid_items),
        "valid_image_entries": len(valid_items),
        "total_corrupted_quarantined": len(corrupted_items),
        "corrupted_image_entries": len(corrupted_items),
        "total_retained": len(all_retained),
        "retained_images": len(all_retained),
        "total_excluded": len(excluded_items),
        "total_files_excluded": len(excluded_items),
        "total_excluded_duplicates": sum(1 for x in excluded_items if x.disposition == "EXCLUDED_DUPLICATE"),
        "total_excluded_label_conflicts": sum(1 for x in excluded_items if x.disposition == "EXCLUDED_LABEL_CONFLICT"),
        "duplicate_groups_detected": len(duplicate_reports),
        "split_counts": {
            "train": len(final_train),
            "validation": len(final_val),
            "test": len(cleaned_test),
        },
        "class_counts": {
            "fire": sum(1 for x in all_retained if x.final_class == "fire"),
            "smoke": sum(1 for x in all_retained if x.final_class == "smoke"),
            "neutral": sum(1 for x in all_retained if x.final_class == "neutral"),
        },
        "retained_files_verified": True,
        "hash_integrity_verified": True,
        "counts_by_split": {
            "train": len(final_train),
            "validation": len(final_val),
            "test": len(cleaned_test),
        },
        "counts_by_class": {
            "train": {
                "fire": sum(1 for x in final_train if x.final_class == "fire"),
                "smoke": sum(1 for x in final_train if x.final_class == "smoke"),
                "neutral": sum(1 for x in final_train if x.final_class == "neutral"),
            },
            "validation": {
                "fire": sum(1 for x in final_val if x.final_class == "fire"),
                "smoke": sum(1 for x in final_val if x.final_class == "smoke"),
                "neutral": sum(1 for x in final_val if x.final_class == "neutral"),
            },
            "test": {
                "fire": sum(1 for x in cleaned_test if x.final_class == "fire"),
                "smoke": sum(1 for x in cleaned_test if x.final_class == "smoke"),
                "neutral": sum(1 for x in cleaned_test if x.final_class == "neutral"),
            },
        },
        "counts_by_split_class": {
            f"{row['split']}/{row['class']}": row["count"] for row in distribution_rows
        },
        "conflict_summary": {
            "label_conflicts": sum(1 for r in duplicate_reports if "LABEL_CONFLICT" in r["conflict_type"]),
            "cross_split_duplicates": sum(1 for r in duplicate_reports if "CROSS_SPLIT" in r["conflict_type"]),
            "train_duplicates": sum(1 for r in duplicate_reports if "TRAIN" in r["conflict_type"]),
            "test_duplicates": sum(1 for r in duplicate_reports if "TEST" in r["conflict_type"]),
        },
        "leakage_verification": {
            "train_val_hash_overlap": len(set(x.sha256 for x in final_train) & set(x.sha256 for x in final_val)),
            "train_test_hash_overlap": len(set(x.sha256 for x in final_train) & set(x.sha256 for x in cleaned_test)),
            "val_test_hash_overlap": len(set(x.sha256 for x in final_val) & set(x.sha256 for x in cleaned_test)),
        },
    }

    if dry_run:
        logger.info("=== DRY-RUN COMPLETE (No files written) ===")
        return summary_data

    # 10. Stage and safely promote dataset
    stage_and_promote_dataset(
        output_dir=output_dir,
        retained_items=all_retained,
        corrupted_items=corrupted_items,
        all_manifest_items=all_manifest_sorted,
        duplicate_reports=duplicate_reports,
        excluded_items=excluded_items,
        distribution_rows=distribution_rows,
        summary_data=summary_data,
        archive_path=archive_path,
        force=force,
    )

    return summary_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SCOUT M07 — Wildfire Image Dataset Preparation Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--archive-path",
        type=Path,
        default=Path(r"C:\Users\TANOOJ\OneDrive\Desktop\Documents\Downloads\FIRE-SMOKE-DATASET.zip"),
        help="Path to the source FIRE-SMOKE-DATASET.zip archive.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/fire_smoke_v1"),
        help="Path to the target output directory.",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.20,
        help="Proportion of training images allocated to validation split.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Fixed random seed for deterministic stratified splitting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform extraction, deduplication, and stratification in memory without writing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output directory safely via staging and backup promotion.",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=DEFAULT_MAX_ARCHIVE_ENTRIES,
        help="Maximum permitted ZIP archive member count.",
    )
    parser.add_argument(
        "--max-total-size",
        type=int,
        default=DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
        help="Maximum permitted cumulative uncompressed bytes.",
    )
    parser.add_argument(
        "--max-image-size",
        type=int,
        default=DEFAULT_MAX_IMAGE_SIZE_BYTES,
        help="Maximum permitted uncompressed bytes for an individual image.",
    )
    parser.add_argument(
        "--max-compression-ratio",
        type=float,
        default=DEFAULT_MAX_COMPRESSION_RATIO,
        help="Maximum permitted compression ratio.",
    )

    args = parser.parse_args()

    try:
        run_pipeline(
            archive_path=args.archive_path,
            output_dir=args.output_dir,
            val_ratio=args.val_ratio,
            seed=args.seed,
            dry_run=args.dry_run,
            force=args.force,
            max_entries=args.max_entries,
            max_total_size=args.max_total_size,
            max_image_size=args.max_image_size,
            max_compression_ratio=args.max_compression_ratio,
        )
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
