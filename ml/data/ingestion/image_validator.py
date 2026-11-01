"""Two-Pass Image Validation and Sanitization Pipeline.

Enforces binary decode integrity, dimension bounds, aspect ratios, and color mode hygiene.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from PIL import Image, ImageOps


@dataclass
class ValidationResult:
    """Result of two-pass image validation."""
    is_valid: bool
    error_reason: Optional[str] = None
    format: Optional[str] = None
    mode: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    channels: Optional[int] = None


def validate_image_file(
    file_path: Union[str, Path],
    min_dimension: int = 64,
    max_dimension: int = 8192,
    min_aspect_ratio: float = 0.2,
    max_aspect_ratio: float = 5.0,
) -> ValidationResult:
    """Perform robust two-pass image validation on a candidate file.

    Pass 1: Verify image headers and structural integrity via PIL.Image.verify().
    Pass 2: Re-open and fully decode pixels via PIL.Image.load() to detect truncated
            or corrupted byte streams.

    Args:
        file_path: Path to candidate image.
        min_dimension: Minimum acceptable width and height in pixels.
        max_dimension: Maximum acceptable width and height in pixels.
        min_aspect_ratio: Minimum acceptable width/height aspect ratio.
        max_aspect_ratio: Maximum acceptable width/height aspect ratio.

    Returns:
        ValidationResult indicating success or specific failure reason.
    """
    path = Path(file_path)
    if not path.is_file():
        return ValidationResult(is_valid=False, error_reason=f"File not found: {path}")

    # Pass 1: Verify header integrity
    img_format = None
    try:
        with Image.open(path) as img:
            img_format = img.format
            img.verify()
    except Exception as exc:
        return ValidationResult(is_valid=False, error_reason=f"Pass 1 header verification failed: {exc}")

    # Pass 2: Re-open to decode full image buffer (verify() invalidates file handle)
    try:
        with Image.open(path) as img:
            img.load()
            w, h = img.size
            mode = img.mode

            if w < min_dimension or h < min_dimension:
                return ValidationResult(
                    is_valid=False,
                    error_reason=f"Image dimensions ({w}x{h}) smaller than min allowed ({min_dimension})",
                    format=img_format,
                    mode=mode,
                    width=w,
                    height=h,
                )

            if w > max_dimension or h > max_dimension:
                return ValidationResult(
                    is_valid=False,
                    error_reason=f"Image dimensions ({w}x{h}) exceed max allowed ({max_dimension})",
                    format=img_format,
                    mode=mode,
                    width=w,
                    height=h,
                )

            aspect = float(w) / float(h)
            if aspect < min_aspect_ratio or aspect > max_aspect_ratio:
                return ValidationResult(
                    is_valid=False,
                    error_reason=f"Aspect ratio {aspect:.2f} outside acceptable range [{min_aspect_ratio}, {max_aspect_ratio}]",
                    format=img_format,
                    mode=mode,
                    width=w,
                    height=h,
                )

            # Determine channel count
            channels = len(img.getbands())

            return ValidationResult(
                is_valid=True,
                error_reason=None,
                format=img_format,
                mode=mode,
                width=w,
                height=h,
                channels=channels,
            )

    except Exception as exc:
        return ValidationResult(
            is_valid=False,
            error_reason=f"Pass 2 pixel decode failed: {exc}",
            format=img_format,
        )


def sanitize_and_save_image(
    source_path: Union[str, Path],
    target_path: Union[str, Path],
    target_format: Optional[str] = None,
) -> Path:
    """Open, normalize color mode to RGB, and save image to target destination.

    Safely converts RGBA, Palette (P), Grayscale (L), and CMYK images to standard 3-channel RGB.

    Args:
        source_path: Path to source image.
        target_path: Destination path.
        target_format: Output image container format (e.g. 'JPEG', 'PNG', 'TIFF'). If None, inferred.

    Returns:
        Path to saved sanitized image.
    """
    src = Path(source_path)
    dst = Path(target_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as img:
        # Normalize EXIF orientation if present
        img = ImageOps.exif_transpose(img)

        # Color mode normalization
        if img.mode == "RGB":
            rgb_img = img
        elif img.mode == "RGBA":
            # Composite onto white background
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            rgb_img = background
        elif img.mode in ("L", "P", "1"):
            rgb_img = img.convert("RGB")
        elif img.mode == "CMYK":
            rgb_img = img.convert("RGB")
        else:
            rgb_img = img.convert("RGB")

        # Save with quality settings
        save_kwargs = {}
        out_fmt = (target_format or dst.suffix.lstrip(".").upper())
        if out_fmt in ("JPG", "JPEG"):
            save_kwargs["quality"] = 95
            save_kwargs["format"] = "JPEG"
        elif out_fmt == "PNG":
            save_kwargs["format"] = "PNG"
            save_kwargs["optimize"] = True
        elif out_fmt in ("TIF", "TIFF"):
            save_kwargs["format"] = "TIFF"
            save_kwargs["compression"] = "tiff_lzw"

        rgb_img.save(dst, **save_kwargs)

    return dst
