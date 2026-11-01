"""Cryptographic and Perceptual Hashing Utilities for Image Datasets.

Implements exact bitwise hashing (SHA-256) and perceptual hashing (dHash, aHash)
for near-duplicate detection and image integrity verification.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union
import numpy as np
from PIL import Image


def compute_sha256(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest for a file.

    Args:
        file_path: Path to the target file.
        chunk_size: Stream buffer size in bytes.

    Returns:
        64-character lowercase hexadecimal SHA-256 string.
    """
    path = Path(file_path)
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def compute_dhash(image_input: Union[str, Path, Image.Image], hash_size: int = 8) -> str:
    """Compute Difference Hash (dHash) for an image.

    Algorithm:
    1. Convert image to grayscale ('L').
    2. Resize to (hash_size + 1, hash_size), e.g. 9x8 for an 8x8 (64-bit) hash.
    3. Compute horizontal gradient: compare adjacent pixels (pixel[x+1] > pixel[x]).
    4. Pack resulting boolean array into hexadecimal representation.

    Args:
        image_input: File path or PIL Image instance.
        hash_size: Grid dimension; default 8 produces a 64-bit hash.

    Returns:
        Hexadecimal hash string (16 characters for hash_size=8).
    """
    if isinstance(image_input, (str, Path)):
        img = Image.open(image_input)
    else:
        img = image_input

    # Convert to grayscale and resize to (width=hash_size + 1, height=hash_size)
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.int32)

    # Difference between consecutive columns
    diff = arr[:, 1:] > arr[:, :-1]

    # Pack bits into uint8 and then hex
    bits = diff.flatten()
    # Pad to multiple of 8 if necessary
    pad_len = (8 - (len(bits) % 8)) % 8
    if pad_len > 0:
        bits = np.pad(bits, (0, pad_len), "constant")

    packed = np.packbits(bits)
    return packed.tobytes().hex()


def compute_ahash(image_input: Union[str, Path, Image.Image], hash_size: int = 8) -> str:
    """Compute Average Hash (aHash) for an image.

    Algorithm:
    1. Convert image to grayscale ('L').
    2. Resize to (hash_size, hash_size), e.g. 8x8.
    3. Compare each pixel against the mean intensity of the 64 pixels.
    4. Pack boolean array into hexadecimal representation.

    Args:
        image_input: File path or PIL Image instance.
        hash_size: Grid dimension; default 8 produces a 64-bit hash.

    Returns:
        Hexadecimal hash string (16 characters for hash_size=8).
    """
    if isinstance(image_input, (str, Path)):
        img = Image.open(image_input)
    else:
        img = image_input

    gray = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    arr = np.asarray(gray, dtype=np.float32)
    mean_val = float(np.mean(arr))
    bits = (arr > mean_val).flatten()

    pad_len = (8 - (len(bits) % 8)) % 8
    if pad_len > 0:
        bits = np.pad(bits, (0, pad_len), "constant")

    packed = np.packbits(bits)
    return packed.tobytes().hex()


def hash_hex_to_int(hex_str: str) -> int:
    """Convert hexadecimal hash string to integer for fast bitwise XOR."""
    return int(hex_str, 16)


def hamming_distance(hash1: Union[str, int], hash2: Union[str, int]) -> int:
    """Compute the bitwise Hamming distance between two perceptual hashes.

    Args:
        hash1: Hexadecimal string or integer representation of hash.
        hash2: Hexadecimal string or integer representation of hash.

    Returns:
        Number of differing bits (0 means identical perceptual hash).
    """
    val1 = int(hash1, 16) if isinstance(hash1, str) else hash1
    val2 = int(hash2, 16) if isinstance(hash2, str) else hash2
    xor_val = val1 ^ val2
    return bin(xor_val).count("1")
