import os
from pathlib import Path
import pytest

from app.core.exceptions import StorageError
from app.core.storage import LocalStorageManager


def test_storage_manager_initialization(tmp_path: Path):
    """Verify that storage directories are initialized correctly."""
    base_dir = tmp_path / "media"
    temp_dir = tmp_path / "tmp"
    mgr = LocalStorageManager(base_dir=base_dir, temp_dir=temp_dir)

    assert mgr.base_dir == base_dir.resolve()
    assert mgr.temp_dir == temp_dir.resolve()


def test_storage_create_and_delete_temp_file(tmp_path: Path):
    """Verify temporary file creation, writing, and cleanup."""
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")

    temp_path, handle = mgr.create_temp_file()
    assert temp_path.exists()
    assert temp_path.parent == mgr.temp_dir

    handle.write(b"sample temp content")
    handle.close()

    assert temp_path.stat().st_size == len(b"sample temp content")

    mgr.delete_temp_file(temp_path)
    assert not temp_path.exists()


def test_storage_finalize_upload(tmp_path: Path):
    """Verify atomic promotion of temporary file to destination."""
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"image bytes payload")
    handle.close()

    rel_dest = "2026/10/test_image.jpg"
    final_path = mgr.finalize_upload(temp_path, rel_dest)

    assert not temp_path.exists()
    assert final_path.exists()
    assert mgr.file_exists(rel_dest)
    assert mgr.get_file_size(rel_dest) == len(b"image bytes payload")

    # Cleanup
    deleted = mgr.delete_file(rel_dest)
    assert deleted is True
    assert not mgr.file_exists(rel_dest)


def test_storage_path_traversal_rejection(tmp_path: Path):
    """Verify that directory traversal attempts are strictly forbidden."""
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")

    # Traversal using ..
    with pytest.raises(StorageError) as exc1:
        mgr.resolve_safe_path("../../outside.jpg")
    assert "traversal" in str(exc1.value).lower()

    # Absolute path
    with pytest.raises(StorageError) as exc2:
        mgr.resolve_safe_path("/root/secret.png")
    assert "absolute" in str(exc2.value).lower()


def test_storage_overwrite_prevention(tmp_path: Path):
    """Verify that existing files cannot be overwritten and existing content is preserved."""
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")

    # First upload
    t1, h1 = mgr.create_temp_file()
    h1.write(b"version 1")
    h1.close()
    mgr.finalize_upload(t1, "duplicate.jpg")

    # Second upload to same destination
    t2, h2 = mgr.create_temp_file()
    h2.write(b"version 2")
    h2.close()

    with pytest.raises(StorageError) as exc:
        mgr.finalize_upload(t2, "duplicate.jpg")
    assert "already exists" in str(exc.value).lower()
    # Staging file should be cleaned up automatically
    assert not t2.exists()
    # Original file must be preserved untouched
    assert (mgr.base_dir / "duplicate.jpg").read_bytes() == b"version 1"


def test_storage_directory_creation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify safe cleanup and non-leaking error message when directory creation fails."""
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"payload")
    handle.close()

    def mock_mkdir(*args, **kwargs):
        raise OSError("Read-only filesystem error")

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    with pytest.raises(StorageError) as exc_info:
        mgr.finalize_upload(temp_path, "sub/dir/image.jpg")

    # Staging file must be cleaned up
    assert not temp_path.exists()
    # Error message must be generic and leak NO absolute path
    error_msg = str(exc_info.value)
    assert "failed to initialize storage directory" in error_msg.lower()
    assert str(tmp_path) not in error_msg


def test_storage_promotion_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify safe cleanup and non-leaking error message when atomic promotion fails."""
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"payload")
    handle.close()

    def mock_promote(*args, **kwargs):
        raise OSError("I/O device error")

    monkeypatch.setattr("app.core.storage.os.rename", mock_promote)

    with pytest.raises(StorageError) as exc_info:
        mgr.finalize_upload(temp_path, "2026/10/image.jpg")

    # Staging file must be cleaned up
    assert not temp_path.exists()
    # Error message must be generic and leak NO absolute path
    error_msg = str(exc_info.value)
    assert "failed to store media file on server" in error_msg.lower()
    assert str(tmp_path) not in error_msg


def test_cross_device_promote_success(tmp_path: Path):
    """
    Verify that cross-device promotion (_cross_device_promote) moves file via staging file,
    preserves exact content, removes source temp file, and completes successfully.
    """
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"cross-device payload bytes")
    handle.close()

    dest_path = dest_dir / "cross_device_image.jpg"

    mgr._cross_device_promote(temp_path, dest_path)

    assert dest_path.exists()
    assert dest_path.read_bytes() == b"cross-device payload bytes"
    assert not temp_path.exists()
    staging_files = list(dest_dir.glob(".tmp_*"))
    assert len(staging_files) == 0


