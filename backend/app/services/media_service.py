import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple
from uuid import UUID
import uuid

from fastapi import UploadFile
from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_X, ST_Y
from PIL import Image, ImageFile, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    DatabaseConflictError,
    EmptyFileError,
    IncidentNotFoundError,
    InternalServiceError,
    InvalidCoordinatesError,
    InvalidSourceTypeError,
    MediaNotFoundError,
    MediaPersistenceUncertainError,
    MediaSizeLimitExceededError,
    StorageError,
    UnsupportedMediaFormatError,
)
from app.core.storage import storage_manager
from app.db.session import SessionLocal
from app.models.incident import Incident
from app.models.uploaded_media import UploadedMedia
from app.schemas.incident import CoordinatePoint
from app.schemas.media import MediaListResponse, MediaResponse

logger = logging.getLogger(__name__)

# Canonical Scalar Projection for Media Queries (Excludes raw PostGIS geometry)
MEDIA_SCALAR_PROJECTION = [
    UploadedMedia.id,
    UploadedMedia.incident_id,
    UploadedMedia.storage_path,
    UploadedMedia.media_format,
    UploadedMedia.source_type,
    UploadedMedia.file_size_bytes,
    ST_X(UploadedMedia.capture_location).label("longitude"),
    ST_Y(UploadedMedia.capture_location).label("latitude"),
    UploadedMedia.captured_at,
    UploadedMedia.created_at,
]

# Ensure Pillow rejects truncated images instead of silently loading partial frames
ImageFile.LOAD_TRUNCATED_IMAGES = False

# Maximum permitted raster image dimensions and total pixels
MAX_IMAGE_DIMENSION = 16384
MAX_IMAGE_PIXELS = 100_000_000  # 100 Megapixels


def detect_image_format_magic(header: bytes) -> Optional[str]:
    """
    Fast preliminary byte signature validation (magic numbers).
    Quickly discards arbitrary non-image binaries before chunk streaming.
    """
    if len(header) < 12:
        return None
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


# Backward-compatible alias
detect_image_format = detect_image_format_magic


def validate_image_content(file_path: Path) -> Tuple[str, int, int]:
    """
    Deep structural and integrity validation of raster images using Pillow.
    Ensures truncated, corrupted, or malicious images (decompression bombs)
    are rejected without loading entire pixel bitmaps into memory.

    Returns:
        Tuple[str, int, int]: (canonical_format, width, height)
    """
    # Enforce safe decompression bomb limits
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    # Pass 1: Structural verification (reads chunks, markers, checksums, headers)
    try:
        with Image.open(file_path) as img:
            img.verify()
    except Image.DecompressionBombError as exc:
        logger.warning("Pillow detected decompression bomb in %s: %s", file_path, exc)
        raise UnsupportedMediaFormatError("Image exceeds safety limits (decompression bomb detected).") from exc
    except (UnidentifiedImageError, SyntaxError, OSError) as exc:
        logger.warning("Pillow rejected corrupted/invalid image structure in %s: %s", file_path, exc)
        raise UnsupportedMediaFormatError("Corrupted or malformed image content.") from exc
    except Exception as exc:
        logger.warning("Unexpected error during image structural verification of %s: %s", file_path, exc)
        raise UnsupportedMediaFormatError("Corrupted or malformed image content.") from exc

    # Pass 2: Inspect metadata, format, and dimensions
    try:
        with Image.open(file_path) as img:
            raw_format = (img.format or "").lower()
            if raw_format == "jpeg":
                canonical_format = "jpeg"
            elif raw_format == "png":
                canonical_format = "png"
            elif raw_format == "webp":
                canonical_format = "webp"
            else:
                raise UnsupportedMediaFormatError("Unsupported image format. Only JPEG, PNG, and WebP are allowed.")

            width, height = img.size
            if width <= 0 or height <= 0:
                raise UnsupportedMediaFormatError("Image has invalid non-positive dimensions.")

            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise UnsupportedMediaFormatError(
                    f"Image dimensions exceed maximum permitted dimension of {MAX_IMAGE_DIMENSION}px."
                )

            if (width * height) > MAX_IMAGE_PIXELS:
                raise UnsupportedMediaFormatError(
                    f"Image pixel count exceeds maximum permitted limit of {MAX_IMAGE_PIXELS} pixels."
                )

            return canonical_format, width, height
    except UnsupportedMediaFormatError:
        raise
    except Image.DecompressionBombError as exc:
        logger.warning("Pillow detected decompression bomb during dimension check of %s: %s", file_path, exc)
        raise UnsupportedMediaFormatError("Image exceeds safety limits (decompression bomb detected).") from exc
    except Exception as exc:
        logger.warning("Failed to inspect image dimensions of %s: %s", file_path, exc)
        raise UnsupportedMediaFormatError("Corrupted or malformed image content.") from exc


