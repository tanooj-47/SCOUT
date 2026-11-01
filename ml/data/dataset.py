"""
ml/data/dataset.py - Dataset loading and strict split isolation for wildfire classification.

Provides:
- scout_image_loader: Robust Pillow loader decoding JPEG, PackBits TIFF, GIF (palette),
  PNG, and BMP into 3-channel RGB with safe handle disposal and corruption detection.
- ScoutFireSmokeDataset: ImageFolder-compatible dataset enforcing the canonical
  mapping {"fire": 0, "neutral": 1, "smoke": 2} and broad format discovery.
- get_data_loaders: Factory for training and validation DataLoaders strictly isolating
  the test partition.
- get_test_loader: Separately named, explicitly invoked DataLoader for final model
  evaluation on the test partition.
"""

from pathlib import Path
from typing import Callable, Dict, Optional, Union
from PIL import Image, UnidentifiedImageError
import torch
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

from ml.config import (
    CLASS_NAMES,
    CLASS_TO_IDX,
    DATASET_V1_ROOT,
    DATASET_V2_ROOT,
    DEFAULT_BATCH_SIZE,
    DEFAULT_DATASET_ROOT,
    DEFAULT_NUM_WORKERS,
    DEFAULT_PIN_MEMORY,
    IMAGE_SIZE,
    SUPPORTED_EXTENSIONS,
)
from ml.data.transforms import get_eval_transforms, get_train_transforms


def is_supported_image_file(filename: str) -> bool:
    """Returns True if the file has any supported raster image extension."""
    lower_name = filename.lower()
    return any(lower_name.endswith(ext) for ext in SUPPORTED_EXTENSIONS)


def scout_image_loader(path: Union[str, Path]) -> Image.Image:
    """
    Safely opens, decodes, and converts an image to a 3-channel RGB PIL Image.

    Supports JPEG, PackBits TIFF, GIF (palette mode), BMP, PNG, and WebP regardless
    of filename extension. Loads entire raster data into memory via img.load()
    before closing the underlying file handle, preventing dangling descriptors or
    truncated streams.

    Raises:
        FileNotFoundError: If the target file does not exist.
        RuntimeError: If image decoding fails, is truncated, or the image is corrupt.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Image file does not exist: {file_path}")

    try:
        with open(file_path, "rb") as f:
            with Image.open(f) as img:
                img.load()  # Force reading entire raster into memory
                return img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RuntimeError(
            f"Failed to decode image at '{file_path}': {type(exc).__name__}: {exc}"
        ) from exc


class ScoutFireSmokeDataset(ImageFolder):
    """
    Production dataset for SCOUT wildfire classification.

    Inherits from torchvision.datasets.ImageFolder with the following guarantees:
    1. Robust file discovery across all approved extensions (.jpg, .png, .bmp, .tif, .gif, etc.).
    2. Uses scout_image_loader to safely decode all formats and convert them to 3-channel RGB.
    3. Strict enforcement of canonical class mapping: {"fire": 0, "neutral": 1, "smoke": 2}.
    """

    def __init__(
        self,
        root: Union[str, Path],
        transform: Optional[Callable] = None,
        target_transform: Optional[Callable] = None,
    ) -> None:
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(f"Dataset directory does not exist: {root_path}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"Dataset path is not a directory: {root_path}")

        super().__init__(
            root=str(root_path),
            transform=transform,
            target_transform=target_transform,
            loader=scout_image_loader,
            is_valid_file=is_supported_image_file,
        )

        # Enforce canonical class-to-index invariant
        if self.class_to_idx != CLASS_TO_IDX:
            raise ValueError(
                f"Discovered class mapping in '{root_path}' ({self.class_to_idx}) "
                f"does not match canonical mapping ({CLASS_TO_IDX})."
            )


def get_data_loaders(
    dataset_root: Union[str, Path] = DEFAULT_DATASET_ROOT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    num_workers: int = DEFAULT_NUM_WORKERS,
    pin_memory: bool = DEFAULT_PIN_MEMORY,
    image_size: int = IMAGE_SIZE,
    generator: Optional[torch.Generator] = None,
) -> Dict[str, DataLoader]:
    """
    Creates and returns DataLoaders for 'train' and 'validation' splits ONLY.

    Strict Test-Set Isolation:
        This factory explicitly omits the test partition to guarantee that training,
        validation, and hyperparameter tuning workflows cannot access, evaluate, or leak
        test set samples. Test evaluation is restricted to the explicitly named `get_test_loader()`.

    Determinism & Worker Policy:
        Enforces num_workers=0 to ensure single-process deterministic execution and
        guarantee that the training DataLoader generator state can be faithfully saved
        and restored by checkpoint managers without multi-process IPC state divergence.

    Args:
        dataset_root: Path to prepared dataset root directory.
        batch_size: Number of samples per batch.
        num_workers: Must be 0 for deterministic execution.
        pin_memory: Whether to copy tensors into CUDA pinned memory.
        image_size: Target spatial dimension for letterboxing.
        generator: Optional dedicated PyTorch Generator for reproducible shuffle sequencing.

    Returns:
        Dict[str, DataLoader] with keys 'train' and 'validation'.
    """
    if num_workers != 0:
        raise ValueError(
            f"Unsupported worker configuration: num_workers must be 0 for deterministic "
            f"execution and generator state restoration, got {num_workers}."
        )

    if str(dataset_root).strip().lower() == "v2":
        root_path = DATASET_V2_ROOT
    elif str(dataset_root).strip().lower() == "v1":
        root_path = DATASET_V1_ROOT
    else:
        root_path = Path(dataset_root)
    train_dir = root_path / "train"
    val_dir = root_path / "validation"

    if not train_dir.exists():
        raise FileNotFoundError(f"Training split directory not found: {train_dir}")
    if not val_dir.exists():
        raise FileNotFoundError(f"Validation split directory not found: {val_dir}")

    train_dataset = ScoutFireSmokeDataset(
        root=train_dir,
        transform=get_train_transforms(target_size=image_size),
    )
    val_dataset = ScoutFireSmokeDataset(
        root=val_dir,
        transform=get_eval_transforms(target_size=image_size),
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        generator=generator,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )

    return {
        "train": train_loader,
        "validation": val_loader,
    }


def get_test_loader(
    dataset_root: Union[str, Path] = DEFAULT_DATASET_ROOT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    num_workers: int = DEFAULT_NUM_WORKERS,
    pin_memory: bool = DEFAULT_PIN_MEMORY,
    image_size: int = IMAGE_SIZE,
) -> DataLoader:
    """
    Separately named, explicitly invoked DataLoader factory for the 'test' partition.

    Must only be called after champion model selection is finalized.
    Uses deterministic evaluation transforms and sequential sampling (shuffle=False).

    Returns:
        DataLoader bound to the test partition.
    """
    if str(dataset_root).strip().lower() == "v2":
        root_path = DATASET_V2_ROOT
    elif str(dataset_root).strip().lower() == "v1":
        root_path = DATASET_V1_ROOT
    else:
        root_path = Path(dataset_root)
    test_dir = root_path / "test"

    if not test_dir.exists():
        raise FileNotFoundError(f"Test split directory not found: {test_dir}")

    test_dataset = ScoutFireSmokeDataset(
        root=test_dir,
        transform=get_eval_transforms(target_size=image_size),
    )

    return DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )
