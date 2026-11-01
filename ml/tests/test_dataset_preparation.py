"""
Comprehensive automated test suite for SCOUT M07 Wildfire Dataset Preparation Pipeline.

Covers all requirements from Milestone 07 specification:
- Security validation: path traversal, absolute paths, duplicate ZIP members, encrypted members.
- Resource limits: max entries, total uncompressed bytes, individual image bytes, compression ratio, dimension/pixel limits.
- Image integrity: valid JPEG/PNG/WebP, corrupt payload rejection, empty file rejection, Pillow decoding.
- Duplicate and conflict governance:
  * Same-split duplicate resolution (2 and 3 identical files).
  * Cross-split duplicate resolution (preserving Test copy, excluding Train copies).
  * Group of 3 identical files across Train and Test (1 Test, 2 Train).
  * Conflicting labels (Fire vs Smoke resolution with visual ground truth).
  * Multi-file groups with simultaneous split and class conflicts.
  * Multiple Test copies and Train copies in one group.
- Input and split validation:
  * val_ratio bounds (0.0, 1.0, negative, > 1.0).
  * Integer seed validation and deterministic reproducibility.
  * Missing class detection.
  * Insufficient samples per class check.
- Collision-safe output filenames and preservation of original filenames in manifest.
- Verification and audit correctness:
  * Bijective mapping between manifest and disk files.
  * Path containment checks.
  * Count and hash reconciliation.
  * Verification failure triggers (missing file, hash mismatch, decode failure).
- Failure-safe staging, atomic promotion, rollback, and directory preservation under --force.
"""

import io
import os
from pathlib import Path
import zipfile
import pytest
from PIL import Image

from ml.data.prepare_fire_smoke_dataset import (
    ArchiveSecurityError,
    DatasetItem,
    DatasetPreparationError,
    DatasetVerificationError,
    OutputDirectoryConflictError,
    assign_collision_safe_paths,
    check_output_directory,
    compute_class_distribution,
    compute_sha256,
    deduplicate_dataset,
    parse_entry_metadata,
    run_pipeline,
    scan_and_validate_archive,
    stage_and_promote_dataset,
    stratified_train_val_split,
    validate_image_bytes,
    validate_resource_limits,
    validate_split_inputs,
    validate_zip_entry_path,
    verify_prepared_dataset,
    APPROVED_DISPOSITIONS,
    REVIEWED_LABEL_CONFLICT_REGISTRY,
    DEFAULT_MAX_ARCHIVE_ENTRIES,
    DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    DEFAULT_MAX_IMAGE_SIZE_BYTES,
    DEFAULT_MAX_COMPRESSION_RATIO,
    DEFAULT_MAX_IMAGE_DIMENSION,
    DEFAULT_MAX_IMAGE_PIXELS,
)


def _make_dummy_image(
    color: tuple = (255, 0, 0),
    size: tuple = (32, 32),
    fmt: str = "JPEG",
) -> bytes:
    """Helper to generate valid image bytes in memory."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_class_image(cls: str, index: int, split: str = "train", fmt: str = "JPEG") -> bytes:
    """Helper to generate distinct image bytes per class, index, and split."""
    cls_offsets = {"fire": 10, "smoke": 90, "neutral": 170}
    split_offset = 0 if split == "train" else 40
    color = (
        (cls_offsets[cls] + index * 5) % 255,
        (split_offset + index * 8) % 255,
        (cls_offsets[cls] + 30) % 255,
    )
    return _make_dummy_image(color=color, fmt=fmt)


def _create_synthetic_zip(
    zip_path: Path,
    entries: dict,
) -> Path:
    """Helper to write a synthetic ZIP archive with provided {archive_path: bytes}."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in entries.items():
            zf.writestr(arcname, data)
    return zip_path


# ==============================================================================
# 1. SECURITY & ARCHIVE PATH TRAVERSAL TESTS
# ==============================================================================

def test_validate_zip_entry_path_accepts_clean_paths():
    """Verify that legitimate relative archive paths pass validation."""
    validate_zip_entry_path("FIRE-SMOKE-DATASET/Train/Fire/image_1.jpg")
    validate_zip_entry_path("Test/Smoke/sample.jpg")
    validate_zip_entry_path("Neutral/frame_01.png")
    validate_zip_entry_path("Train/Neutral/sample.webp")


def test_validate_zip_entry_path_rejects_traversal_and_absolute_paths():
    """Verify that malicious paths containing '..' or absolute roots are rejected."""
    with pytest.raises(ArchiveSecurityError):
        validate_zip_entry_path("../../outside.jpg")

    with pytest.raises(ArchiveSecurityError):
        validate_zip_entry_path("/etc/shadow")

    with pytest.raises(ArchiveSecurityError):
        validate_zip_entry_path("\\Windows\\System32\\cmd.exe")

    with pytest.raises(ArchiveSecurityError):
        validate_zip_entry_path("C:/Windows/System32/cmd.exe")

    with pytest.raises(ArchiveSecurityError):
        validate_zip_entry_path("FIRE-SMOKE-DATASET/Train/../../secret.jpg")

    with pytest.raises(ArchiveSecurityError):
        validate_zip_entry_path("Train/../Test/Fire/img.jpg")


def test_parse_entry_metadata():
    """Verify metadata extraction and normalization to canonical lowercase."""
    meta = parse_entry_metadata("FIRE-SMOKE-DATASET/Train/Fire/image_10.jpg")
    assert meta == ("train", "fire", "image_10.jpg")

    meta_test = parse_entry_metadata("FIRE-SMOKE-DATASET/Test/Smoke/frame_2.jpg")
    assert meta_test == ("test", "smoke", "frame_2.jpg")

    meta_neutral = parse_entry_metadata("Train/Neutral/neutral_01.jpg")
    assert meta_neutral == ("train", "neutral", "neutral_01.jpg")

    # Non-image files or invalid classes return None
    assert parse_entry_metadata("FIRE-SMOKE-DATASET/Train/Fire/notes.txt") is None
    assert parse_entry_metadata("FIRE-SMOKE-DATASET/Validation/Fire/img.jpg") is None
    assert parse_entry_metadata("FIRE-SMOKE-DATASET/Train/Flood/img.jpg") is None


# ==============================================================================
# 2. IMAGE CONTENT & FORMAT VALIDATION TESTS
# ==============================================================================