def validate_coordinates(latitude: Optional[float], longitude: Optional[float]) -> None:
    """
    Validates optional coordinate pairs.
    Both must be present together or both must be None.
    Rejects NaN, +/-Infinity, and out-of-range coordinates.
    """
    if latitude is None and longitude is None:
        return

    if latitude is None or longitude is None:
        raise InvalidCoordinatesError("Both latitude and longitude must be provided together, or both omitted.")

    if math.isnan(latitude) or math.isinf(latitude) or math.isnan(longitude) or math.isinf(longitude):
        raise InvalidCoordinatesError("Coordinates must be valid finite numbers (NaN and Infinities rejected).")

    if latitude < -90.0 or latitude > 90.0:
        raise InvalidCoordinatesError("Latitude must be within the range [-90.0, 90.0] degrees.")

    if longitude < -180.0 or longitude > 180.0:
        raise InvalidCoordinatesError("Longitude must be within the range [-180.0, 180.0] degrees.")


def validate_source_type(source_type: Optional[str]) -> str:
    """
    Validates acquisition source type.
    - If None, defaults to 'other'.
    - Rejects empty or whitespace-only strings.
    - Rejects strings exceeding the database column limit (32 characters) without silent truncation.
    """
    if source_type is None:
        return "other"

    cleaned = source_type.strip()
    if not cleaned:
        raise InvalidSourceTypeError("Acquisition source_type cannot be empty or whitespace-only.")

    if len(cleaned) > 32:
        raise InvalidSourceTypeError(
            f"Acquisition source_type exceeds maximum permitted length of 32 characters (received {len(cleaned)})."
        )

    return cleaned


def _row_to_media_response(row: Any) -> MediaResponse:
    """Converts a projected scalar row to a MediaResponse schema."""
    m = row._mapping
    location = None
    if m["latitude"] is not None and m["longitude"] is not None:
        location = CoordinatePoint(
            latitude=m["latitude"],
            longitude=m["longitude"],
            srid=4326,
        )

    return MediaResponse(
        id=m["id"],
        incident_id=m["incident_id"],
        storage_path=m["storage_path"],
        media_format=m["media_format"],
        source_type=m["source_type"],
        file_size_bytes=m["file_size_bytes"],
        capture_location=location,
        captured_at=m["captured_at"],
        created_at=m["created_at"],
    )


def _cleanup_promoted_file_pre_commit(media_id: UUID, relative_path: str, context: str) -> None:
    """
    Cleans up the promoted file when a pre-commit operation fails.
    If deletion fails, logs a critical CLEANUP_PENDING event containing
    the media ID and relative path so operator reconciliation can occur.
    Never masks the original exception.
    """
    deleted = storage_manager.delete_file(relative_path)
    if not deleted:
        logger.critical(
            "CLEANUP_PENDING: Failed to delete promoted media file during pre-commit rollback: "
            "media_id=%s, storage_path=%s, context=%s",
            media_id,
            relative_path,
            context,
        )


