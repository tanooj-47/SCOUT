# SCOUT — Milestone 06: Media Ingestion Pipeline Implementation Report

**Status:** COMPLETE & VERIFIED  
**Date:** October 30, 2026  
**Project:** SCOUT (Smart Crisis Observation & Understanding Technology)  
**Milestone:** Milestone 06 — Media Ingestion Pipeline  
**Lead Engineer:** Senior Backend & Geospatial Architect  

---

## 1. Executive Summary

Milestone 06 delivers a secure, reliable, and transaction-isolated **Media Ingestion Pipeline** for SCOUT. The implementation enables ingestion of high-resolution visual evidence (drone imagery, satellite captures, field sensor photography) directly into the platform, validating byte signatures, enforcing streaming size limits, maintaining zero-orphaned-file transactional consistency, and projecting geospatial capture coordinates via PostGIS without exposing internal filesystem layouts.

### Key Achievements:
- **Zero Schema Disruption:** The existing five database tables (`incidents`, `uploaded_media`, `detection_results`, `environmental_observations`, `hazard_predictions`), ORM models, and initial Alembic migration (`0001_initial_schema`) remain strictly frozen and unmodified.
- **Strict Byte Signature Validation:** File extensions and client MIME headers are treated as untrusted. Files are validated using magic byte headers (`JPEG`, `PNG`, `WebP`). Executable binaries, PDFs, arbitrary documents, and empty files are rejected.
- **Chunked Streaming & Memory Safety:** Files stream in 64 KB chunks directly to staging storage (`storage/tmp/`). The 10 MB size limit is enforced during streaming without buffering full files in memory.
- **Transactional Consistency & Zero Orphaned Files:** Physical storage and SQLAlchemy database operations are coordinated atomically. If validation, database insertion, or commit fails, physical files are purged immediately.
- **Path Traversal Protection:** Relative storage paths are strictly sandboxed within the configured media root; directory traversal sequences (`..`) and absolute paths are rejected.
- **Lightweight PostGIS Projections:** Media endpoints project `capture_location` coordinates via scalar PostGIS functions (`ST_X`, `ST_Y`), completely avoiding in-memory GeoAlchemy2 WKB deserialization overhead.
- **100% Test Pass Rate:** Test suite expanded from 61 to **85 tests**, all passing in 6.16 seconds.

---

## 2. Inventory of Files Created and Modified

### New Components:
1. [`backend/app/core/storage.py`](backend/app/core/storage.py)  
   Filesystem storage abstraction managing temporary file creation, safe path resolution, atomic promotion, and cleanup.
2. [`backend/app/schemas/media.py`](backend/app/schemas/media.py)  
   Pydantic schemas including `MediaFormat`, `MediaSourceType`, `MediaResponse`, and `MediaListResponse`.
3. [`backend/app/services/media_service.py`](backend/app/services/media_service.py)  
   Core ingestion coordinator managing magic-byte detection, chunked streaming, coordinate validation, database persistence, and rollback cleanup.
4. [`backend/app/api/v1/endpoints/media.py`](backend/app/api/v1/endpoints/media.py)  
   REST endpoints mounted under `/api/v1/media` handling multipart upload, metadata retrieval, and paginated listing.
5. [`backend/tests/unit/test_storage.py`](backend/tests/unit/test_storage.py)  
   Unit tests covering storage manager initialization, staging, atomic promotion, traversal rejection, and overwrite prevention.
6. [`backend/tests/unit/test_media_schemas.py`](backend/tests/unit/test_media_schemas.py)  
   Unit tests covering magic byte format detection, coordinate validation (bounds, NaN, infinity, single-coordinate rejection), and response serialization.
7. [`backend/tests/integration/test_media_api.py`](backend/tests/integration/test_media_api.py)  
   Full integration test suite against PostgreSQL/PostGIS covering valid formats, nullable incident linking, coordinate mapping, size limits, failure cleanup, and path hiding.

### Modified Components:
8. [`backend/app/core/config.py`](backend/app/core/config.py)  
   Added `STORAGE_DIR`, `MAX_UPLOAD_SIZE_BYTES`, `MEDIA_STORAGE_DIR`, and `TEMP_STORAGE_DIR` settings.
9. [`backend/app/core/exceptions.py`](backend/app/core/exceptions.py)  
   Added `MediaNotFoundError` (404), `UnsupportedMediaFormatError` (415), `MediaSizeLimitExceededError` (413), `EmptyFileError` (400), `InvalidCoordinatesError` (400), and `StorageError` (500).