def test_cross_device_copy_failure_leaves_no_partial_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Verify that a copy failure during cross-device promotion cleans up any destination
    staging file, never creates the final destination file, and leaves no partial files.
    """
    import shutil
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"interrupted payload")
    handle.close()

    dest_path = dest_dir / "failed_copy.jpg"

    def mock_copyfileobj(f_in, f_out):
        f_out.write(b"partial bytes")
        raise IOError("Disk write error during stream copy")

    monkeypatch.setattr(shutil, "copyfileobj", mock_copyfileobj)

    with pytest.raises(IOError) as exc_info:
        mgr._cross_device_promote(temp_path, dest_path)

    assert "Disk write error" in str(exc_info.value)
    assert not dest_path.exists()
    staging_files = list(dest_dir.glob(".tmp_*"))
    assert len(staging_files) == 0


def test_cross_device_collision_preserves_existing_destination(tmp_path: Path):
    """
    Verify that cross-device promotion fails if destination already exists,
    cleans up destination staging file, and leaves existing file content untouched.
    """
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / "existing.jpg"
    dest_path.write_bytes(b"original preserved content")

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"attempted overwriter content")
    handle.close()

    with pytest.raises(FileExistsError):
        mgr._cross_device_promote(temp_path, dest_path)

    assert dest_path.read_bytes() == b"original preserved content"
    staging_files = list(dest_dir.glob(".tmp_*"))
    assert len(staging_files) == 0


def test_cross_device_cleanup_failure_logs_critical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """
    Verify that if unlinking the destination staging file fails during error cleanup,
    a CRITICAL CLEANUP_PENDING log is emitted.
    """
    import logging
    import shutil
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"payload")
    handle.close()

    dest_path = dest_dir / "cleanup_fail.jpg"

    def mock_copyfileobj(f_in, f_out):
        raise IOError("Disk error during copy")

    orig_unlink = Path.unlink

    def mock_unlink(self_path, *args, **kwargs):
        if ".tmp_" in self_path.name:
            raise OSError("Permission denied when unlinking staging file")
        return orig_unlink(self_path, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfileobj", mock_copyfileobj)
    monkeypatch.setattr(Path, "unlink", mock_unlink)

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(IOError):
            mgr._cross_device_promote(temp_path, dest_path)

    assert any("CLEANUP_PENDING" in record.message for record in caplog.records)


def test_promote_file_no_overwrite_handles_exdev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Verify that _promote_file_no_overwrite handles EXDEV / WinError 17 by falling back
    to _cross_device_promote.
    """
    import errno
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"simulated exdev payload")
    handle.close()

    dest_path = dest_dir / "exdev_promoted.jpg"

    called_cross_device = False
    orig_cross_device = mgr._cross_device_promote
    orig_rename = os.rename

    def mock_cross_device(src, dst):
        nonlocal called_cross_device
        called_cross_device = True
        return orig_cross_device(src, dst)

    def mock_rename(src, dst):
        if src == temp_path:
            err = OSError("Simulated cross-device link error")
            err.errno = errno.EXDEV
            err.winerror = 17
            raise err
        return orig_rename(src, dst)

    monkeypatch.setattr("app.core.storage.os.rename", mock_rename)
    monkeypatch.setattr(mgr, "_cross_device_promote", mock_cross_device)

    mgr._promote_file_no_overwrite(temp_path, dest_path)

    assert called_cross_device is True
    assert dest_path.exists()
    assert dest_path.read_bytes() == b"simulated exdev payload"