def test_validate_image_bytes_valid_formats():
    """Verify that valid JPEG, PNG, and WebP bytes are approved."""
    for fmt in ["JPEG", "PNG", "WEBP"]:
        ext = fmt.lower()
        img_bytes = _make_dummy_image(color=(50, 100, 150), size=(40, 40), fmt=fmt)
        is_valid, err, dims = validate_image_bytes(img_bytes, f"test.{ext}")
        assert is_valid is True, f"Failed for format {fmt}: {err}"
        assert err is None
        assert dims == (40, 40)


def test_validate_image_bytes_corrupted_payload():
    """Verify that corrupted or truncated bytes are rejected."""
    corrupt_bytes = b"\xff\xd8\xff\xe0" + b"GARBAGE_PAYLOAD_NOT_IMAGE"
    is_valid, err, dims = validate_image_bytes(corrupt_bytes, "corrupt.jpg")
    assert is_valid is False
    assert err is not None
    assert dims is None

    # Empty payload
    is_valid_empty, err_empty, _ = validate_image_bytes(b"", "empty.jpg")
    assert is_valid_empty is False
    assert "Empty" in err_empty


def test_validate_image_bytes_dimension_and_pixel_limits():
    """Verify that images exceeding pixel or dimension limits are rejected."""
    img_bytes = _make_dummy_image(size=(100, 100))
    # Passing limit lower than image dimensions
    is_valid, err, _ = validate_image_bytes(
        img_bytes, "test.jpg", max_dimension=50, max_pixels=10_000
    )
    assert is_valid is False
    assert "dimension" in err.lower() or "limit" in err.lower()

    # Exceeding pixel count limit
    is_valid_px, err_px, _ = validate_image_bytes(
        img_bytes, "test.jpg", max_dimension=200, max_pixels=500
    )
    assert is_valid_px is False
    assert "pixel" in err_px.lower() or "limit" in err_px.lower()


# ==============================================================================
# 3. ARCHIVE SECURITY & LIMITS ENFORCEMENT
# ==============================================================================

def test_archive_duplicate_member_names_rejected(tmp_path: Path):
    """Verify that an archive containing duplicate member paths raises ArchiveSecurityError."""
    zip_path = tmp_path / "dup_member.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Train/Fire/img1.jpg", _make_dummy_image(color=(1, 1, 1)))
        zf.writestr("Train/Fire/img1.jpg", _make_dummy_image(color=(2, 2, 2)))

    with pytest.raises(ArchiveSecurityError, match="Duplicate member name"):
        scan_and_validate_archive(zip_path)


def test_archive_encrypted_entries_rejected(tmp_path: Path):
    """Verify that encrypted zip entries (flag_bits & 0x1) raise ArchiveSecurityError."""
    zip_path = tmp_path / "encrypted.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Train/Fire/img1.jpg", _make_dummy_image())
    raw = bytearray(buf.getvalue())
    cd_idx = raw.find(b"PK\x01\x02")
    if cd_idx != -1:
        raw[cd_idx + 8] |= 0x1
    loc_idx = raw.find(b"PK\x03\x04")
    if loc_idx != -1:
        raw[loc_idx + 6] |= 0x1
    zip_path.write_bytes(bytes(raw))

    with pytest.raises(ArchiveSecurityError, match="Encrypted archive member"):
        scan_and_validate_archive(zip_path)


def test_archive_entry_count_limit_exceeded(tmp_path: Path):
    """Verify that exceeding max_entries raises ArchiveSecurityError."""
    zip_path = tmp_path / "too_many_entries.zip"
    entries = {f"Train/Fire/img_{i}.jpg": _make_dummy_image() for i in range(15)}
    _create_synthetic_zip(zip_path, entries)

    with pytest.raises(ArchiveSecurityError, match="exceeds maximum limit"):
        scan_and_validate_archive(zip_path, max_entries=10)


def test_archive_total_uncompressed_size_limit_exceeded(tmp_path: Path):
    """Verify that exceeding total uncompressed size raises ArchiveSecurityError."""
    zip_path = tmp_path / "too_large_total.zip"
    img = _make_dummy_image()
    entries = {f"Train/Fire/img_{i}.jpg": img for i in range(5)}
    _create_synthetic_zip(zip_path, entries)

    total_bytes = len(img) * 5
    with pytest.raises(ArchiveSecurityError, match="exceeds safety limit"):
        scan_and_validate_archive(zip_path, max_total_size=total_bytes - 10)


def test_archive_individual_image_size_limit_exceeded(tmp_path: Path):
    """Verify that an individual image exceeding max_image_size raises ArchiveSecurityError."""
    zip_path = tmp_path / "too_large_image.zip"
    img = _make_dummy_image(size=(128, 128))
    entries = {"Train/Fire/big_img.jpg": img}
    _create_synthetic_zip(zip_path, entries)

    with pytest.raises(ArchiveSecurityError, match="exceeds limit"):
        scan_and_validate_archive(zip_path, max_image_size=len(img) - 10)


def test_archive_compression_ratio_limit_exceeded(tmp_path: Path):
    """Verify that a zip bomb with suspicious compression ratio raises ArchiveSecurityError."""
    zip_path = tmp_path / "zip_bomb.zip"
    compressible_data = b"\x00" * 500_000
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Train/Fire/bomb.jpg", compressible_data)

    with pytest.raises(ArchiveSecurityError, match="compression ratio"):
        scan_and_validate_archive(zip_path, max_compression_ratio=2.0)


def test_validate_resource_limits_rejects_booleans():
    """Verify that validate_resource_limits explicitly rejects boolean arguments."""
    with pytest.raises(ValueError, match="Limit parameter 'max_entries' must be an integer, got bool"):
        validate_resource_limits(max_entries=True)

    with pytest.raises(ValueError, match="Limit parameter 'max_entries' must be an integer, got bool"):
        validate_resource_limits(max_entries=False)

    with pytest.raises(ValueError, match="Limit parameter 'max_total_size' must be an integer, got bool"):
        validate_resource_limits(max_total_size=True)

    with pytest.raises(ValueError, match="Limit parameter 'max_image_size' must be an integer, got bool"):
        validate_resource_limits(max_image_size=True)

    with pytest.raises(ValueError, match="Limit parameter 'max_compression_ratio' must be a numeric float or integer, got bool"):
        validate_resource_limits(max_compression_ratio=True)

    with pytest.raises(ValueError, match="Limit parameter 'max_dimension' must be an integer, got bool"):
        validate_resource_limits(max_dimension=False)

    with pytest.raises(ValueError, match="Limit parameter 'max_pixels' must be an integer, got bool"):
        validate_resource_limits(max_pixels=True)


