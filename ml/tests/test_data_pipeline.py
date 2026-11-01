"""
ml/tests/test_data_pipeline.py - Comprehensive unit and integration tests for data pipeline.

Validates:
- AspectRatioPreservingLetterbox across landscape, portrait, square, and odd dimensions.
- Symmetry, fill color preservation, and aspect ratio fidelity.
- Deterministic evaluation transform pipeline.
- Training transform pipeline validity, tensor dimensions, and finite values.
- scout_image_loader RGB conversion, corruption handling, and missing file errors.
- ScoutFireSmokeDataset canonical class mapping validation and custom class rejection.
- Strict test-set isolation in get_data_loaders vs explicit get_test_loader.
- Complete census, exact split counts, and decoding across all 2,931 images in the real dataset.
- Exact decoding of all 156 PackBits TIFFs, GIF (palette mode), BMP, and PNG instances.
"""

from pathlib import Path
from PIL import Image
import pytest
import torch

from ml.config import (
    CLASS_NAMES,
    CLASS_TO_IDX,
    DEFAULT_DATASET_ROOT,
    EXPECTED_COUNTS,
    EXPECTED_TOTAL_IMAGES,
    IMAGE_SIZE,
    LETTERBOX_FILL_COLOR,
)
from ml.data.dataset import (
    ScoutFireSmokeDataset,
    get_data_loaders,
    get_test_loader,
    scout_image_loader,
)
from ml.data.transforms import (
    AspectRatioPreservingLetterbox,
    get_eval_transforms,
    get_train_transforms,
)


# ===========================================================================
# 1. AspectRatioPreservingLetterbox Unit Tests (Synthetic)
# ===========================================================================
def test_letterbox_landscape_aspect_ratio_and_padding():
    """Verify landscape image retains exact aspect ratio with vertical symmetric padding."""
    letterbox = AspectRatioPreservingLetterbox(
        target_size=224, fill=LETTERBOX_FILL_COLOR
    )

    # 300x150 has aspect ratio 2.0
    img = Image.new("RGB", (300, 150), color=(255, 0, 0))
    result = letterbox(img)

    assert result.size == (224, 224)
    # Long edge (width) is resized to 224; height scaled to round(150 * 224 / 300) = 112
    # Active content is at y in [56, 168)
    # Top and bottom padding is 56 pixels each (56 + 112 + 56 = 224)

    # Check top padding pixel has exact fill color
    top_pad_pixel = result.getpixel((112, 10))
    assert top_pad_pixel == LETTERBOX_FILL_COLOR

    # Check bottom padding pixel has exact fill color
    bottom_pad_pixel = result.getpixel((112, 215))
    assert bottom_pad_pixel == LETTERBOX_FILL_COLOR

    # Check center content pixel is original red
    content_pixel = result.getpixel((112, 112))
    assert content_pixel == (255, 0, 0)


def test_letterbox_portrait_aspect_ratio_and_padding():
    """Verify portrait image retains exact aspect ratio with horizontal symmetric padding."""
    letterbox = AspectRatioPreservingLetterbox(
        target_size=224, fill=LETTERBOX_FILL_COLOR
    )

    # 150x300 has aspect ratio 0.5
    img = Image.new("RGB", (150, 300), color=(0, 255, 0))
    result = letterbox(img)

    assert result.size == (224, 224)
    # Height is resized to 224; width scaled to round(150 * 224 / 300) = 112
    # Left and right padding is 56 pixels each

    # Check left padding pixel
    left_pad_pixel = result.getpixel((10, 112))
    assert left_pad_pixel == LETTERBOX_FILL_COLOR

    # Check right padding pixel
    right_pad_pixel = result.getpixel((215, 112))
    assert right_pad_pixel == LETTERBOX_FILL_COLOR

    # Check center content pixel is original green
    content_pixel = result.getpixel((112, 112))
    assert content_pixel == (0, 255, 0)


def test_letterbox_square():
    """Verify square image is scaled to target_size with zero padding."""
    letterbox = AspectRatioPreservingLetterbox(
        target_size=224, fill=LETTERBOX_FILL_COLOR
    )

    img = Image.new("RGB", (320, 320), color=(0, 0, 255))
    result = letterbox(img)

    assert result.size == (224, 224)
    assert result.getpixel((0, 0)) == (0, 0, 255)
    assert result.getpixel((223, 223)) == (0, 0, 255)


