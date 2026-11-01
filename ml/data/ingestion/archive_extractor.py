"""Safe Archive Extraction with Path Traversal / Zip Slip Protection.

Guarantees that archive members cannot write outside the intended destination directory.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path
from typing import List, Optional

from ml.data.ingestion.hasher import compute_sha256


class SafeArchiveExtractor:
    """Safely extracts zip and tar archives preventing Zip Slip / path traversal attacks."""

    @staticmethod
    def _is_safe_path(base_dir: Path, target_path: Path) -> bool:
        """Verify that target_path resolves strictly inside base_dir."""
        try:
            base_resolved = base_dir.resolve()
            target_resolved = target_path.resolve()
            # On Python 3.9+, is_relative_to is standard
            return target_resolved.is_relative_to(base_resolved)
        except (ValueError, AttributeError):
            # Fallback using commonpath
            return os.path.commonpath([str(base_resolved), str(target_resolved)]) == str(base_resolved)

    @classmethod
    def extract_zip(
        cls,
        archive_path: Path | str,
        destination_dir: Path | str,
        expected_sha256: Optional[str] = None,
    ) -> List[Path]:
        """Extract a zip archive safely.

        Args:
            archive_path: Path to .zip file.
            destination_dir: Extraction destination.
            expected_sha256: Optional SHA-256 checksum to verify before extraction.

        Returns:
            List of successfully extracted file paths.

        Raises:
            ValueError: If checksum fails or a member attempts path traversal.
        """
        archive_path = Path(archive_path)
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)

        if expected_sha256:
            actual_sha = compute_sha256(archive_path)
            if actual_sha.lower() != expected_sha256.lower():
                raise ValueError(
                    f"Checksum mismatch for {archive_path.name}: "
                    f"expected {expected_sha256}, got {actual_sha}"
                )

        extracted_files: List[Path] = []
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.infolist():
                # Ignore directory entries
                if member.is_dir():
                    continue

                target_path = destination_dir / member.filename
                if not cls._is_safe_path(destination_dir, target_path):
                    raise ValueError(
                        f"Zip Slip security violation: '{member.filename}' "
                        f"attempts to escape destination '{destination_dir}'"
                    )

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as source, target_path.open("wb") as target:
                    target.write(source.read())
                extracted_files.append(target_path)

        return extracted_files

    @classmethod
    def extract_tar(
        cls,
        archive_path: Path | str,
        destination_dir: Path | str,
        expected_sha256: Optional[str] = None,
    ) -> List[Path]:
        """Extract a tar archive safely."""
        archive_path = Path(archive_path)
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)

        if expected_sha256:
            actual_sha = compute_sha256(archive_path)
            if actual_sha.lower() != expected_sha256.lower():
                raise ValueError(
                    f"Checksum mismatch for {archive_path.name}: "
                    f"expected {expected_sha256}, got {actual_sha}"
                )

        extracted_files: List[Path] = []
        with tarfile.open(archive_path, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue

                target_path = destination_dir / member.name
                if not cls._is_safe_path(destination_dir, target_path):
                    raise ValueError(
                        f"Tar traversal security violation: '{member.name}' "
                        f"attempts to escape destination '{destination_dir}'"
                    )

                target_path.parent.mkdir(parents=True, exist_ok=True)
                fileobj = tf.extractfile(member)
                if fileobj is not None:
                    with target_path.open("wb") as target:
                        target.write(fileobj.read())
                    extracted_files.append(target_path)

        return extracted_files


def extract_archive_safely(
    archive_path: Path | str,
    destination_dir: Path | str,
    expected_sha256: Optional[str] = None,
) -> List[Path]:
    """Convenience function to extract either zip or tar archives safely."""
    path = Path(archive_path)
    if path.suffix.lower() == ".zip":
        return SafeArchiveExtractor.extract_zip(path, destination_dir, expected_sha256)
    elif path.suffix.lower() in [".tar", ".gz", ".tgz", ".bz2"]:
        return SafeArchiveExtractor.extract_tar(path, destination_dir, expected_sha256)
    else:
        raise ValueError(f"Unsupported archive format: {path.name}")