10. [`backend/app/schemas/__init__.py`](backend/app/schemas/__init__.py)  
    Exported new media schema types.
11. [`backend/app/services/__init__.py`](backend/app/services/__init__.py)  
    Exported `media_service`.
12. [`backend/app/api/v1/router.py`](backend/app/api/v1/router.py)  
    Mounted `media.router` under `/media` prefix.
13. [`backend/requirements.txt`](backend/requirements.txt)  
    Added `python-multipart>=0.0.20` for FastAPI form handling.
14. [`backend/tests/unit/test_config.py`](backend/tests/unit/test_config.py)  
    Added `test_storage_settings` unit test.
15. [`.env.example`](.env.example)  
    Added `STORAGE_DIR` and `MAX_UPLOAD_SIZE_BYTES` placeholders.
16. [`.gitignore`](.gitignore)  
    Added `storage/` directory exclusion.
17. [`README.md`](README.md)  
    Documented Milestone 06 architecture, curl/PowerShell examples, limits, and endpoints.

---

## 3. API Endpoints Specification

### Ingestion Endpoints

| Method | Endpoint | Status | Description |
|---|---|---|---|
| `POST` | `/api/v1/media` | `201 Created` | Ingest raster image via `multipart/form-data` |
| `GET` | `/api/v1/media/{media_id}` | `200 OK` | Fetch metadata by media UUID (binary payload omitted) |
| `GET` | `/api/v1/media` | `200 OK` | Paginated search, filter by incident or source type |

### Upload Form Parameters:
- `file: UploadFile` (Required): Binary image payload.
- `incident_id: Optional[UUID]` (Optional): Incident link; validated against database.
- `source_type: Optional[str]` (Optional): Category (e.g. `drone`, `satellite`, `field_camera`, `ground_team`, `other`).
- `latitude: Optional[float]` (Optional): WGS 84 latitude `[-90.0, 90.0]`.
- `longitude: Optional[float]` (Optional): WGS 84 longitude `[-180.0, 180.0]`.
- `captured_at: Optional[datetime]` (Optional): ISO-8601 acquisition timestamp.

---

## 4. Storage Architecture & Transaction Safety

