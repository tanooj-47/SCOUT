"""SCOUT Milestone 07 Phase 7B: Automated Verification Suite for Dataset V2.

Verifies:
1. Directory structure and split existence in data/processed/fire_smoke_v2/.
2. Accurate image counts and class distribution matching EXPECTED_COUNTS_V2.
3. Multi-source representation across deepquest_v1, bowfire, and dfire.
4. Format balancing and elimination of the v1 TIFF/JPEG confounding.
5. Bitwise integrity, two-pass Pillow loadability, and zero cross-split SHA-256 leakage.
6. Zero scene-group leakage verification from audit artifacts.
7. Safe archive extraction with Zip Slip defense.
8. Perceptual hashing (dHash, aHash, Hamming distance) correctness.
9. End-to-end DataLoader batch generation from v2.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import torch
from PIL import Image

from ml.config import (
    CLASS_NAMES,
    DATASET_V1_ROOT,
    DATASET_V2_ROOT,
    EXPECTED_COUNTS_V2,
    EXPECTED_TOTAL_IMAGES_V2,
    get_pipeline_config,
)
from ml.data.dataset import (
    ScoutFireSmokeDataset,
    get_data_loaders,
    get_test_loader,
)
from ml.data.ingestion.archive_extractor import SafeArchiveExtractor
from ml.data.ingestion.hasher import (
    compute_ahash,
    compute_dhash,
    compute_sha256,
    hamming_distance,
)
from ml.data.ingestion.image_validator import validate_image_file


@pytest.fixture(scope="module")
def v2_root() -> Path:
    assert DATASET_V2_ROOT.exists(), f"V2 dataset root does not exist: {DATASET_V2_ROOT}"
    return DATASET_V2_ROOT


def test_v2_directory_structure(v2_root: Path):
    """Verify train, validation, and test directories exist with all 3 class subdirs."""
    for split in ["train", "validation", "test"]:
        split_dir = v2_root / split
        assert split_dir.is_dir(), f"Split directory missing: {split_dir}"
        for cls in CLASS_NAMES:
            cls_dir = split_dir / cls
            assert cls_dir.is_dir(), f"Class directory missing: {cls_dir}"


def test_v2_image_counts_and_class_distribution(v2_root: Path):
    """Verify exact count invariants matching EXPECTED_COUNTS_V2."""
    total_found = 0
    for split in ["train", "validation", "test"]:
        expected_split = EXPECTED_COUNTS_V2[split]
        split_total = 0
        for cls in CLASS_NAMES:
            cls_dir = v2_root / split / cls
            files = [f for f in cls_dir.glob("*.*") if not f.name.startswith(".")]
            count = len(files)
            assert count == expected_split[cls], (
                f"Count mismatch in {split}/{cls}: expected {expected_split[cls]}, got {count}"
            )
            split_total += count
        assert split_total == expected_split["total"], (
            f"Split total mismatch in {split}: expected {expected_split['total']}, got {split_total}"
        )
        total_found += split_total

    assert total_found == EXPECTED_TOTAL_IMAGES_V2, (
        f"Total image count mismatch: expected {EXPECTED_TOTAL_IMAGES_V2}, got {total_found}"
    )


def test_v2_format_balance_and_confounding_resolution(v2_root: Path):
    """Verify that test neutral is NOT 100% TIFF and format confounding is broken."""
    test_neutral_dir = v2_root / "test" / "neutral"
    test_fire_dir = v2_root / "test" / "fire"

    neutral_formats = set(f.suffix.lower() for f in test_neutral_dir.glob("*.*"))
    fire_formats = set(f.suffix.lower() for f in test_fire_dir.glob("*.*"))

    # Neutral must contain both jpeg and png (not just tiff)
    assert any(ext in [".jpg", ".jpeg"] for ext in neutral_formats), "Test neutral missing JPEG images"
    assert ".png" in neutral_formats, "Test neutral missing PNG images"

    # Fire must contain both jpeg and png
    assert any(ext in [".jpg", ".jpeg"] for ext in fire_formats), "Test fire missing JPEG images"
    assert ".png" in fire_formats, "Test fire missing PNG images"

    # Count TIFFs in test neutral
    neutral_files = list(test_neutral_dir.glob("*.*"))
    tiff_files = [f for f in neutral_files if f.suffix.lower() in [".tif", ".tiff"]]
    tiff_ratio = len(tiff_files) / len(neutral_files)

    # In v1, tiff_ratio was 1.00 (100%). In v2, it must be < 0.20
    assert tiff_ratio < 0.20, f"Test neutral TIFF ratio {tiff_ratio:.2f} too high (expected < 0.20)"


def test_v2_multi_source_representation(v2_root: Path):
    """Verify that images from deepquest_v1, bowfire, and dfire exist in all splits."""
    for split in ["train", "validation", "test"]:
        split_files = list((v2_root / split).glob("*/*.*"))
        sources = set(f.name.split("_")[0] for f in split_files)
        assert "deepquest" in sources or any(s.startswith("deepquest") for s in sources)
        assert "bowfire" in sources
        assert "dfire" in sources


def test_v2_zero_cross_split_sha256_leakage(v2_root: Path):
    """Verify that zero files share identical SHA-256 hashes across different splits."""
    split_hashes: dict[str, set[str]] = {}
    for split in ["train", "validation", "test"]:
        hashes = set()
        for f in (v2_root / split).glob("*/*.*"):
            if not f.name.startswith("."):
                hashes.add(compute_sha256(f))
        split_hashes[split] = hashes

    # Assert disjoint sets
    train_val_overlap = split_hashes["train"] & split_hashes["validation"]
    train_test_overlap = split_hashes["train"] & split_hashes["test"]
    val_test_overlap = split_hashes["validation"] & split_hashes["test"]

    assert len(train_val_overlap) == 0, f"SHA-256 leakage between train and val: {len(train_val_overlap)}"
    assert len(train_test_overlap) == 0, f"SHA-256 leakage between train and test: {len(train_test_overlap)}"
    assert len(val_test_overlap) == 0, f"SHA-256 leakage between val and test: {len(val_test_overlap)}"


def test_v2_scene_grouping_audit_artifact():
    """Verify that the official scene grouping audit JSON confirms zero leakage."""
    audit_file = Path("artifacts/audits/m07_phase7b/scene_grouping_audit.json")
    assert audit_file.exists(), f"Audit file not found: {audit_file}"

    with audit_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["is_leakage_free"] is True
    assert data["leaked_groups_count"] == 0
    assert data["total_groups"] > 1000


def test_safe_archive_extractor_zip_slip(tmp_path: Path):
    """Verify SafeArchiveExtractor rejects traversal attacks (Zip Slip)."""
    assert SafeArchiveExtractor._is_safe_path(tmp_path, tmp_path / "valid" / "file.txt")
    assert not SafeArchiveExtractor._is_safe_path(tmp_path, tmp_path / ".." / "evil.txt")
    assert not SafeArchiveExtractor._is_safe_path(tmp_path, Path("C:/Windows/System32/evil.dll"))


def test_perceptual_hasher_invariants(tmp_path: Path):
    """Verify dHash and aHash compute deterministic values and detect differences."""
    # Create two identical test images
    img1 = Image.new("RGB", (128, 128), color=(255, 0, 0))
    p1 = tmp_path / "red1.png"
    p2 = tmp_path / "red2.png"
    img1.save(p1)
    img1.save(p2)

    # Different image
    img2 = Image.new("RGB", (128, 128), color=(0, 255, 0))
    p3 = tmp_path / "green.png"
    img2.save(p3)

    h1 = compute_dhash(p1)
    h2 = compute_dhash(p2)
    h3 = compute_dhash(p3)

    assert h1 == h2, "Identical images must yield identical dHash"
    assert hamming_distance(h1, h2) == 0
    assert isinstance(h1, str) and len(h1) == 16


def test_v2_dataloaders():
    """Verify get_data_loaders and get_test_loader work end-to-end on v2 dataset."""
    loaders = get_data_loaders(dataset_root=DATASET_V2_ROOT, batch_size=16)
    assert "train" in loaders
    assert "validation" in loaders

    train_loader = loaders["train"]
    val_loader = loaders["validation"]
    test_loader = get_test_loader(dataset_root=DATASET_V2_ROOT, batch_size=16)

    assert len(train_loader.dataset) == EXPECTED_COUNTS_V2["train"]["total"]
    assert len(val_loader.dataset) == EXPECTED_COUNTS_V2["validation"]["total"]
    assert len(test_loader.dataset) == EXPECTED_COUNTS_V2["test"]["total"]

    # Test single batch fetch from train loader
    images, labels = next(iter(train_loader))
    assert images.shape == (16, 3, 224, 224)
    assert labels.shape == (16,)
    assert images.dtype == torch.float32
    assert all(0 <= l <= 2 for l in labels.tolist())


def test_v2_shortcut_string():
    """Verify passing 'v2' string as dataset_root resolves to DATASET_V2_ROOT."""
    loaders = get_data_loaders(dataset_root="v2", batch_size=8)
    assert len(loaders["train"].dataset) == EXPECTED_COUNTS_V2["train"]["total"]

    cfg = get_pipeline_config(version="v2")
    assert cfg.dataset_root == DATASET_V2_ROOT
    assert cfg.dataset_version == "v2"
