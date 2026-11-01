"""
ml/data/transforms.py - Aspect-ratio-preserving preprocessing and augmentation transforms.

Preserves full visual context (flames, smoke plumes, horizons) without anisotropic
distortion or aggressive cropping. Symmetrically pads images to standard 224x224 squares
using ImageNet channel mean fill color.
"""

from typing import Tuple
from PIL import Image
import torch
import torchvision.transforms.functional as F
from torchvision import transforms

from ml.config import (
    IMAGE_SIZE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    LETTERBOX_FILL_COLOR,
)


class AspectRatioPreservingLetterbox:
    """
    Resizes an image preserving aspect ratio so the longer edge equals target_size,
    then symmetrically pads with fill_color to produce a square (target_size, target_size).

    Handles landscape, portrait, and square images symmetrically. Bilinear interpolation
    avoids pixel ringing on diffuse smoke boundaries. Symmetrical padding ensures the subject
    remains centered. When target_size - new_dim is odd, the 1-pixel difference is placed
    on the bottom/right padding.
    """

    def __init__(
        self,
        target_size: int = IMAGE_SIZE,
        fill: Tuple[int, int, int] = LETTERBOX_FILL_COLOR,
    ) -> None:
        if target_size <= 0:
            raise ValueError(f"target_size must be positive, got {target_size}")
        self.target_size = target_size
        self.fill = fill

    def __call__(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid image dimensions: ({w}, {h})")

        scale = self.target_size / max(w, h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))

        # Resample preserving aspect ratio
        resized_img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        # Compute symmetric padding
        pad_left = (self.target_size - new_w) // 2
        pad_top = (self.target_size - new_h) // 2
        pad_right = self.target_size - new_w - pad_left
        pad_bottom = self.target_size - new_h - pad_top

        return F.pad(
            resized_img,
            padding=[pad_left, pad_top, pad_right, pad_bottom],
            fill=self.fill,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(target_size={self.target_size}, fill={self.fill})"


def get_train_transforms(
    target_size: int = IMAGE_SIZE,
) -> transforms.Compose:
    """
    Returns the training transformation pipeline:
    1. AspectRatioPreservingLetterbox (preserves complete scene)
    2. RandomHorizontalFlip (p=0.5)
    3. RandomAffine (rotation within ±8 degrees, translation up to 4%, scale 0.96-1.04,
       bilinear interpolation, matching padding fill color)
    4. ColorJitter (brightness 0.15, contrast 0.15, saturation 0.15, hue 0.02)
    5. ToTensor
    6. Normalize (ImageNet mean and std)

    Note:
        ColorJitter applies chromatic perturbations across the entire PIL canvas after
        letterboxing, which also slightly alters the letterbox padding color during training.
        This behavior is intentional and serves as a regularizer preventing the network
        from overfitting to exact border constants.
    """
    return transforms.Compose(
        [
            AspectRatioPreservingLetterbox(
                target_size=target_size, fill=LETTERBOX_FILL_COLOR
            ),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomAffine(
                degrees=(-8, 8),
                translate=(0.04, 0.04),
                scale=(0.96, 1.04),
                interpolation=transforms.InterpolationMode.BILINEAR,
                fill=LETTERBOX_FILL_COLOR,
            ),
            transforms.ColorJitter(
                brightness=0.15,
                contrast=0.15,
                saturation=0.15,
                hue=0.02,
            ),
            transforms.ToTensor(),
            transforms.Normalize(mean=list(IMAGENET_MEAN), std=list(IMAGENET_STD)),
        ]
    )


def get_eval_transforms(
    target_size: int = IMAGE_SIZE,
) -> transforms.Compose:
    """
    Returns the deterministic evaluation pipeline used for validation and test splits:
    1. AspectRatioPreservingLetterbox (preserves complete scene)
    2. ToTensor
    3. Normalize (ImageNet mean and std)

    Guarantees 100% deterministic, reproducible outputs with zero stochastic augmentations.
    """
    return transforms.Compose(
        [
            AspectRatioPreservingLetterbox(
                target_size=target_size, fill=LETTERBOX_FILL_COLOR
            ),
            transforms.ToTensor(),
            transforms.Normalize(mean=list(IMAGENET_MEAN), std=list(IMAGENET_STD)),
        ]
    )