def test_validate_resource_limits_rejects_non_positive_and_invalid():
    """Verify that validate_resource_limits rejects non-integers, non-positives, NaN, and inf."""
    # Non-integers
    with pytest.raises(ValueError, match="must be an integer"):
        validate_resource_limits(max_entries="1000")  # type: ignore

    with pytest.raises(ValueError, match="must be an integer"):
        validate_resource_limits(max_entries=10.5)  # type: ignore

    # Non-positives
    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_entries=0)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_entries=-5)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_total_size=0)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_image_size=-1)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_dimension=0)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_pixels=-100)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_compression_ratio=0.0)

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_resource_limits(max_compression_ratio=-10.0)

    # NaN / Inf
    with pytest.raises(ValueError, match="must be finite"):
        validate_resource_limits(max_compression_ratio=float("nan"))

    with pytest.raises(ValueError, match="must be finite"):
        validate_resource_limits(max_compression_ratio=float("inf"))

    # Valid values should pass without error
    validate_resource_limits(
        max_entries=1000,
        max_total_size=1024 * 1024,
        max_image_size=1024,
        max_compression_ratio=50.0,
        max_dimension=1024,
        max_pixels=1_000_000,
    )


def test_scan_and_validate_archive_enforces_limits_upfront(tmp_path: Path):
    """Verify scan_and_validate_archive validates limits before opening archive."""
    fake_zip = tmp_path / "non_existent.zip"
    with pytest.raises(ValueError, match="Limit parameter 'max_entries' must be an integer, got bool"):
        scan_and_validate_archive(fake_zip, max_entries=True)


# ==============================================================================
# 4. DEDUPLICATION & CONFLICT RESOLUTION TESTS
# ==============================================================================

def test_duplicate_detection_same_split_same_class():
    """Verify same-split same-class duplicates retain 1 copy and exclude the rest."""
    img_bytes = _make_dummy_image(color=(10, 20, 30))
    h = compute_sha256(img_bytes)

    item1 = DatasetItem(
        archive_path="FIRE-SMOKE-DATASET/Train/Fire/image_1.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="image_1.jpg",
        file_size_bytes=len(img_bytes),
    )
    item2 = DatasetItem(
        archive_path="FIRE-SMOKE-DATASET/Train/Fire/image_2.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="image_2.jpg",
        file_size_bytes=len(img_bytes),
    )

    retained, excluded, reports = deduplicate_dataset([item1, item2])

    assert len(retained) == 1
    assert len(excluded) == 1
    assert len(reports) == 1

    assert retained[0].archive_path == "FIRE-SMOKE-DATASET/Train/Fire/image_1.jpg"
    assert retained[0].is_retained is True
    assert retained[0].disposition == "RETAINED_TRAIN"

    assert excluded[0].archive_path == "FIRE-SMOKE-DATASET/Train/Fire/image_2.jpg"
    assert excluded[0].is_retained is False
    assert excluded[0].disposition == "EXCLUDED_DUPLICATE"


def test_duplicate_group_3_identical_same_split():
    """Verify a group of 3 identical images in same split retains 1 and excludes 2."""
    img_bytes = _make_dummy_image(color=(11, 22, 33))
    h = compute_sha256(img_bytes)

    items = [
        DatasetItem(
            archive_path=f"Train/Smoke/smoke_{i}.jpg",
            sha256=h,
            original_split="train",
            original_class="smoke",
            original_filename=f"smoke_{i}.jpg",
            file_size_bytes=len(img_bytes),
        )
        for i in [3, 1, 2]  # Unordered
    ]

    retained, excluded, reports = deduplicate_dataset(items)

    assert len(retained) == 1
    assert len(excluded) == 2
    assert len(reports) == 1

    # Deterministic alphabetical retention
    assert retained[0].archive_path == "Train/Smoke/smoke_1.jpg"
    assert retained[0].disposition == "RETAINED_TRAIN"

    assert reports[0]["group_size"] == 3
    assert reports[0]["retained_file"] == "Train/Smoke/smoke_1.jpg"
    assert len(reports[0]["excluded_files"].split("; ")) == 2

    for exc in excluded:
        assert exc.disposition == "EXCLUDED_DUPLICATE"
        assert exc.is_retained is False


def test_cross_split_duplicate_preserves_test_copy():
    """Verify cross-split duplicates retain Test copy and exclude Train copy."""
    img_bytes = _make_dummy_image(color=(40, 50, 60))
    h = compute_sha256(img_bytes)

    test_item = DatasetItem(
        archive_path="FIRE-SMOKE-DATASET/Test/Fire/image_39.jpg",
        sha256=h,
        original_split="test",
        original_class="fire",
        original_filename="image_39.jpg",
        file_size_bytes=len(img_bytes),
    )
    train_item = DatasetItem(
        archive_path="FIRE-SMOKE-DATASET/Train/Fire/image_821.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="image_821.jpg",
        file_size_bytes=len(img_bytes),
    )

    retained, excluded, reports = deduplicate_dataset([train_item, test_item])

    assert len(retained) == 1
    assert len(excluded) == 1
    # Test copy MUST be preserved
    assert retained[0].original_split == "test"
    assert retained[0].archive_path == "FIRE-SMOKE-DATASET/Test/Fire/image_39.jpg"
    assert retained[0].disposition == "RETAINED_TEST"

    # Train copy MUST be excluded
    assert excluded[0].original_split == "train"
    assert excluded[0].archive_path == "FIRE-SMOKE-DATASET/Train/Fire/image_821.jpg"
    assert excluded[0].disposition == "EXCLUDED_DUPLICATE"


def test_duplicate_group_3_identical_across_train_and_test():
    """Verify group of 3 identical images with 1 Test and 2 Train copies."""
    img_bytes = _make_dummy_image(color=(45, 55, 65))
    h = compute_sha256(img_bytes)

    test_item = DatasetItem(
        archive_path="Test/Fire/test_img.jpg",
        sha256=h,
        original_split="test",
        original_class="fire",
        original_filename="test_img.jpg",
        file_size_bytes=len(img_bytes),
    )
    train_item1 = DatasetItem(
        archive_path="Train/Fire/train_img1.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="train_img1.jpg",
        file_size_bytes=len(img_bytes),
    )
    train_item2 = DatasetItem(
        archive_path="Train/Fire/train_img2.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="train_img2.jpg",
        file_size_bytes=len(img_bytes),
    )

    retained, excluded, reports = deduplicate_dataset([train_item2, test_item, train_item1])

    assert len(retained) == 1
    assert len(excluded) == 2
    assert retained[0].archive_path == "Test/Fire/test_img.jpg"
    assert retained[0].disposition == "RETAINED_TEST"

    for exc in excluded:
        assert exc.original_split == "train"
        assert exc.disposition == "EXCLUDED_DUPLICATE"
        assert "data leakage" in exc.exclusion_or_quarantine_reason