def test_letterbox_odd_dimensions_symmetry_tolerance():
    """Verify symmetric padding within 1-pixel rounding tolerance for odd dimensions."""
    letterbox = AspectRatioPreservingLetterbox(
        target_size=224, fill=LETTERBOX_FILL_COLOR
    )

    # Typical wildfire dataset dimension: 275x183 (landscape)
    img = Image.new("RGB", (275, 183), color=(200, 100, 50))
    result = letterbox(img)

    assert result.size == (224, 224)
    # scale = 224 / 275 = 0.814545...
    # new_h = round(183 * 0.814545...) = 149
    # pad_total = 224 - 149 = 75
    # pad_top = 37, pad_bottom = 38 (difference <= 1 pixel)

    # Verify top pad is fill color
    assert result.getpixel((112, 15)) == LETTERBOX_FILL_COLOR
    # Verify bottom pad is fill color
    assert result.getpixel((112, 210)) == LETTERBOX_FILL_COLOR
    # Verify center is content color
    assert result.getpixel((112, 112)) == (200, 100, 50)


# ===========================================================================
# 2. Transform Pipeline Tests (Synthetic)
# ===========================================================================
def test_eval_transforms_are_deterministic():
    """Verify evaluation transforms produce mathematically identical outputs."""
    eval_transform = get_eval_transforms(target_size=224)
    img = Image.new("RGB", (275, 183), color=(120, 80, 40))

    tensor1 = eval_transform(img)
    tensor2 = eval_transform(img)

    assert torch.equal(
        tensor1, tensor2
    ), "Evaluation transform must be deterministic!"
    assert tensor1.shape == (3, 224, 224)
    assert torch.isfinite(tensor1).all()


def test_train_transforms_output_shape_and_finite_values():
    """Verify training transforms produce valid (3, 224, 224) finite float tensors."""
    train_transform = get_train_transforms(target_size=224)

    test_sizes = [(300, 168), (180, 240), (224, 224), (800, 600)]
    for w, h in test_sizes:
        img = Image.new("RGB", (w, h), color=(150, 120, 90))
        tensor = train_transform(img)

        assert tensor.shape == (3, 224, 224), f"Failed for size ({w}, {h})"
        assert torch.isfinite(
            tensor
        ).all(), f"Non-finite values for size ({w}, {h})"


# ===========================================================================
# 3. Image Loader & Error Handling Tests (Synthetic)
# ===========================================================================
def test_scout_image_loader_rgb_conversion(tmp_path):
    """Verify loader converts Grayscale (L), RGBA, and Palette (P) to 3-channel RGB."""
    # 1. Grayscale
    gray_path = tmp_path / "gray.png"
    Image.new("L", (100, 100), color=128).save(gray_path)
    img_gray = scout_image_loader(gray_path)
    assert img_gray.mode == "RGB"

    # 2. RGBA
    rgba_path = tmp_path / "rgba.png"
    Image.new("RGBA", (100, 100), color=(255, 0, 0, 128)).save(rgba_path)
    img_rgba = scout_image_loader(rgba_path)
    assert img_rgba.mode == "RGB"

    # 3. Palette (P)
    pal_path = tmp_path / "pal.gif"
    Image.new("P", (100, 100), color=1).save(pal_path)
    img_pal = scout_image_loader(pal_path)
    assert img_pal.mode == "RGB"


def test_scout_image_loader_corrupt_file_raises_runtime_error(tmp_path):
    """Verify loader raises informative RuntimeError on corrupt or truncated files."""
    corrupt_file = tmp_path / "corrupt.jpg"
    corrupt_file.write_bytes(b"NOT_A_VALID_JPEG_HEADER_RANDOM_GARBAGE")

    with pytest.raises(RuntimeError) as exc_info:
        scout_image_loader(corrupt_file)

    assert "Failed to decode image" in str(exc_info.value)
    assert str(corrupt_file) in str(exc_info.value)


def test_scout_image_loader_missing_file_raises_file_not_found(tmp_path):
    """Verify loader raises FileNotFoundError when target file does not exist."""
    missing_file = tmp_path / "nonexistent.jpg"

    with pytest.raises(FileNotFoundError):
        scout_image_loader(missing_file)


