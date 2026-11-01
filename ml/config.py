"""
ml/config.py - Centralized configuration for SCOUT wildfire image classification.

Provides paths, dataset specifications, preprocessing constants, loader configurations,
and canonical label mappings for the wildfire dataset.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Project Paths
# ---------------------------------------------------------------------------
# Root directory of the SCOUT repository
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Dataset roots for v1 (DeepQuest baseline) and v2 (Multi-Source hardened)
DATASET_V1_ROOT = PROJECT_ROOT / "data" / "processed" / "fire_smoke_v1"
DATASET_V2_ROOT = PROJECT_ROOT / "data" / "processed" / "fire_smoke_v2"

# Default dataset root for prepared wildfire dataset (maintains backwards compatibility with v1)
DEFAULT_DATASET_ROOT = DATASET_V1_ROOT

# ---------------------------------------------------------------------------
# Canonical Class Mappings
# ---------------------------------------------------------------------------
CLASS_NAMES: Tuple[str, ...] = ("fire", "neutral", "smoke")

CLASS_TO_IDX: Dict[str, int] = {
    "fire": 0,
    "neutral": 1,
    "smoke": 2,
}

IDX_TO_CLASS: Dict[int, str] = {v: k for k, v in CLASS_TO_IDX.items()}
NUM_CLASSES: int = len(CLASS_NAMES)

# ---------------------------------------------------------------------------
# Image Preprocessing & Normalization Constants
# ---------------------------------------------------------------------------
IMAGE_SIZE: int = 224
INPUT_CHANNELS: int = 3

# Standard ImageNet RGB mean and standard deviation
IMAGENET_MEAN: Tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: Tuple[float, float, float] = (0.229, 0.224, 0.225)

# Neutral letterbox padding fill color (ImageNet uint8 channel mean: [124, 116, 104])
LETTERBOX_FILL_COLOR: Tuple[int, int, int] = (124, 116, 104)

# ---------------------------------------------------------------------------
# Supported File Formats
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS: Tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".gif",
    ".ppm",
    ".pgm",
)

# ---------------------------------------------------------------------------
# DataLoader & Execution Defaults
# ---------------------------------------------------------------------------
DEFAULT_BATCH_SIZE: int = 32
DEFAULT_NUM_WORKERS: int = 0
DEFAULT_PIN_MEMORY: bool = False
RANDOM_SEED: int = 42
DEVICE: str = "cpu"

# ---------------------------------------------------------------------------
# Verified Dataset Accounting Invariants
# ---------------------------------------------------------------------------
EXPECTED_COUNTS: Dict[str, Dict[str, int]] = {
    "train": {
        "fire": 673,
        "neutral": 718,
        "smoke": 715,
        "total": 2106,
    },
    "validation": {
        "fire": 168,
        "neutral": 180,
        "smoke": 179,
        "total": 527,
    },
    "test": {
        "fire": 98,
        "neutral": 100,
        "smoke": 100,
        "total": 298,
    },
}
EXPECTED_TOTAL_IMAGES: int = 2931
EXPECTED_COUNTS_V1 = EXPECTED_COUNTS
EXPECTED_TOTAL_IMAGES_V1 = EXPECTED_TOTAL_IMAGES

# Hardened v2 Multi-Source Dataset Invariants (Phase 7B)
EXPECTED_COUNTS_V2: Dict[str, Dict[str, int]] = {
    "train": {
        "fire": 810,
        "neutral": 841,
        "smoke": 800,
        "total": 2451,
    },
    "validation": {
        "fire": 173,
        "neutral": 179,
        "smoke": 171,
        "total": 523,
    },
    "test": {
        "fire": 175,
        "neutral": 185,
        "smoke": 173,
        "total": 533,
    },
}
EXPECTED_TOTAL_IMAGES_V2: int = 3507


# ---------------------------------------------------------------------------
# Configuration Dataclass & Validator
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PipelineConfig:
    """Immutable runtime configuration container for dataset and model pipelines."""

    dataset_root: Path = DEFAULT_DATASET_ROOT
    dataset_version: str = "v1"
    image_size: int = IMAGE_SIZE
    batch_size: int = DEFAULT_BATCH_SIZE
    num_workers: int = DEFAULT_NUM_WORKERS
    pin_memory: bool = DEFAULT_PIN_MEMORY
    random_seed: int = RANDOM_SEED
    device: str = DEVICE

    def __post_init__(self) -> None:
        if self.image_size <= 0:
            raise ValueError(f"image_size must be positive, got {self.image_size}")
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")
        if self.num_workers < 0:
            raise ValueError(f"num_workers cannot be negative, got {self.num_workers}")

    @property
    def train_dir(self) -> Path:
        return self.dataset_root / "train"

    @property
    def val_dir(self) -> Path:
        return self.dataset_root / "validation"

    @property
    def test_dir(self) -> Path:
        return self.dataset_root / "test"

    @property
    def audit_dir(self) -> Path:
        return self.dataset_root / "audit"

    def validate_directories(self, require_test: bool = False) -> None:
        """Validates that expected split directories exist on disk."""
        if not self.dataset_root.exists():
            raise FileNotFoundError(
                f"Dataset root directory does not exist: {self.dataset_root}"
            )
        if not self.train_dir.exists():
            raise FileNotFoundError(
                f"Training split directory does not exist: {self.train_dir}"
            )
        if not self.val_dir.exists():
            raise FileNotFoundError(
                f"Validation split directory does not exist: {self.val_dir}"
            )
        if require_test and not self.test_dir.exists():
            raise FileNotFoundError(
                f"Test split directory does not exist: {self.test_dir}"
            )


def get_pipeline_config(version: str = "v2", **overrides) -> PipelineConfig:
    """Helper factory to instantiate PipelineConfig for v1 or v2 datasets."""
    ver = version.lower()
    root = DATASET_V2_ROOT if ver == "v2" else DATASET_V1_ROOT
    kwargs = {
        "dataset_root": root,
        "dataset_version": ver,
        **overrides,
    }
    return PipelineConfig(**kwargs)


# Default global instance
default_config = PipelineConfig()