def test_label_conflict_resolution_smoke_over_fire():
    """
    Verify conflicting label (Train/Fire/image_12.jpg vs Train/Smoke/image_23.jpg).
    Keyed strictly by approved SHA-256 in REVIEWED_LABEL_CONFLICT_REGISTRY.
    Smoke copy MUST be retained, Fire copy MUST be excluded with detailed reason.
    """
    h = "b667e935cfa32afbc25a4170a6adc1c6700b9e2df082e2dd55c299120678e786"
    assert h in REVIEWED_LABEL_CONFLICT_REGISTRY

    fire_item = DatasetItem(
        archive_path="FIRE-SMOKE-DATASET/Train/Fire/image_12.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="image_12.jpg",
        file_size_bytes=1024,
    )
    smoke_item = DatasetItem(
        archive_path="FIRE-SMOKE-DATASET/Train/Smoke/image_23.jpg",
        sha256=h,
        original_split="train",
        original_class="smoke",
        original_filename="image_23.jpg",
        file_size_bytes=1024,
    )

    retained, excluded, reports = deduplicate_dataset([fire_item, smoke_item])

    assert len(retained) == 1
    assert len(excluded) == 1

    # Smoke copy retained
    assert retained[0].archive_path == "FIRE-SMOKE-DATASET/Train/Smoke/image_23.jpg"
    assert retained[0].final_class == "smoke"
    assert retained[0].disposition == "RETAINED_TRAIN"

    # Fire copy excluded with label conflict reason citing visual ground truth
    assert excluded[0].archive_path == "FIRE-SMOKE-DATASET/Train/Fire/image_12.jpg"
    assert excluded[0].disposition == "EXCLUDED_LABEL_CONFLICT"
    assert "visual ground-truth audit confirmed" in excluded[0].exclusion_or_quarantine_reason.lower()

    # Duplicate report must cite reviewed conflict registry
    assert len(reports) == 1
    assert reports[0]["conflict_type"] == "LABEL_CONFLICT"
    assert reports[0]["retained_class"] == "smoke"
    assert "reviewed conflict registry" in reports[0]["reason"]


def test_unreviewed_fire_smoke_conflict_raises_error():
    """Verify that any unreviewed Fire vs Smoke duplicate group raises DatasetPreparationError."""
    img_bytes = _make_dummy_image(color=(70, 80, 90))
    h = compute_sha256(img_bytes)
    assert h not in REVIEWED_LABEL_CONFLICT_REGISTRY

    fire_item = DatasetItem(
        archive_path="Train/Fire/img_other_fire.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="img_other_fire.jpg",
        file_size_bytes=len(img_bytes),
    )
    smoke_item = DatasetItem(
        archive_path="Train/Smoke/img_other_smoke.jpg",
        sha256=h,
        original_split="train",
        original_class="smoke",
        original_filename="img_other_smoke.jpg",
        file_size_bytes=len(img_bytes),
    )

    with pytest.raises(DatasetPreparationError, match="Unreviewed conflicting labels in Train"):
        deduplicate_dataset([fire_item, smoke_item])


def test_conflicting_labels_within_test_raises_error():
    """Verify that duplicate images within Test with conflicting labels raise DatasetPreparationError."""
    img_bytes = _make_dummy_image(color=(88, 88, 88))
    h = compute_sha256(img_bytes)

    test_fire = DatasetItem(
        archive_path="Test/Fire/test_fire.jpg",
        sha256=h,
        original_split="test",
        original_class="fire",
        original_filename="test_fire.jpg",
        file_size_bytes=len(img_bytes),
    )
    test_smoke = DatasetItem(
        archive_path="Test/Smoke/test_smoke.jpg",
        sha256=h,
        original_split="test",
        original_class="smoke",
        original_filename="test_smoke.jpg",
        file_size_bytes=len(img_bytes),
    )

    with pytest.raises(DatasetPreparationError, match="Unresolvable conflicting labels within Test set"):
        deduplicate_dataset([test_fire, test_smoke])


def test_multi_file_group_split_and_class_conflicts():
    """
    Verify multi-file group with simultaneous split and class conflicts:
    1 Test/Smoke, 1 Train/Smoke, 1 Train/Fire.
    Test/Smoke must be retained; Train/Smoke is duplicate; Train/Fire is label conflict against Test.
    """
    img_bytes = _make_dummy_image(color=(95, 95, 95))
    h = compute_sha256(img_bytes)

    test_smoke = DatasetItem(
        archive_path="Test/Smoke/img_t.jpg",
        sha256=h,
        original_split="test",
        original_class="smoke",
        original_filename="img_t.jpg",
        file_size_bytes=len(img_bytes),
    )
    train_smoke = DatasetItem(
        archive_path="Train/Smoke/img_s.jpg",
        sha256=h,
        original_split="train",
        original_class="smoke",
        original_filename="img_s.jpg",
        file_size_bytes=len(img_bytes),
    )
    train_fire = DatasetItem(
        archive_path="Train/Fire/img_f.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="img_f.jpg",
        file_size_bytes=len(img_bytes),
    )

    retained, excluded, reports = deduplicate_dataset([train_fire, train_smoke, test_smoke])

    assert len(retained) == 1
    assert len(excluded) == 2
    assert retained[0].archive_path == "Test/Smoke/img_t.jpg"
    assert retained[0].disposition == "RETAINED_TEST"

    # Train/Smoke is duplicate
    exc_smoke = next(x for x in excluded if x.original_class == "smoke")
    assert exc_smoke.disposition == "EXCLUDED_DUPLICATE"

    # Train/Fire is label conflict against Test
    exc_fire = next(x for x in excluded if x.original_class == "fire")
    assert exc_fire.disposition == "EXCLUDED_LABEL_CONFLICT"
    assert "preserved Test copy as ground truth benchmark" in exc_fire.exclusion_or_quarantine_reason

    # Report has CROSS_SPLIT_LABEL_CONFLICT
    assert len(reports) == 1
    assert reports[0]["conflict_type"] == "CROSS_SPLIT_LABEL_CONFLICT"