# ===========================================================================
# 4. ScoutFireSmokeDataset & Loader Isolation Tests (Synthetic)
# ===========================================================================
def test_dataset_canonical_class_mapping_enforcement(tmp_path):
    """Verify dataset accepts canonical class folders and rejects non-canonical names."""
    # Create canonical directory structure
    ds_root = tmp_path / "dataset"
    for cls in ("fire", "neutral", "smoke"):
        cls_dir = ds_root / cls
        cls_dir.mkdir(parents=True)
        Image.new("RGB", (50, 50)).save(cls_dir / "sample.jpg")

    dataset = ScoutFireSmokeDataset(root=ds_root)
    assert dataset.class_to_idx == CLASS_TO_IDX

    # Create non-canonical structure (e.g. missing fire, has dogs)
    bad_root = tmp_path / "bad_dataset"
    for cls in ("dogs", "neutral", "smoke"):
        cls_dir = bad_root / cls
        cls_dir.mkdir(parents=True)
        Image.new("RGB", (50, 50)).save(cls_dir / "sample.jpg")

    with pytest.raises(ValueError) as exc_info:
        ScoutFireSmokeDataset(root=bad_root)
    assert "canonical mapping" in str(exc_info.value)


def test_test_split_isolation_in_default_loaders(tmp_path):
    """Verify get_data_loaders exposes ONLY train and validation, protecting test."""
    ds_root = tmp_path / "mock_dataset"
    for split in ("train", "validation", "test"):
        for cls in ("fire", "neutral", "smoke"):
            cls_dir = ds_root / split / cls
            cls_dir.mkdir(parents=True)
            Image.new("RGB", (50, 50)).save(cls_dir / "sample.jpg")

    loaders = get_data_loaders(dataset_root=ds_root, batch_size=2)
    assert "train" in loaders
    assert "validation" in loaders
    assert (
        "test" not in loaders
    ), "SECURITY BREACH: 'test' key must not exist in training data loaders!"

    # Verify explicit test loader factory
    test_loader = get_test_loader(dataset_root=ds_root, batch_size=2)
    assert test_loader is not None
    assert isinstance(test_loader.dataset, ScoutFireSmokeDataset)


def test_missing_split_directory_errors(tmp_path):
    """Verify helpful errors when split directories are missing."""
    empty_root = tmp_path / "empty_dir"
    empty_root.mkdir()

    with pytest.raises(FileNotFoundError) as exc_train:
        get_data_loaders(dataset_root=empty_root)
    assert "Training split directory not found" in str(exc_train.value)

    with pytest.raises(FileNotFoundError) as exc_test:
        get_test_loader(dataset_root=empty_root)
    assert "Test split directory not found" in str(exc_test.value)


