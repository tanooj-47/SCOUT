"""Image Metadata Profiling and Feature Extraction.

Extracts container formats, geometric properties, cryptographic checksums,
perceptual hashes, and color channel statistics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Union
import numpy as np
from PIL import Image

from ml.data.ingestion.hasher import compute_ahash, compute_dhash, compute_sha256


@dataclass
class ImageMetadata:
    """Comprehensive image profile metadata."""
    file_path: str
    file_name: str
    sha256: str
    size_bytes: int
    format: str
    mode: str
    width: int
    height: int
    aspect_ratio: float
    channels: int
    dhash: str
    ahash: str
    mean_r: float
    mean_g: float
    mean_b: float
    std_r: float
    std_g: float
    std_b: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)


def extract_image_metadata(file_path: Union[str, Path]) -> ImageMetadata:
    """Extract comprehensive metadata and statistics for an image file.

    Args:
        file_path: Target image file path.

    Returns:
        ImageMetadata dataclass instance.
    """
    path = Path(file_path)
    size_bytes = path.stat().st_size
    sha256_hash = compute_sha256(path)

    with Image.open(path) as img:
        img_format = img.format or path.suffix.lstrip(".").upper()
        mode = img.mode
        width, height = img.size
        aspect = float(width) / float(height) if height > 0 else 0.0
        channels = len(img.getbands())

        dhash_str = compute_dhash(img)
        ahash_str = compute_ahash(img)

        # Color channel statistics (converted to RGB for uniform 3-channel evaluation)
        rgb_img = img.convert("RGB")
        arr = np.asarray(rgb_img, dtype=np.float32)

        mean_vals = np.mean(arr, axis=(0, 1))
        std_vals = np.std(arr, axis=(0, 1))

        mean_r, mean_g, mean_b = float(mean_vals[0]), float(mean_vals[1]), float(mean_vals[2])
        std_r, std_g, std_b = float(std_vals[0]), float(std_vals[1]), float(std_vals[2])

    return ImageMetadata(
        file_path=str(path.resolve()),
        file_name=path.name,
        sha256=sha256_hash,
        size_bytes=size_bytes,
        format=img_format,
        mode=mode,
        width=width,
        height=height,
        aspect_ratio=round(aspect, 4),
        channels=channels,
        dhash=dhash_str,
        ahash=ahash_str,
        mean_r=round(mean_r, 2),
        mean_g=round(mean_g, 2),
        mean_b=round(mean_b, 2),
        std_r=round(std_r, 2),
        std_g=round(std_g, 2),
        std_b=round(std_b, 2),
    )