def test_multiple_test_and_train_copies():
    """Verify group with multiple Test copies and multiple Train copies."""
    img_bytes = _make_dummy_image(color=(120, 120, 120))
    h = compute_sha256(img_bytes)

    test1 = DatasetItem(
        archive_path="Test/Fire/test_a.jpg",
        sha256=h,
        original_split="test",
        original_class="fire",
        original_filename="test_a.jpg",
        file_size_bytes=len(img_bytes),
    )
    test2 = DatasetItem(
        archive_path="Test/Fire/test_b.jpg",
        sha256=h,
        original_split="test",
        original_class="fire",
        original_filename="test_b.jpg",
        file_size_bytes=len(img_bytes),
    )
    train1 = DatasetItem(
        archive_path="Train/Fire/train_a.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="train_a.jpg",
        file_size_bytes=len(img_bytes),
    )

    retained, excluded, _ = deduplicate_dataset([train1, test2, test1])

    assert len(retained) == 1
    assert len(excluded) == 2
    assert retained[0].archive_path == "Test/Fire/test_a.jpg"
    assert retained[0].disposition == "RETAINED_TEST"

    # Second Test is excluded as Test duplicate
    exc_test = next(x for x in excluded if x.original_split == "test")
    assert exc_test.archive_path == "Test/Fire/test_b.jpg"
    assert exc_test.disposition == "EXCLUDED_DUPLICATE"

    # Train is excluded as duplicate of Test
    exc_train = next(x for x in excluded if x.original_split == "train")
    assert exc_train.archive_path == "Train/Fire/train_a.jpg"
    assert exc_train.disposition == "EXCLUDED_DUPLICATE"


def test_unresolvable_conflict_raises_error():
    """Verify that an unknown conflicting label in Train raises DatasetPreparationError."""
    img_bytes = _make_dummy_image(color=(1, 2, 3))
    h = compute_sha256(img_bytes)

    item1 = DatasetItem(
        archive_path="Train/Neutral/img_n.jpg",
        sha256=h,
        original_split="train",
        original_class="neutral",
        original_filename="img_n.jpg",
        file_size_bytes=len(img_bytes),
    )
    item2 = DatasetItem(
        archive_path="Train/Fire/img_f.jpg",
        sha256=h,
        original_split="train",
        original_class="fire",
        original_filename="img_f.jpg",
        file_size_bytes=len(img_bytes),
    )

    with pytest.raises(DatasetPreparationError, match="Unreviewed conflicting labels in Train"):
        deduplicate_dataset([item1, item2])


# ==============================================================================
# 5. SPLIT INPUT VALIDATION & STRATIFIED PARTITIONING
# ==============================================================================

def test_validate_split_inputs_checks():
    """Verify input validation for val_ratio, seed, classes, and sample counts."""
    valid_items = [
        DatasetItem(
            archive_path=f"Train/{cls}/img_{i}.jpg",
            sha256=f"hash_{cls}_{i}",
            original_split="train",
            original_class=cls,
            original_filename=f"img_{i}.jpg",
            file_size_bytes=100,
        )
        for cls in ["fire", "smoke", "neutral"]
        for i in range(10)
    ]

    # Valid call passes
    validate_split_inputs(valid_items, val_ratio=0.20, seed=42)

    # Invalid ratios
    for invalid_ratio in [0.0, 1.0, -0.1, 1.2]:
        with pytest.raises(ValueError, match="strictly between 0 and 1"):
            validate_split_inputs(valid_items, val_ratio=invalid_ratio, seed=42)

    # Invalid seed
    with pytest.raises(ValueError, match="seed must be an integer"):
        validate_split_inputs(valid_items, val_ratio=0.20, seed="42")  # type: ignore

    # Missing class
    missing_class_items = [x for x in valid_items if x.original_class != "neutral"]
    with pytest.raises(DatasetPreparationError, match="Missing required class"):
        validate_split_inputs(missing_class_items, val_ratio=0.20, seed=42)

    # Insufficient samples
    sparse_items = [
        DatasetItem(
            archive_path="Train/fire/img_0.jpg",
            sha256="h0",
            original_split="train",
            original_class="fire",
            original_filename="img_0.jpg",
            file_size_bytes=100,
        ),
        DatasetItem(
            archive_path="Train/smoke/img_0.jpg",
            sha256="h1",
            original_split="train",
            original_class="smoke",
            original_filename="img_0.jpg",
            file_size_bytes=100,
        ),
        DatasetItem(
            archive_path="Train/neutral/img_0.jpg",
            sha256="h2",
            original_split="train",
            original_class="neutral",
            original_filename="img_0.jpg",
            file_size_bytes=100,
        ),
    ]
    with pytest.raises(DatasetPreparationError, match="insufficient samples"):
        validate_split_inputs(sparse_items, val_ratio=0.20, seed=42)


def test_stratified_split_isolation_and_reproducibility():
    """Verify stratified proportion, zero hash overlap, and reproducibility."""
    items = []
    classes = ["fire", "smoke", "neutral"]
    for cls in classes:
        for i in range(100):
            content = f"dummy_{cls}_{i}".encode("utf-8")
            h = compute_sha256(content)
            items.append(
                DatasetItem(
                    archive_path=f"Train/{cls}/img_{i}.jpg",
                    sha256=h,
                    original_split="train",
                    original_class=cls,
                    final_split="train",
                    final_class=cls,
                    original_filename=f"img_{i}.jpg",
                    file_size_bytes=len(content),
                )
            )

    train_1, val_1 = stratified_train_val_split(items, val_ratio=0.20, seed=42)

    # 1. Proportions: 20 val, 80 train per class
    for cls in classes:
        cls_val = [x for x in val_1 if x.final_class == cls]
        cls_train = [x for x in train_1 if x.final_class == cls]
        assert len(cls_val) == 20
        assert len(cls_train) == 80

    assert len(train_1) == 240
    assert len(val_1) == 60

    # 2. Check zero hash overlap
    train_hashes = set(x.sha256 for x in train_1)
    val_hashes = set(x.sha256 for x in val_1)
    assert len(train_hashes & val_hashes) == 0

    # 3. Check reproducibility
    train_2, val_2 = stratified_train_val_split(items, val_ratio=0.20, seed=42)
    assert [x.archive_path for x in train_1] == [x.archive_path for x in train_2]
    assert [x.archive_path for x in val_1] == [x.archive_path for x in val_2]


# ==============================================================================
# 6. FILENAME COLLISION HANDLING
# ==============================================================================