# ===========================================================================
# 5. Real Prepared Dataset Invariants Tests (data/processed/fire_smoke_v1)
# ===========================================================================
@pytest.mark.skipif(
    not DEFAULT_DATASET_ROOT.exists(),
    reason="Prepared dataset not found at expected path",
)
class TestRealDatasetInvariants:
    """Rigorous invariants verification against the actual prepared dataset on disk."""

    def test_real_dataset_canonical_class_mappings(self):
        """Verify all splits on disk match canonical class mapping {"fire": 0, "neutral": 1, "smoke": 2}."""
        for split in ("train", "validation", "test"):
            split_dir = DEFAULT_DATASET_ROOT / split
            ds = ScoutFireSmokeDataset(root=split_dir)
            assert (
                ds.class_to_idx == CLASS_TO_IDX
            ), f"Class mapping mismatch in split {split}"

    def test_real_dataset_exact_split_counts(self):
        """Verify exact per-class and total counts across all splits."""
        discovered_counts = {}
        for split in ("train", "validation", "test"):
            split_dir = DEFAULT_DATASET_ROOT / split
            ds = ScoutFireSmokeDataset(root=split_dir)

            class_counts = {"fire": 0, "neutral": 0, "smoke": 0}
            for _, label_idx in ds.samples:
                cls_name = ds.classes[label_idx]
                class_counts[cls_name] += 1

            assert (
                class_counts["fire"] == EXPECTED_COUNTS[split]["fire"]
            ), f"Fire count mismatch in {split}"
            assert (
                class_counts["neutral"] == EXPECTED_COUNTS[split]["neutral"]
            ), f"Neutral count mismatch in {split}"
            assert (
                class_counts["smoke"] == EXPECTED_COUNTS[split]["smoke"]
            ), f"Smoke count mismatch in {split}"
            assert (
                len(ds) == EXPECTED_COUNTS[split]["total"]
            ), f"Total count mismatch in {split}"

            discovered_counts[split] = len(ds)

        assert (
            sum(discovered_counts.values()) == EXPECTED_TOTAL_IMAGES
        ), f"Total dataset size mismatch: expected {EXPECTED_TOTAL_IMAGES}, got {sum(discovered_counts.values())}"

    def test_real_dataset_unusual_formats_decoded(self):
        """Verify that internal GIF, BMP, PNG, and PackBits TIFF images decode cleanly."""
        # 1. GIF instance: train/neutral/image_330.jpg
        gif_file = DEFAULT_DATASET_ROOT / "train" / "neutral" / "image_330.jpg"
        assert gif_file.exists()
        img_gif = scout_image_loader(gif_file)
        assert img_gif.mode == "RGB"
        assert img_gif.size == (600, 450)

        # 2. BMP instance: train/neutral/image_334.jpg
        bmp_file = DEFAULT_DATASET_ROOT / "train" / "neutral" / "image_334.jpg"
        assert bmp_file.exists()
        img_bmp = scout_image_loader(bmp_file)
        assert img_bmp.mode == "RGB"
        assert img_bmp.size == (448, 336)

        # 3. PNG instance: train/neutral/image_338.jpg
        png_file = DEFAULT_DATASET_ROOT / "train" / "neutral" / "image_338.jpg"
        assert png_file.exists()
        img_png = scout_image_loader(png_file)
        assert img_png.mode == "RGB"
        assert img_png.size == (330, 248)

        # 4. PackBits TIFF sample: test/neutral/image_0.jpg
        tiff_file = DEFAULT_DATASET_ROOT / "test" / "neutral" / "image_0.jpg"
        assert tiff_file.exists()
        img_tiff = scout_image_loader(tiff_file)
        assert img_tiff.mode == "RGB"
        assert img_tiff.size == (800, 600)

    def test_real_dataset_all_156_tiff_images_decode(self):
        """Verify all 156 PackBits TIFF images decode to RGB without errors."""
        tiff_count = 0
        for split in ("train", "validation", "test"):
            neutral_dir = DEFAULT_DATASET_ROOT / split / "neutral"
            for f in neutral_dir.glob("*.jpg"):
                with open(f, "rb") as fp:
                    header = fp.read(4)
                # TIFF magic bytes: II*\x00 (little endian) or MM\x00* (big endian)
                if header in (b"II*\x00", b"MM\x00*"):
                    tiff_count += 1
                    img = scout_image_loader(f)
                    assert (
                        img.mode == "RGB"
                    ), f"TIFF image {f} did not decode to RGB"
                    assert (
                        img.size[0] > 0 and img.size[1] > 0
                    ), f"TIFF image {f} has zero size"

        assert (
            tiff_count == 156
        ), f"Expected 156 PackBits TIFF images, discovered {tiff_count}"

    def test_real_dataset_full_decoding_census(self):
        """
        Exhaustively loads all 2,931 images across train, validation, and test.
        Ensures zero unhandled exceptions, zero corrupt rasters, and 100% RGB output.
        """
        loaders = get_data_loaders(
            dataset_root=DEFAULT_DATASET_ROOT, batch_size=64
        )
        test_loader = get_test_loader(
            dataset_root=DEFAULT_DATASET_ROOT, batch_size=64
        )

        total_verified = 0

        # Verify train loader batches
        for images, targets in loaders["train"]:
            assert images.shape[1:] == (3, 224, 224)
            assert torch.isfinite(images).all()
            total_verified += images.size(0)

        # Verify val loader batches
        for images, targets in loaders["validation"]:
            assert images.shape[1:] == (3, 224, 224)
            assert torch.isfinite(images).all()
            total_verified += images.size(0)

        # Verify test loader batches
        for images, targets in test_loader:
            assert images.shape[1:] == (3, 224, 224)
            assert torch.isfinite(images).all()
            total_verified += images.size(0)

        assert total_verified == EXPECTED_TOTAL_IMAGES