def reconcile_media_commit_failure(
    media_id: UUID,
    relative_path: str,
    response_obj: MediaResponse,
    commit_exc: Exception,
) -> MediaResponse:
    """
    Reconciles the state of a media ingestion transaction following an exception on db.commit().

    Distinguishes:
    - CONFIRMED_PERSISTED: Fresh session confirms record exists and matches promoted asset.
      Preserves the physical file and returns the validated response.
    - OUTCOME_UNCERTAIN: Fresh session finds no record or inquiry itself fails. An immediate
      absence of a record is NEVER treated as definitive proof of rollback. The physical file
      is strictly PRESERVED to prevent loss of critical crisis evidence, a CRITICAL structured
      event is logged, and a safe HTTP 503 MediaPersistenceUncertainError is returned.
      Note: Files with uncertain commit outcomes are preserved pending operator reconciliation;
      we do NOT claim zero orphaned files in the presence of ambiguous commit failures.
    """
    classification = "OUTCOME_UNCERTAIN"
    file_preserved = True

    try:
        with SessionLocal() as fresh_db:
            persisted = fresh_db.get(UploadedMedia, media_id)
            if persisted is not None:
                # Establish consistency between persisted entity and prepared response
                if (
                    persisted.id == media_id
                    and persisted.storage_path == relative_path
                    and persisted.media_format == response_obj.media_format
                ):
                    classification = "CONFIRMED_PERSISTED"
    except Exception as fresh_err:
        logger.warning(
            "Fresh database inquiry failed during commit reconciliation: media_id=%s, storage_path=%s, error=%s",
            media_id,
            relative_path,
            fresh_err,
        )

    if classification == "CONFIRMED_PERSISTED":
        logger.info(
            "Media commit reconciliation confirmed record persistence: "
            "media_id=%s, storage_path=%s, classification=%s, file_preserved=%s",
            media_id,
            relative_path,
            classification,
            file_preserved,
        )
        return response_obj

    # In disaster intelligence, preserving visual evidence is the top operational priority.
    # An absent record in an immediate query does not prove permanent rollback;
    # the physical file is PRESERVED and marked for operator reconciliation.
    logger.critical(
        "RECONCILIATION_PENDING: Media transaction outcome uncertain after commit exception. "
        "media_id=%s, storage_path=%s, classification=%s, file_preserved=%s",
        media_id,
        relative_path,
        classification,
        file_preserved,
    )

    raise MediaPersistenceUncertainError(media_id=media_id)