def test_cross_device_staging_collision_preserves_preexisting_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Regression Test 1: Verify staging-file ownership.
    If destination staging file pre-exists (name collision), exclusive creation fails with
    FileExistsError, and the pre-existing staging file and its contents remain untouched.
    The current operation must NEVER delete a file it did not create.
    """
    import uuid
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / "target_media.jpg"

    # Pre-create a staging file with fixed UUID
    fixed_uuid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr("app.core.storage.uuid.uuid4", lambda: fixed_uuid)

    expected_staging_path = dest_dir / f".tmp_{dest_path.name}_{fixed_uuid.hex}"
    expected_staging_path.write_bytes(b"PRE-EXISTING UNRELATED STAGING DATA")

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"new upload payload")
    handle.close()

    # Attempt cross-device promotion
    with pytest.raises(FileExistsError):
        mgr._cross_device_promote(temp_path, dest_path)

    # The pre-existing staging file must STILL exist and remain untouched
    assert expected_staging_path.exists()
    assert expected_staging_path.read_bytes() == b"PRE-EXISTING UNRELATED STAGING DATA"

    # The source temp file must still exist
    assert temp_path.exists()
    assert temp_path.read_bytes() == b"new upload payload"

    # Destination was never created
    assert not dest_path.exists()


def test_posix_same_device_promotion_unlink_failure_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """
    Regression Test 2: POSIX same-device promotion.
    os.link() successfully creates the final destination, but source temp unlinking fails.
    The promotion MUST be treated as successful because the destination was created.
    Final destination exists with complete bytes, and CLEANUP_PENDING is logged at CRITICAL.
    """
    import errno
    import logging
    import shutil

    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"posix payload bytes")
    handle.close()

    dest_path = dest_dir / "posix_promoted.jpg"

    # Monkeypatch to POSIX mode
    monkeypatch.setattr("app.core.storage.OS_NAME", "posix")

    # Mock working os.link via file copy
    def mock_link(src, dst):
        if Path(dst).exists():
            err = OSError("File exists")
            err.errno = errno.EEXIST
            raise err
        shutil.copy2(src, dst)

    monkeypatch.setattr("app.core.storage.os.link", mock_link)

    # Mock delete_temp_file to fail (simulating source os.unlink failure)
    monkeypatch.setattr(mgr, "delete_temp_file", lambda p: False)

    with caplog.at_level(logging.CRITICAL):
        # Must NOT raise an exception
        mgr._promote_file_no_overwrite(temp_path, dest_path)

    # Destination must exist and have complete bytes
    assert dest_path.exists()
    assert dest_path.read_bytes() == b"posix payload bytes"

    # CLEANUP_PENDING must be logged at CRITICAL level
    crit_logs = [r for r in caplog.records if r.levelno >= logging.CRITICAL and "CLEANUP_PENDING" in r.message]
    assert len(crit_logs) >= 1
    assert temp_path.name in crit_logs[0].message


def test_posix_cross_device_promotion_staging_unlink_failure_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """
    Regression Test 3: POSIX cross-device promotion.
    Target staging file is created and populated; os.link() creates final destination,
    but unlinking the staging file fails.
    The promotion MUST be treated as successful.
    Final destination exists with complete bytes, and CLEANUP_PENDING is logged at CRITICAL.
    """
    import errno
    import logging
    import shutil

    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"posix cross-device payload")
    handle.close()

    dest_path = dest_dir / "cross_promoted.jpg"

    # Monkeypatch to POSIX mode
    monkeypatch.setattr("app.core.storage.OS_NAME", "posix")

    # Mock working os.link via file copy
    def mock_link(src, dst):
        if Path(dst).exists():
            err = OSError("File exists")
            err.errno = errno.EEXIST
            raise err
        shutil.copy2(src, dst)

    orig_unlink = Path.unlink

    def mock_unlink(self_path, *args, **kwargs):
        if ".tmp_" in self_path.name:
            raise OSError("Simulated permission denied on staging file unlink")
        return orig_unlink(self_path, *args, **kwargs)

    monkeypatch.setattr("app.core.storage.os.link", mock_link)
    monkeypatch.setattr(Path, "unlink", mock_unlink)

    with caplog.at_level(logging.CRITICAL):
        # Must NOT raise an exception
        mgr._cross_device_promote(temp_path, dest_path)

    # Destination must exist and have complete bytes
    assert dest_path.exists()
    assert dest_path.read_bytes() == b"posix cross-device payload"

    # CLEANUP_PENDING must be logged for the staging file
    crit_logs = [r for r in caplog.records if r.levelno >= logging.CRITICAL and "CLEANUP_PENDING" in r.message]
    assert len(crit_logs) >= 1
    assert ".tmp_" in crit_logs[0].message


def test_posix_same_device_collision_preserves_destination_and_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Regression Test 4: POSIX same-device collision handling.
    When destination already exists, os.link() raises EEXIST -> FileExistsError.
    Pre-existing destination and source temp file are preserved untouched.
    """
    import errno
    mgr = LocalStorageManager(base_dir=tmp_path / "media", temp_dir=tmp_path / "tmp")
    dest_dir = mgr.base_dir / "2026/10"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / "colliding_dest.jpg"
    dest_path.write_bytes(b"PRE-EXISTING FINAL DESTINATION BYTES")

    temp_path, handle = mgr.create_temp_file()
    handle.write(b"new upload attempting to overwrite")
    handle.close()

    # Monkeypatch to POSIX mode
    monkeypatch.setattr("app.core.storage.OS_NAME", "posix")

    def mock_link(src, dst):
        if Path(dst).exists():
            err = OSError("File exists")
            err.errno = errno.EEXIST
            raise err

    monkeypatch.setattr("app.core.storage.os.link", mock_link)

    with pytest.raises(FileExistsError):
        mgr._promote_file_no_overwrite(temp_path, dest_path)

    # Pre-existing destination MUST be completely preserved
    assert dest_path.read_bytes() == b"PRE-EXISTING FINAL DESTINATION BYTES"
    # Source temp file MUST be preserved
    assert temp_path.read_bytes() == b"new upload attempting to overwrite"
