"""
backend/app/geospatial/acquisition/downloader.py
Resumable, fault-tolerant dataset download engine with integrity verification,
atomic file placement, and disk-space preflight validation.
"""

from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Callable, Optional, Tuple
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when a dataset download fails permanently."""
    pass


class InsufficientDiskSpaceError(DownloadError):
    """Raised when destination drive lacks required disk space."""
    pass


class ChecksumMismatchError(DownloadError):
    """Raised when downloaded file SHA-256 or MD5 does not match expected value."""
    pass


class DownloadResult(BaseModel):
    status: str  # "completed", "skipped_existing", "dry_run", "failed"
    file_path: Optional[Path] = None
    file_size_bytes: int = 0
    sha256: Optional[str] = None
    md5: Optional[str] = None
    duration_seconds: float = 0.0
    download_url: str
    error_message: Optional[str] = None


def check_available_disk_space(
    target_path: Path,
    required_bytes: int,
    safety_multiplier: float = 2.5,
) -> Tuple[bool, int, int]:
    """
    Checks if target partition has enough free space.
    Returns: (is_sufficient, available_bytes, required_safe_bytes)
    """
    check_dir = target_path if target_path.is_dir() else target_path.parent
    check_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(check_dir))
    safe_required = int(required_bytes * safety_multiplier)
    is_sufficient = usage.free >= safe_required
    return is_sufficient, usage.free, safe_required


def compute_file_checksums(file_path: Path, chunk_size: int = 1024 * 1024) -> Tuple[str, str, int]:
    """
    Computes SHA-256, MD5, and exact file size in bytes using chunked streaming.
    Returns: (sha256_hex, md5_hex, total_bytes)
    """
    sha256_hash = hashlib.sha256()
    md5_hash = hashlib.md5()
    total_bytes = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256_hash.update(chunk)
            md5_hash.update(chunk)
            total_bytes += len(chunk)

    return sha256_hash.hexdigest(), md5_hash.hexdigest(), total_bytes


class ResumableDownloader:
    """
    Production-grade downloader for large geospatial assets.
    Features:
    - HTTP Range request resumption.
    - Retry loop with exponential backoff.
    - Atomic placement via .part temporary files.
    - Pre-flight storage checks.
    - SHA-256 and MD5 hash validation.
    """

    def __init__(
        self,
        timeout_seconds: float = 120.0,
        max_retries: int = 5,
        backoff_factor: float = 1.0,
        chunk_size: int = 1024 * 1024,  # 1 MB buffer
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.chunk_size = chunk_size

    def download(
        self,
        url: str,
        destination: Path,
        expected_size: Optional[int] = None,
        expected_sha256: Optional[str] = None,
        expected_md5: Optional[str] = None,
        dry_run: bool = False,
        headers: Optional[dict] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> DownloadResult:
        """
        Executes or simulates dataset download.
        """
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        part_path = destination.with_suffix(destination.suffix + ".part")

        # 1. Preflight disk check
        est_size = expected_size or (100 * 1024 * 1024)  # 100MB fallback estimate
        is_ok, free_bytes, safe_req = check_available_disk_space(destination.parent, est_size)
        if not is_ok:
            msg = (
                f"Insufficient disk space in {destination.parent}. "
                f"Available: {free_bytes / (1024**3):.2f} GB, "
                f"Required with safety buffer: {safe_req / (1024**3):.2f} GB."
            )
            logger.error(msg)
            if not dry_run:
                raise InsufficientDiskSpaceError(msg)

        # 2. Dry run simulation
        if dry_run:
            logger.info(f"[DRY-RUN] Would download '{url}' -> '{destination}'. Expected size: {est_size} bytes.")
            return DownloadResult(
                status="dry_run",
                file_path=destination,
                file_size_bytes=est_size,
                download_url=url,
            )

        # 3. Check existing completed file
        if destination.exists() and destination.stat().st_size > 0:
            if expected_size is None or destination.stat().st_size == expected_size:
                logger.info(f"Target file '{destination}' already exists with matching size. Computing hashes...")
                sha256_val, md5_val, sz = compute_file_checksums(destination)
                if expected_sha256 and sha256_val.lower() != expected_sha256.lower():
                    logger.warning("Existing file SHA-256 mismatch. Re-downloading...")
                elif expected_md5 and md5_val.lower() != expected_md5.lower():
                    logger.warning("Existing file MD5 mismatch. Re-downloading...")
                else:
                    return DownloadResult(
                        status="skipped_existing",
                        file_path=destination,
                        file_size_bytes=sz,
                        sha256=sha256_val,
                        md5=md5_val,
                        download_url=url,
                    )

        start_time = time.time()
        req_headers = dict(headers or {})

        # 4. Resumption calculation
        initial_bytes = 0
        if part_path.exists():
            initial_bytes = part_path.stat().st_size
            if initial_bytes > 0:
                req_headers["Range"] = f"bytes={initial_bytes}-"
                logger.info(f"Resuming download from byte offset {initial_bytes}...")

        attempt = 0
        last_error: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                    with client.stream("GET", url, headers=req_headers) as resp:
                        # Validate status
                        if resp.status_code not in (200, 206):
                            resp.read()  # read error body
                            content_preview = resp.text[:200]
                            raise DownloadError(
                                f"HTTP download failed with status {resp.status_code}: {content_preview}"
                            )

                        content_type = resp.headers.get("content-type", "").lower()
                        if "text/html" in content_type and not url.endswith((".html", ".htm")):
                            raise DownloadError(
                                f"Server returned HTML page instead of binary dataset (Content-Type: {content_type})"
                            )

                        # Check if resumption was accepted
                        mode = "ab" if (resp.status_code == 206 and initial_bytes > 0) else "wb"
                        bytes_written = initial_bytes if mode == "ab" else 0

                        total_expected = None
                        cl = resp.headers.get("content-length")
                        if cl:
                            total_expected = int(cl) + (initial_bytes if mode == "ab" else 0)

                        with open(part_path, mode) as f:
                            for chunk in resp.iter_bytes(chunk_size=self.chunk_size):
                                if chunk:
                                    f.write(chunk)
                                    bytes_written += len(chunk)
                                    if progress_callback:
                                        progress_callback(bytes_written, total_expected)

                        # Stream finished successfully
                        break

            except (httpx.RequestError, httpx.TimeoutException, DownloadError) as exc:
                last_error = exc
                logger.warning(
                    f"Download attempt {attempt}/{self.max_retries} failed for {url}: {exc}. "
                    f"Retrying in {self.backoff_factor * (2 ** (attempt - 1)):.1f}s..."
                )
                if attempt >= self.max_retries:
                    raise DownloadError(f"Failed to download {url} after {self.max_retries} attempts: {last_error}")
                time.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                # Update resumption header for retry
                if part_path.exists():
                    initial_bytes = part_path.stat().st_size
                    req_headers["Range"] = f"bytes={initial_bytes}-"

        # 5. Atomic rename to destination
        if not part_path.exists():
            raise DownloadError(f"Download completed but temporary file {part_path} not found.")

        os.replace(part_path, destination)
        duration = time.time() - start_time

        # 6. Verify checksums
        sha256_val, md5_val, final_size = compute_file_checksums(destination)

        if expected_size is not None and final_size != expected_size:
            destination.unlink(missing_ok=True)
            raise DownloadError(
                f"File size mismatch: downloaded {final_size} bytes, expected {expected_size} bytes."
            )

        if expected_sha256 and sha256_val.lower() != expected_sha256.lower():
            destination.unlink(missing_ok=True)
            raise ChecksumMismatchError(
                f"SHA-256 hash mismatch for {destination.name}: got {sha256_val}, expected {expected_sha256}"
            )

        if expected_md5 and md5_val.lower() != expected_md5.lower():
            destination.unlink(missing_ok=True)
            raise ChecksumMismatchError(
                f"MD5 hash mismatch for {destination.name}: got {md5_val}, expected {expected_md5}"
            )

        logger.info(
            f"Successfully downloaded '{destination.name}' ({final_size / (1024**2):.2f} MB) in {duration:.2f}s."
        )

        return DownloadResult(
            status="completed",
            file_path=destination,
            file_size_bytes=final_size,
            sha256=sha256_val,
            md5=md5_val,
            duration_seconds=duration,
            download_url=url,
        )