def test_filename_collision_handling():
    """
    Verify that two distinct images with the same original filename
    in the same split and class receive collision-safe unique output filenames.
    """
    item1 = DatasetItem(
        archive_path="Train/Fire/folderA/image_01.jpg",
        original_filename="image_01.jpg",
        original_split="train",
        original_class="fire",
        final_split="train",
        final_class="fire",
        sha256="111111111111aaaa",
        file_size_bytes=100,
    )
    item2 = DatasetItem(
        archive_path="Train/Fire/folderB/image_01.jpg",
        original_filename="image_01.jpg",
        original_split="train",
        original_class="fire",
        final_split="train",
        final_class="fire",
        sha256="222222222222bbbb",
        file_size_bytes=100,
    )

    assign_collision_safe_paths([item1, item2])

    assert item1.output_filename != item2.output_filename
    assert item1.output_filename == "111111111111_image_01.jpg"
    assert item2.output_filename == "222222222222_image_01.jpg"
    assert item1.output_path == "train/fire/111111111111_image_01.jpg"
    assert item2.output_path == "train/fire/222222222222_image_01.jpg"


# ==============================================================================
# 7. END-TO-END PIPELINE & VERIFICATION WITH SYNTHETIC ARCHIVES
# ==============================================================================

def test_normal_archive_processing_end_to_end(tmp_path: Path):
    """
    Test complete pipeline end-to-end on synthetic ZIP archive into tmp_path:
    - 3 classes (fire, smoke, neutral) across Train and Test.
    - Validates directory structure, image decoding, manifest mapping, and summary metrics.
    """
    zip_path = tmp_path / "synthetic_dataset.zip"
    out_dir = tmp_path / "prepared_dataset"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(10):
            entries[f"FIRE-SMOKE-DATASET/Train/{cls.capitalize()}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(5):
            entries[f"FIRE-SMOKE-DATASET/Test/{cls.capitalize()}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    entries["FIRE-SMOKE-DATASET/README.txt"] = b"Disaster intelligence test archive."

    _create_synthetic_zip(zip_path, entries)

    summary = run_pipeline(
        archive_path=zip_path,
        output_dir=out_dir,
        val_ratio=0.20,
        seed=42,
        dry_run=False,
        force=False,
    )

    assert summary["total_archive_entries"] == 46
    assert summary["recognized_image_entries"] == 45
    assert summary["valid_image_entries"] == 45
    assert summary["retained_images"] == 45
    assert summary["counts_by_split"]["train"] == 24
    assert summary["counts_by_split"]["validation"] == 6
    assert summary["counts_by_split"]["test"] == 15

    # Check disk output
    assert out_dir.exists()
    assert (out_dir / "audit" / "dataset_manifest.csv").is_file()
    assert (out_dir / "audit" / "duplicate_report.csv").is_file()
    assert (out_dir / "audit" / "excluded_files.csv").is_file()
    assert (out_dir / "audit" / "class_distribution.csv").is_file()
    assert (out_dir / "audit" / "dataset_summary.json").is_file()

    # Verify prepared output independently
    assert verify_prepared_dataset(out_dir, summary) is True


def test_corrupted_images_quarantined_and_recorded(tmp_path: Path):
    """Verify corrupted images are rejected, quarantined, and recorded in manifest."""
    zip_path = tmp_path / "corrupt_dataset.zip"
    out_dir = tmp_path / "out_corrupt"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    # Add a corrupt image in Train/Fire
    entries["Train/Fire/corrupt_01.jpg"] = b"\xff\xd8\xff\xe0" + b"CORRUPTED_PAYLOAD"

    _create_synthetic_zip(zip_path, entries)

    summary = run_pipeline(
        archive_path=zip_path,
        output_dir=out_dir,
        val_ratio=0.20,
        seed=42,
    )

    assert summary["corrupted_image_entries"] == 1
    assert summary["valid_image_entries"] == 21
    quarantine_files = list((out_dir / "quarantine").iterdir())
    assert len(quarantine_files) == 1
    assert "corrupt_01.jpg" in quarantine_files[0].name


def test_output_contains_jpeg_extension_verified(tmp_path: Path):
    """Verify that images with .jpeg extension are handled and verified cleanly."""
    zip_path = tmp_path / "jpeg_dataset.zip"
    out_dir = tmp_path / "out_jpeg"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            ext = "jpeg" if i % 2 == 0 else "jpg"
            entries[f"Train/{cls}/img_{i}.{ext}"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpeg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)

    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)
    assert summary["retained_images"] == 21
    assert verify_prepared_dataset(out_dir, summary) is True


def test_dry_run_does_not_write_files(tmp_path: Path):
    """Verify that dry_run=True returns summary without writing any files."""
    zip_path = tmp_path / "dry_run_dataset.zip"
    out_dir = tmp_path / "out_dry_run"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)

    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir, dry_run=True)
    assert summary["dry_run"] is True
    assert not out_dir.exists()


# ==============================================================================
# 8. VERIFICATION FAILURE TRIGGERS
# ==============================================================================