def ingest_media(
    db: Session,
    upload_file: UploadFile,
    incident_id: Optional[UUID] = None,
    source_type: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    captured_at: Optional[datetime] = None,
) -> MediaResponse:
    """
    Safely ingests an uploaded raster image.
    Enforces format validation, chunked size limits, deep Pillow integrity validation,
    atomic no-overwrite file promotion, pre-commit response validation, and
    robust database transaction reconciliation with evidence preservation on commit uncertainty.
    """
    # 1. Validate associated incident if provided
    if incident_id is not None:
        incident = db.get(Incident, incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)

    # 2. Validate coordinates
    validate_coordinates(latitude, longitude)

    # 3. Validate source_type strictly (rejects empty/whitespace, rejects > 32 chars, defaults to 'other')
    effective_source_type = validate_source_type(source_type)

    # 4. Stream upload into a temporary file in chunks
    temp_path, temp_file = storage_manager.create_temp_file()
    total_bytes = 0
    chunk_size = 64 * 1024  # 64 KB chunks
    max_bytes = settings.MAX_UPLOAD_SIZE_BYTES
    header_bytes = bytearray()
    initial_sniff_format: Optional[str] = None

    try:
        while True:
            chunk = upload_file.file.read(chunk_size)
            if not chunk:
                break

            if total_bytes == 0:
                header_bytes.extend(chunk[:12])
                initial_sniff_format = detect_image_format_magic(bytes(header_bytes))
                if initial_sniff_format is None:
                    raise UnsupportedMediaFormatError("Initial file bytes do not match any supported image format signature.")

            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise MediaSizeLimitExceededError(max_bytes=max_bytes, received_bytes=total_bytes)

            temp_file.write(chunk)

        temp_file.flush()
        temp_file.close()

        if total_bytes == 0:
            raise EmptyFileError()

        if initial_sniff_format is None:
            raise UnsupportedMediaFormatError("File contents do not match any supported image format signature.")

        # 5. Deep Pillow structural & dimension verification
        canonical_format, width, height = validate_image_content(temp_path)

    except Exception:
        try:
            temp_file.close()
        except Exception:
            pass
        if not storage_manager.delete_temp_file(temp_path):
            logger.critical("CLEANUP_PENDING: Failed to delete temp staging file after upload error: %s", temp_path.name)
        raise

    # 6. Determine canonical relative destination path (storage/media/YYYY/MM/<uuid>.<ext>)
    media_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    ext_map = {"jpeg": "jpg", "png": "png", "webp": "webp"}
    ext = ext_map.get(canonical_format, "bin")
    relative_path = f"{now.year}/{now.month:02d}/{media_id}.{ext}"

    # 7. Atomically promote physical file without overwriting
    storage_manager.finalize_upload(temp_path, relative_dest_path=relative_path)

    # 8. Post-promotion pre-commit phase:
    # All operations after physical file promotion and before db.commit()
    # (WKTElement construction, ORM model instantiation, db.add, db.flush,
    # scalar projection query, and response serialization) are protected in a single try block.
    try:
        point_wkt: Optional[WKTElement] = None
        if latitude is not None and longitude is not None:
            point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)

        media_record = UploadedMedia(
            id=media_id,
            incident_id=incident_id,
            storage_path=relative_path,
            media_format=canonical_format,
            source_type=effective_source_type,
            file_size_bytes=total_bytes,
            capture_location=point_wkt,
            captured_at=captured_at,
            created_at=now,
        )

        db.add(media_record)
        db.flush()

        stmt = select(*MEDIA_SCALAR_PROJECTION).where(UploadedMedia.id == media_id)
        row = db.execute(stmt).one()
        response_obj = _row_to_media_response(row)
        _ = response_obj.model_dump()
    except IntegrityError as exc:
        try:
            db.rollback()
        except Exception as rb_exc:
            logger.error("Error during session rollback after IntegrityError: %s", rb_exc)
        _cleanup_promoted_file_pre_commit(media_id, relative_path, context="IntegrityError")
        logger.warning("Database integrity constraint violated during media ingestion: %s", exc)
        raise DatabaseConflictError("Media record violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        try:
            db.rollback()
        except Exception as rb_exc:
            logger.error("Error during session rollback after SQLAlchemyError: %s", rb_exc)
        _cleanup_promoted_file_pre_commit(media_id, relative_path, context="SQLAlchemyError")
        logger.exception("Database error during media ingestion flush: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while persisting media metadata.") from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception as rb_exc:
            logger.error("Error during session rollback after pre-commit failure: %s", rb_exc)
        _cleanup_promoted_file_pre_commit(media_id, relative_path, context=type(exc).__name__)
        logger.exception("Unexpected error during media ingestion pre-commit: %s", exc)
        raise InternalServiceError("Failed to prepare media metadata record.") from exc

    # Commit phase: execute commit with reconciliation safety
    try:
        db.commit()
        return response_obj
    except Exception as commit_exc:
        logger.warning(
            "db.commit() encountered an exception during media ingestion: media_id=%s, storage_path=%s, error=%s",
            media_id,
            relative_path,
            commit_exc,
        )
        try:
            db.rollback()
        except Exception as rb_exc:
            logger.error(
                "Error during session rollback after commit failure: media_id=%s, error=%s",
                media_id,
                rb_exc,
            )

        return reconcile_media_commit_failure(
            media_id=media_id,
            relative_path=relative_path,
            response_obj=response_obj,
            commit_exc=commit_exc,
        )


def get_media_by_id(db: Session, media_id: UUID) -> MediaResponse:
    """
    Retrieves metadata for a specific media record.
    Never exposes internal filesystem paths or returns binary payloads.
    """
    stmt = select(*MEDIA_SCALAR_PROJECTION).where(UploadedMedia.id == media_id)
    row = db.execute(stmt).first()
    if row is None:
        raise MediaNotFoundError(media_id)
    return _row_to_media_response(row)


def list_media(
    db: Session,
    incident_id: Optional[UUID] = None,
    source_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    order_direction: str = "desc",
) -> MediaListResponse:
    """
    Retrieves a paginated list of media metadata matching optional filters.
    Enforces deterministic secondary ordering on media ID.
    Never loads media binaries into memory.
    """
    filters = []
    if incident_id is not None:
        filters.append(UploadedMedia.incident_id == incident_id)
    if source_type is not None:
        filters.append(UploadedMedia.source_type == source_type)

    count_stmt = select(func.count(UploadedMedia.id)).where(*filters)
    total = db.scalar(count_stmt) or 0

    sort_col = (
        UploadedMedia.created_at.desc()
        if order_direction.lower() == "desc"
        else UploadedMedia.created_at.asc()
    )

    data_stmt = (
        select(*MEDIA_SCALAR_PROJECTION)
        .where(*filters)
        .order_by(sort_col, UploadedMedia.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(data_stmt).all()

    items = [_row_to_media_response(r) for r in rows]
    has_next = (offset + limit) < total
    has_prev = offset > 0

    return MediaListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
        has_prev=has_prev,
    )