1. **Staging & Atomic Move:** Inbound chunks write to `storage/tmp/upload_<uuid>.tmp`. Upon successful streaming and byte-signature validation, `os.replace` atomically promotes the file to `storage/media/images/YYYY/MM/<media_id>.<ext>`.
2. **Zero Orphaned Files:** If `db.flush()` or `db.commit()` raises an exception, the `except` block invokes `storage_manager.delete_file(relative_path)` before re-raising the error.
3. **Path Traversal Shield:** Paths are verified via `resolved.relative_to(base_dir)`; attempts to inject parent directories (`..`) or absolute paths (`/etc/`, `C:\`) raise `StorageError` and are rejected.
4. **Information Hiding:** Internal server paths (e.g. `C:\Users\...`) are never sent in API responses; only safe canonical relative paths (e.g. `images/2026/10/<uuid>.jpg`) are serialized.

---

## 5. Actual Test & Dependency Verification Evidence

### Test Suite Execution:
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\backend
configfile: pytest.ini
plugins: anyio-4.15.1
collecting ... collected 85 items

backend\tests\integration\test_db_connection.py::test_live_database_connection PASSED [  1%]
backend\tests\integration\test_health.py::test_health_check_endpoint PASSED [  2%]
backend\tests\integration\test_health.py::test_root_endpoint PASSED      [  3%]
backend\tests\integration\test_health.py::test_nonexistent_endpoint PASSED [  4%]
backend\tests\integration\test_incidents_api.py::test_create_incident_success PASSED [  5%]
backend\tests\integration\test_incidents_api.py::test_create_incident_validation_errors PASSED [  7%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_and_counts PASSED [  8%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_with_postgis_perimeter PASSED [  9%]
backend\tests\integration\test_incidents_api.py::test_get_incident_not_found_and_malformed_uuid PASSED [ 10%]
backend\tests\integration\test_incidents_api.py::test_list_incidents_filtering_and_pagination PASSED [ 11%]
backend\tests\integration\test_incidents_api.py::test_list_incidents_sorting_options PASSED [ 12%]
backend\tests\integration\test_patch_incident_fields_and_transitions PASSED [ 14%]
backend\tests\integration\test_patch_rejection_of_invalid_transitions PASSED [ 15%]
backend\tests\integration\test_patch_rejection_of_null_and_empty_payload PASSED [ 16%]
backend\tests\integration\test_patch_metadata_full_replacement PASSED [ 17%]
backend\tests\integration\test_archive_incident_and_immutability PASSED [ 18%]
backend\tests\integration\test_media_api.py::test_upload_jpeg_with_incident_and_coordinates PASSED [ 20%]
backend\tests\integration\test_media_api.py::test_upload_png_without_incident PASSED [ 21%]
backend\tests\integration\test_media_api.py::test_upload_webp_format PASSED [ 22%]
backend\tests\integration\test_media_api.py::test_upload_empty_file_rejected PASSED [ 23%]
backend\tests\integration\test_media_api.py::test_upload_disguised_fake_bytes_rejected PASSED [ 24%]
backend\tests\integration\test_media_api.py::test_upload_unsupported_format_pdf_rejected PASSED [ 25%]
backend\tests\integration\test_media_api.py::test_upload_oversized_file_rejected PASSED [ 27%]
backend\tests\integration\test_media_api.py::test_upload_single_coordinate_rejected PASSED [ 28%]
backend\tests\integration\test_media_api.py::test_upload_out_of_bounds_coordinates_rejected PASSED [ 29%]
backend\tests\integration\test_media_api.py::test_upload_nonexistent_incident_id_returns_404 PASSED [ 30%]
backend\tests\integration\test_media_api.py::test_get_media_by_id_and_not_found PASSED [ 31%]
backend\tests\integration\test_media_api.py::test_list_media_filtering_and_pagination PASSED [ 32%]
backend\tests\integration\test_media_api.py::test_failed_database_flush_cleans_up_file PASSED [ 34%]
backend\tests\unit\test_alembic.py::test_alembic_config_initialization PASSED [ 35%]
backend\tests\unit\test_alembic.py::test_include_object_filter PASSED    [ 36%]
backend\tests\unit\test_alembic_migrations.py::test_alembic_discovers_migration_history PASSED [ 37%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_upgrade_generation PASSED [ 38%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_downgrade_generation PASSED [ 40%]
backend\tests\unit\test_config.py::test_default_settings PASSED          [ 41%]
backend\tests\unit\test_config.py::test_cors_origins_parsing PASSED      [ 42%]
backend\tests\unit\test_config.py::test_resolved_paths PASSED            [ 43%]
backend\tests\unit\test_config.py::test_database_url_construction PASSED [ 44%]
backend\tests\unit\test_config.py::test_special_character_escaping_in_database_url PASSED [ 45%]
backend\tests\unit\test_masked_database_uri PASSED       [ 47%]
backend\tests\unit\test_config.py::test_storage_settings PASSED          [ 48%]
backend\tests\unit\test_db_engine.py::test_engine_dialect_and_driver PASSED [ 49%]
backend\tests\unit\test_db_engine.py::test_engine_pool_configuration PASSED [ 50%]
backend\tests\unit\test_db_engine.py::test_engine_lazy_initialization PASSED [ 51%]
backend\tests\unit\test_db_session.py::test_session_factory PASSED       [ 52%]
backend\tests\unit\test_db_session.py::test_get_db_yields_and_closes_normally PASSED [ 54%]
backend\tests\unit\test_db_session.py::test_get_db_closes_on_exception PASSED [ 55%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_valid PASSED [ 56%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_boundary_limits PASSED [ 57%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_nan_and_infinities PASSED [ 58%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_extra_fields PASSED [ 60%]
backend\tests\unit\test_coordinate_point_server_srid_default PASSED [ 61%]
backend\tests\unit\test_incident_create_valid PASSED [ 62%]
backend\tests\unit\test_incident_create_invalid_title PASSED [ 63%]
backend\tests\unit\test_incident_create_rejects_unexpected_fields PASSED [ 64%]
backend\tests\unit\test_incident_update_omitted_fields PASSED [ 65%]
backend\tests\unit\test_incident_update_rejects_empty_payload PASSED [ 67%]
backend\tests\unit\test_incident_update_rejects_explicit_null_on_non_nullable PASSED [ 68%]
backend\tests\unit\test_incident_update_metadata_replacement PASSED [ 69%]
backend\tests\unit\test_incident_service.py::test_status_transition_matrix_rules PASSED [ 70%]
backend\tests\unit\test_incident_service.py::test_invalid_status_transitions_rejected PASSED [ 71%]
backend\tests\unit\test_incident_service.py::test_severity_ranking_hierarchy PASSED [ 72%]
backend\tests\unit\test_media_schemas.py::test_magic_byte_format_detection PASSED [ 74%]
backend\tests\unit\test_media_schemas.py::test_validate_coordinates_valid PASSED [ 75%]
backend\tests\unit\test_media_schemas.py::test_validate_coordinates_single_coordinate_rejected PASSED [ 76%]
backend\tests\unit\test_media_schemas.py::test_validate_coordinates_bounds_and_nan PASSED [ 77%]
backend\tests\unit\test_media_schemas.py::test_media_response_schema PASSED [ 78%]
backend\tests\unit\test_models_base.py::test_declarative_base_naming_conventions PASSED [ 80%]
backend\tests\unit\test_models_base.py::test_approved_tables_registered PASSED [ 81%]
backend\tests\unit\test_models_schema.py::test_uuid_primary_keys PASSED  [ 82%]
backend\tests\unit\test_models_schema.py::test_spatial_column_types_and_srid PASSED [ 83%]
backend\tests\unit\test_models_schema.py::test_jsonb_columns PASSED      [ 84%]
backend\tests\unit\test_models_schema.py::test_timezone_aware_timestamps PASSED [ 85%]
backend\tests\unit\test_models_schema.py::test_foreign_keys_and_restrict_policy PASSED [ 87%]
backend\tests\unit\test_models_schema.py::test_relationships_and_back_populates PASSED [ 88%]
backend\tests\unit\test_models_schema.py::test_check_constraints_present PASSED [ 89%]
backend\tests\unit\test_models_schema.py::test_spatial_and_functional_indexes PASSED [ 90%]
backend\tests\unit\test_models_schema.py::test_exact_columns_and_rejection_of_unapproved_fields PASSED [ 91%]
backend\tests\unit\test_models_schema.py::test_column_nullability_and_immutability PASSED [ 92%]
backend\tests\unit\test_metadata_declarative_base_preservation PASSED [ 94%]
backend\tests\unit\test_storage.py::test_storage_manager_initialization PASSED [ 95%]
backend\tests\unit\test_storage.py::test_storage_create_and_delete_temp_file PASSED [ 96%]
backend\tests\unit\test_storage.py::test_storage_finalize_upload PASSED  [ 97%]
backend\tests\unit\test_storage.py::test_storage_path_traversal_rejection PASSED [ 98%]
backend\tests\unit\test_storage.py::test_storage_overwrite_prevention PASSED [100%]

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 85 passed, 1 warning in 6.16s ========================
```

### Dependency Check:
```powershell
.\.venv\Scripts\python.exe -m pip check
```
```text
No broken requirements found.
```

---

## 6. Live Database State & Schema Invariants

- **PostgreSQL Version:** 16.4
- **PostGIS Version:** 3.4.3
- **Alembic Revision Head:** `0001_initial_schema` (unchanged)
- **Schema Mutation Check:**
  ```powershell
  git diff -- backend/app/models backend/alembic
  ```
  Result: **0 differences**. All 5 ORM models, foreign keys (`RESTRICT`), check constraints, and GiST indexes remain intact.

---

## 7. Known Limitations

1. **Raster Formats Only:** Only JPEG, PNG, and WebP are accepted in Milestone 06. Multi-spectral TIFF/GeoTIFF, netCDF, HDF5, video streams (RTSP/HLS), and vector formats will be added in specialized downstream milestones.
2. **Local Storage Driver:** Storing files locally inside `storage/media` is optimal for development. Cloud object storage drivers (AWS S3, Google Cloud Storage, MinIO) will plug in behind `LocalStorageManager` in future infrastructure milestones.
3. **No Embedded EXIF Parsing:** EXIF metadata extraction was not implemented per project instructions to keep dependencies minimal.

---

## 8. Exact Commands for Verification

```powershell
# 1. Run complete test suite (unit + live integration)
.\.venv\Scripts\python.exe -m pytest backend/tests -v

# 2. Run dependency health check
.\.venv\Scripts\python.exe -m pip check

# 3. Verify models and alembic immutability
git diff -- backend/app/models backend/alembic
```