def test_verify_prepared_dataset_catches_missing_file(tmp_path: Path):
    """Verify verification fails when a retained image is deleted from disk."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_missing"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Delete one image from disk
    first_img = next((out_dir / "train" / "fire").iterdir())
    first_img.unlink()

    with pytest.raises(DatasetVerificationError, match="non-existent file"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_untracked_file(tmp_path: Path):
    """Verify verification fails when an untracked image is added to disk."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_untracked"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Add untracked image
    untracked = out_dir / "train" / "fire" / "rogue.jpg"
    untracked.write_bytes(_make_dummy_image(color=(255, 255, 255)))

    with pytest.raises(DatasetVerificationError, match="Manifest and disk mismatch"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_cross_split_hash_collision(tmp_path: Path):
    """Verify verification fails if two files share a hash (data leakage)."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_collision"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Overwrite a test image with identical bytes from a train image
    train_img = next((out_dir / "train" / "fire").iterdir())
    test_img = next((out_dir / "test" / "fire").iterdir())
    test_img.write_bytes(train_img.read_bytes())

    with pytest.raises(DatasetVerificationError, match="Duplicate SHA-256 detected"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_content_tampering_sha256_mismatch(tmp_path: Path):
    """Verify that tampering with an on-disk image's contents causes hash verification failure."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_tamper"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Tamper with an image on disk
    target_img = next((out_dir / "train" / "fire").iterdir())
    target_img.write_bytes(_make_dummy_image(color=(123, 234, 56)))

    with pytest.raises(DatasetVerificationError, match="Hash mismatch for"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_manifest_file_size_mismatch(tmp_path: Path):
    """Verify that tampering with file_size_bytes in the manifest is detected."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_size_mismatch"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Tamper with manifest file_size_bytes
    manifest_file = out_dir / "audit" / "dataset_manifest.csv"
    lines = manifest_file.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    size_idx = header.index("file_size_bytes")
    row_parts = lines[1].split(",")
    row_parts[size_idx] = "9999999"
    lines[1] = ",".join(row_parts)
    manifest_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="File size mismatch for"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_manifest_sha256_mismatch(tmp_path: Path):
    """Verify that tampering with sha256 in the manifest is detected."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_sha_mismatch"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Tamper with manifest sha256
    manifest_file = out_dir / "audit" / "dataset_manifest.csv"
    lines = manifest_file.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    sha_idx = header.index("sha256")
    row_parts = lines[1].split(",")
    row_parts[sha_idx] = "0" * 64
    lines[1] = ",".join(row_parts)
    manifest_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="Hash mismatch for"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_manifest_output_path_mismatch(tmp_path: Path):
    """Verify that tampering with output_path hierarchy in manifest is detected."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_path_mismatch"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Tamper with output_path to point to a nonexistent file in another class
    manifest_file = out_dir / "audit" / "dataset_manifest.csv"
    lines = manifest_file.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    path_idx = header.index("output_path")
    row_parts = lines[1].split(",")
    row_parts[path_idx] = "train/smoke/non_existent_img.jpg"
    lines[1] = ",".join(row_parts)
    manifest_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(DatasetVerificationError):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_disposition_not_approved(tmp_path: Path):
    """Verify that an unapproved disposition in the manifest raises DatasetVerificationError."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_disp_mismatch"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Tamper with disposition
    manifest_file = out_dir / "audit" / "dataset_manifest.csv"
    lines = manifest_file.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    disp_idx = header.index("disposition")
    row_parts = lines[1].split(",")
    row_parts[disp_idx] = "INVALID_STATUS"
    lines[1] = ",".join(row_parts)
    manifest_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="unapproved disposition 'INVALID_STATUS'"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_unexpected_top_level_directory(tmp_path: Path):
    """Verify that unexpected directory in dataset root is rejected."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_top_dir"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Add unexpected directory
    (out_dir / "unexpected_extra_dir").mkdir()

    with pytest.raises(DatasetVerificationError, match="Unexpected directory found in dataset root"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_untracked_loose_file_in_split(tmp_path: Path):
    """Verify that a loose file directly in a split directory is rejected."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_loose_file"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Add loose file in split directory
    (out_dir / "train" / "loose_file.txt").write_text("rogue_content")

    with pytest.raises(DatasetVerificationError, match="Untracked loose file found directly inside split directory"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_unexpected_class_directory(tmp_path: Path):
    """Verify that an unexpected class directory inside a split is rejected."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_bad_class"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Add unexpected class directory
    (out_dir / "train" / "extra_unrecognized_class").mkdir()

    with pytest.raises(DatasetVerificationError, match="Unexpected class directory found in 'train'"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_empty_class_directory(tmp_path: Path):
    """Verify that an empty class directory raises DatasetVerificationError."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_empty_class"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Delete all images in train/fire
    for f in (out_dir / "train" / "fire").iterdir():
        f.unlink()

    with pytest.raises(DatasetVerificationError, match="is empty. All classes must be populated"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_class_distribution_mismatch(tmp_path: Path):
    """Verify that mismatch between on-disk class_distribution.csv and disk is caught."""
    import csv
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_dist_mismatch"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Modify class_distribution.csv
    dist_file = out_dir / "audit" / "class_distribution.csv"
    with open(dist_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[0]["retained_count"] = "999"
    with open(dist_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(DatasetVerificationError, match="class_distribution.csv"):
        verify_prepared_dataset(out_dir, summary)


def test_verify_prepared_dataset_catches_dataset_summary_mismatch(tmp_path: Path):
    """Verify that mismatch between on-disk dataset_summary.json and disk is caught."""
    import json
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "out_summary_mismatch"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    summary = run_pipeline(archive_path=zip_path, output_dir=out_dir)

    # Modify dataset_summary.json
    sum_file = out_dir / "audit" / "dataset_summary.json"
    with open(sum_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["total_retained"] = 999
    with open(sum_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(DatasetVerificationError, match="dataset_summary.json retained count"):
        verify_prepared_dataset(out_dir, summary)


# ==============================================================================
# 9. ATOMIC PROMOTION, BACKUP, ROLLBACK & CLEANUP SAFETY
# ==============================================================================

def test_check_output_directory_prevents_silent_overwrite(tmp_path: Path):
    """Verify that existing prepared dataset directory cannot be overwritten without force."""
    out_dir = tmp_path / "existing_dataset"
    out_dir.mkdir(parents=True)
    (out_dir / "train").mkdir()

    with pytest.raises(OutputDirectoryConflictError):
        check_output_directory(out_dir, force=False)

    # With force: passes
    check_output_directory(out_dir, force=True)


def test_force_replacement_succeeds_cleanly(tmp_path: Path):
    """Verify that running with force=True safely replaces existing directory."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "force_target"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)

    # First run
    run_pipeline(archive_path=zip_path, output_dir=out_dir, force=False)
    assert out_dir.exists()

    # Second run without force raises
    with pytest.raises(OutputDirectoryConflictError):
        run_pipeline(archive_path=zip_path, output_dir=out_dir, force=False)

    # Second run with force succeeds
    run_pipeline(archive_path=zip_path, output_dir=out_dir, force=True)
    assert out_dir.exists()

    # Ensure no leftover temporary staging or backup directories
    sibling_names = [p.name for p in out_dir.parent.iterdir()]
    assert not any(name.startswith(".tmp_") for name in sibling_names)
    assert not any(name.startswith(".bak_") for name in sibling_names)


def test_staging_failure_preserves_existing_dataset(tmp_path: Path, monkeypatch):
    """Verify that if writing fails during staging, existing directory is untouched."""
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "preserve_target"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    run_pipeline(archive_path=zip_path, output_dir=out_dir)

    sentinel_file = out_dir / "sentinel.txt"
    sentinel_file.write_text("DO_NOT_DELETE")

    def mock_write_error(*args, **kwargs):
        raise RuntimeError("Simulated crash during dataset writing")

    monkeypatch.setattr("ml.data.prepare_fire_smoke_dataset.write_dataset_contents", mock_write_error)

    with pytest.raises(RuntimeError, match="Simulated crash during dataset writing"):
        run_pipeline(archive_path=zip_path, output_dir=out_dir, force=True)

    # Existing dataset and sentinel file must remain untouched
    assert out_dir.exists()
    assert sentinel_file.exists()
    assert sentinel_file.read_text() == "DO_NOT_DELETE"

    # Ensure no dangling temporary staging directory
    sibling_names = [p.name for p in out_dir.parent.iterdir()]
    assert not any(name.startswith(".tmp_") for name in sibling_names)


def test_verification_failure_restores_original_from_backup(tmp_path: Path, monkeypatch):
    """
    Verify that if verification fails during staging, existing directory
    remains completely untouched and staging directory is cleaned up.
    """
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "rollback_target"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    run_pipeline(archive_path=zip_path, output_dir=out_dir)

    marker = out_dir / "original_version.txt"
    marker.write_text("ORIGINAL_V1")

    # Mock verify_prepared_dataset to fail on second run
    def mock_verify(target_dir, expected_summary):
        raise DatasetVerificationError("Simulated verification failure on staged output")

    monkeypatch.setattr("ml.data.prepare_fire_smoke_dataset.verify_prepared_dataset", mock_verify)

    with pytest.raises(DatasetVerificationError, match="Simulated verification failure"):
        run_pipeline(archive_path=zip_path, output_dir=out_dir, force=True)

    # Verify original directory is completely preserved
    assert out_dir.exists()
    assert marker.exists()
    assert marker.read_text() == "ORIGINAL_V1"

    # Ensure temporary staging directory was cleaned up
    sibling_names = [p.name for p in out_dir.parent.iterdir()]
    assert not any(name.startswith(".tmp_") for name in sibling_names)
    assert not any(name.startswith(".bak_") for name in sibling_names)


def test_promotion_failure_restores_original_from_backup(tmp_path: Path, monkeypatch):
    """
    Verify that if promotion fails after backup is made, original directory
    is safely restored from backup.
    """
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "promo_rollback_target"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    run_pipeline(archive_path=zip_path, output_dir=out_dir)

    marker = out_dir / "must_survive.txt"
    marker.write_text("SURVIVOR")

    # Monkeypatch Path.rename on staging_dir to simulate rename failure
    real_rename = Path.rename

    def mock_rename(self, target):
        if ".tmp_" in self.name:
            raise OSError("Simulated filesystem rename failure during promotion")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", mock_rename)

    with pytest.raises(DatasetPreparationError, match="Failed to promote staging directory"):
        run_pipeline(archive_path=zip_path, output_dir=out_dir, force=True)

    # Target directory must have been restored from backup
    assert out_dir.exists()
    assert marker.exists()
    assert marker.read_text() == "SURVIVOR"

    # No leftover .tmp_ or .bak_ directories
    sibling_names = [p.name for p in out_dir.parent.iterdir()]
    assert not any(name.startswith(".tmp_") for name in sibling_names)
    assert not any(name.startswith(".bak_") for name in sibling_names)


def test_promotion_failure_backup_restoration_failure_preserves_backup_and_logs_critical(tmp_path: Path, monkeypatch, caplog):
    """
    Verify that if promotion fails AND subsequent backup restoration fails:
    1. logger.critical is emitted detailing both paths.
    2. The backup directory is preserved on disk for manual operator recovery.
    3. DatasetPreparationError is raised without masking the failure.
    """
    import logging
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "double_fault_target"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    run_pipeline(archive_path=zip_path, output_dir=out_dir)

    sentinel = out_dir / "must_not_be_lost.txt"
    sentinel.write_text("CRITICAL_DATA")

    real_rename = Path.rename

    def mock_rename(self, target):
        # Allow initial backup rename (output_dir -> .bak_)
        # Fail promotion rename (.tmp_ -> output_dir)
        # Fail restore rename (.bak_ -> output_dir)
        if ".tmp_" in self.name:
            raise OSError("Simulated promotion filesystem error")
        if ".bak_" in self.name:
            raise OSError("Simulated restore filesystem error")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", mock_rename)

    with caplog.at_level(logging.CRITICAL, logger="scout.ml.data_prep"):
        with pytest.raises(DatasetPreparationError, match="Failed to promote staging directory"):
            run_pipeline(archive_path=zip_path, output_dir=out_dir, force=True)

    # 1. Critical log was emitted with exact path
    assert any("CRITICAL: Failed to restore backup directory" in r.message for r in caplog.records)

    # 2. Backup directory MUST remain preserved on disk
    backup_dirs = [p for p in out_dir.parent.iterdir() if p.name.startswith(".bak_")]
    assert len(backup_dirs) == 1
    preserved_backup = backup_dirs[0]
    assert preserved_backup.exists()
    assert (preserved_backup / "must_not_be_lost.txt").read_text() == "CRITICAL_DATA"


def test_backup_cleanup_failure_preserves_promoted_dataset_and_logs_warning(tmp_path: Path, monkeypatch, caplog):
    """
    Verify that if promotion succeeds but old backup directory cleanup fails:
    1. The promoted dataset remains live and functional at output_dir.
    2. A WARNING log is emitted indicating manual cleanup is needed.
    3. Pipeline execution completes successfully without raising an exception.
    """
    import logging
    import shutil
    zip_path = tmp_path / "ds.zip"
    out_dir = tmp_path / "cleanup_fail_target"

    entries = {}
    for cls in ["fire", "smoke", "neutral"]:
        for i in range(5):
            entries[f"Train/{cls}/img_{i}.jpg"] = _make_class_image(cls, i, split="train")
        for j in range(2):
            entries[f"Test/{cls}/img_{j}.jpg"] = _make_class_image(cls, j, split="test")

    _create_synthetic_zip(zip_path, entries)
    run_pipeline(archive_path=zip_path, output_dir=out_dir)

    real_rmtree = shutil.rmtree

    def mock_rmtree(path, *args, **kwargs):
        if ".bak_" in str(path):
            raise OSError("Simulated permission error on old backup cleanup")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("shutil.rmtree", mock_rmtree)

    with caplog.at_level(logging.WARNING, logger="scout.ml.data_prep"):
        summary = run_pipeline(archive_path=zip_path, output_dir=out_dir, force=True)

    # 1. Pipeline succeeded without crashing
    assert summary["retained_images"] == 21
    assert out_dir.exists()
    assert (out_dir / "train" / "fire").is_dir()

    # 2. Warning was logged
    assert any("old backup cleanup failed" in r.message for r in caplog.records)

    # 3. Old backup still exists on disk for manual operator removal
    backup_dirs = [p for p in out_dir.parent.iterdir() if p.name.startswith(".bak_")]
    assert len(backup_dirs) == 1
    assert backup_dirs[0].exists()
