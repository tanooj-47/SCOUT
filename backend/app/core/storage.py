import errno
import logging
import os
from pathlib import Path
import shutil
from typing import BinaryIO, Optional, Tuple
import uuid

from app.core.config import settings
from app.core.exceptions import StorageError

logger = logging.getLogger(__name__)

# Operating system platform name (allows targeted testing of POSIX paths without mutating os.name)
OS_NAME = os.name


class LocalStorageManager:
    """
    Manages physical storage of media assets on the local filesystem.
    Enforces atomic no-overwrite uploads, directory segregation,
    guaranteed temporary file cleanup, and strict path traversal prevention.
    All internal OS paths and filesystem errors are isolated to server logs.
    """

    def __init__(self, base_dir: Optional[Path] = None, temp_dir: Optional[Path] = None):
        self.base_dir = (base_dir or settings.MEDIA_STORAGE_DIR).resolve()
        self.temp_dir = (temp_dir or settings.TEMP_STORAGE_DIR).resolve()

    def _ensure_dir(self, directory: Path) -> None:
        """Ensures that a directory exists safely without leaking paths in client exceptions."""
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.exception("Failed to create storage directory '%s': %s", directory, exc)
            raise StorageError("Failed to initialize storage directory.") from exc

    def resolve_safe_path(self, relative_path: str) -> Path:
        """
        Resolves a relative storage path against base_dir.
        Guarantees that the resolved path is strictly contained within base_dir.
        """
        clean_rel = Path(relative_path)
        if clean_rel.is_absolute() or clean_rel.as_posix().startswith("/") or clean_rel.drive:
            logger.warning("Rejected attempt to use absolute path '%s'", relative_path)
            raise StorageError("Absolute storage paths are forbidden.")

        resolved = (self.base_dir / clean_rel).resolve()
        try:
            resolved.relative_to(self.base_dir)
        except ValueError:
            logger.warning("Path traversal attempt detected with relative path '%s'", relative_path)
            raise StorageError("Path traversal violation detected.")

        return resolved

    def create_temp_file(self) -> Tuple[Path, BinaryIO]:
        """
        Creates a temporary staging file using exclusive creation mode (O_CREAT | O_EXCL).
        Guarantees no truncation or collision of existing staging files.
        """
        self._ensure_dir(self.temp_dir)
        max_attempts = 10
        for _ in range(max_attempts):
            temp_name = f"upload_{uuid.uuid4().hex}.tmp"
            temp_path = self.temp_dir / temp_name
            try:
                # Mode "xb" opens exclusively, failing with FileExistsError if existing
                handle = open(temp_path, "xb")
                return temp_path, handle
            except FileExistsError:
                continue
            except OSError as exc:
                logger.exception("Failed to create temporary staging file at '%s': %s", temp_path, exc)
                raise StorageError("Failed to initialize temporary staging storage.") from exc

        raise StorageError("Failed to allocate a unique temporary staging file.")

    def _cross_device_promote(self, temp_path: Path, dest_path: Path) -> None:
        """
        Cross-filesystem atomic promotion:
        1. Never copies directly into final destination.
        2. Creates a unique staging file in the target directory using exclusive creation.
        3. Copies content from temp_path into target staging file.
        4. Flushes, syncs, and closes staging file.
        5. Atomically promotes target staging file to dest_path without overwriting.
        6. Unlinks staging file (on POSIX if link-based) and source temp_path.
        7. On pre-promotion failure, cleans up destination staging file only if this operation created it.
        """
        dest_dir = dest_path.parent
        dest_staging = dest_dir / f".tmp_{dest_path.name}_{uuid.uuid4().hex}"

        # 1. Create unique staging file in target directory exclusively and stream copy.
        # Track exclusive creation ownership so pre-existing files are never deleted on collision.
        staging_created = False
        try:
            with open(dest_staging, "xb") as f_out:
                staging_created = True
                with open(temp_path, "rb") as f_in:
                    shutil.copyfileobj(f_in, f_out)
                    f_out.flush()
                    try:
                        os.fsync(f_out.fileno())
                    except OSError:
                        pass
        except Exception as copy_err:
            if staging_created and dest_staging.exists():
                try:
                    dest_staging.unlink()
                except OSError as clean_err:
                    logger.critical(
                        "CLEANUP_PENDING: Failed to clean up destination staging file after copy failure: %s (error: %s)",
                        dest_staging.name,
                        clean_err,
                    )
            logger.exception("Cross-device copy failed from '%s' to '%s': %s", temp_path.name, dest_staging.name, copy_err)
            raise

        # 2. Promote destination staging file to dest_path atomically (same filesystem)
        promoted_to_dest = False
        try:
            if OS_NAME == "nt":
                os.rename(dest_staging, dest_path)
                promoted_to_dest = True
            else:
                try:
                    os.link(dest_staging, dest_path)
                    promoted_to_dest = True
                except OSError as exc:
                    if exc.errno == errno.EEXIST:
                        raise FileExistsError("File already exists at destination") from exc
                    raise

                # Hard link succeeded: staging-file cleanup is best-effort and must not fail promotion
                try:
                    dest_staging.unlink()
                except OSError as clean_err:
                    logger.critical(
                        "CLEANUP_PENDING: Failed to unlink destination staging file %s after link promotion: %s",
                        dest_staging.name,
                        clean_err,
                    )
        except Exception:
            if not promoted_to_dest and staging_created and dest_staging.exists():
                try:
                    dest_staging.unlink()
                except OSError as clean_err:
                    logger.critical(
                        "CLEANUP_PENDING: Failed to clean up destination staging file after promotion failure: %s (error: %s)",
                        dest_staging.name,
                        clean_err,
                    )
            raise

        # 3. Clean up source temp file (best-effort)
        if not self.delete_temp_file(temp_path):
            logger.critical(
                "CLEANUP_PENDING: Failed to delete source temp staging file after cross-device promotion: %s",
                temp_path.name,
            )

    def _promote_file_no_overwrite(self, temp_path: Path, dest_path: Path) -> None:
        """
        Promotes temp_path to dest_path atomically without overwriting an existing file.
        Explicitly handles both same-filesystem atomic moves and cross-filesystem staging.
        """
        if OS_NAME == "nt":
            try:
                os.rename(temp_path, dest_path)
                return
            except FileExistsError:
                raise
            except OSError as exc:
                if exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == 17:
                    self._cross_device_promote(temp_path, dest_path)
                    return
                raise
        else:
            try:
                os.link(temp_path, dest_path)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    raise FileExistsError("File already exists at destination") from exc
                if exc.errno == errno.EXDEV:
                    self._cross_device_promote(temp_path, dest_path)
                    return
                raise

            # Destination link succeeded: promotion has crossed the success boundary.
            # Source cleanup is best-effort; failure to unlink must not fail promotion.
            if not self.delete_temp_file(temp_path):
                logger.critical(
                    "CLEANUP_PENDING: Failed to delete source temp file %s after link promotion to %s",
                    temp_path.name,
                    dest_path.name,
                )
            return

    def finalize_upload(self, temp_path: Path, relative_dest_path: str) -> Path:
        """
        Atomically promotes a staged temporary file to its final destination with a
        strict no-overwrite guarantee.
        Always guarantees cleanup of temp_path if an error occurs.
        """
        dest_path: Optional[Path] = None
        try:
            dest_path = self.resolve_safe_path(relative_dest_path)
            self._ensure_dir(dest_path.parent)

            # Atomic non-overwriting promotion (with cross-device support):
            self._promote_file_no_overwrite(temp_path, dest_path)

            logger.debug("Finalized upload: moved '%s' -> '%s'", temp_path.name, dest_path.name)
            return dest_path

        except FileExistsError as exc:
            if not self.delete_temp_file(temp_path):
                logger.critical("CLEANUP_PENDING: Failed to delete temp staging file after collision: %s", temp_path.name)
            logger.warning("Collision: refusing to overwrite existing file at '%s': %s", dest_path or relative_dest_path, exc)
            raise StorageError("A file already exists at the target destination.") from exc
        except StorageError:
            if not self.delete_temp_file(temp_path):
                logger.critical("CLEANUP_PENDING: Failed to delete temp staging file after StorageError: %s", temp_path.name)
            raise
        except OSError as exc:
            if not self.delete_temp_file(temp_path):
                logger.critical("CLEANUP_PENDING: Failed to delete temp staging file after OSError: %s", temp_path.name)
            logger.exception("Failed to promote file to '%s': %s", dest_path or relative_dest_path, exc)
            raise StorageError("Failed to store media file on server.") from exc
        except Exception as exc:
            if not self.delete_temp_file(temp_path):
                logger.critical("CLEANUP_PENDING: Failed to delete temp staging file after unexpected error: %s", temp_path.name)
            logger.exception("Unexpected error promoting file to '%s': %s", dest_path or relative_dest_path, exc)
            raise StorageError("Failed to store media file on server.") from exc

    def delete_temp_file(self, temp_path: Path) -> bool:
        """
        Safely cleans up a temporary staging file.
        Returns True if deleted or already absent, False on deletion error.
        """
        try:
            if temp_path.exists():
                temp_path.unlink()
                logger.debug("Cleaned up temporary staging file: %s", temp_path)
            return True
        except OSError as exc:
            logger.error("Failed to delete temporary staging file '%s': %s", temp_path, exc)
            return False

    def delete_file(self, relative_path: str) -> bool:
        """
        Deletes a finalized physical media file by its relative path.
        Returns True if deleted, False if file did not exist or deletion failed.
        """
        try:
            target_path = self.resolve_safe_path(relative_path)
            if target_path.is_file():
                target_path.unlink()
                logger.info("Deleted physical media file: %s", target_path)
                return True
            return False
        except StorageError:
            logger.error("Failed to delete media file due to invalid relative path: %s", relative_path)
            return False
        except OSError as exc:
            logger.error("Failed to delete physical media file at relative path '%s': %s", relative_path, exc)
            return False

    def file_exists(self, relative_path: str) -> bool:
        """Checks whether a file exists at the given relative path."""
        try:
            target_path = self.resolve_safe_path(relative_path)
            return target_path.is_file()
        except StorageError:
            return False

    def get_file_size(self, relative_path: str) -> int:
        """Returns the size in bytes of the finalized file."""
        target_path = self.resolve_safe_path(relative_path)
        if not target_path.is_file():
            raise StorageError("File does not exist at requested storage path.")
        return target_path.stat().st_size


# Default singleton instance
storage_manager = LocalStorageManager()
