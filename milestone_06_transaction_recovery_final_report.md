# SCOUT — Milestone 06 Final Storage & Transaction Safety Report
## Disaster Intelligence Evidence Preservation, Cross-Filesystem Promotion & Transaction Recovery

**System:** SCOUT (Smart Crisis Observation & Understanding Technology)  
**Milestone:** 06 — Media Ingestion Pipeline  
**Modules:** Storage Manager ([`storage.py`](backend/app/core/storage.py)), Media Service ([`media_service.py`](backend/app/services/media_service.py)), Exceptions ([`exceptions.py`](backend/app/core/exceptions.py)), Integration Tests ([`test_media_api.py`](backend/tests/integration/test_media_api.py)), Unit Tests ([`test_storage.py`](backend/tests/unit/test_storage.py))  
**Date:** October 30, 2026  
**Environment:** Windows 11 / Python 3.14.7 (`.venv`) / PostgreSQL 16.4 / PostGIS 3.4.3 / Docker  

---

## 1. Executive Summary & Defect Remediation

This final correction addresses the remaining storage atomicity, post-promotion protection, and transaction reconciliation defects identified during independent review of the Milestone 06 Media Ingestion Pipeline.

### Remediated Issues:
1. **Cross-Filesystem Atomic Promotion:**
   - Replaced POSIX `EXDEV` direct-copy fallback with a staged atomic promotion workflow in [`storage.py`](backend/app/core/storage.py):
     - Never copies directly into final destination path.
     - Creates a unique staging file in the target directory using exclusive creation mode (`"xb"`).
     - Stream copies source bytes, calls `flush()` and `os.fsync()`, and closes file handles before promotion.
     - Atomically promotes staging file to destination without overwrite (`os.rename` on Windows, `os.link` + `os.unlink` on POSIX).
     - Guarantees removal of target staging file on copy or promotion failure so partially written files are never left in destination storage.
     - Cleans up source staging file on success, logging structured `CLEANUP_PENDING` if unlinking fails.
2. **Comprehensive Post-Promotion Protection:**
   - In [`media_service.py`](backend/app/services/media_service.py), all operations occurring between physical file promotion and `db.commit()` are wrapped in a single protected `try` block:
     - `WKTElement` construction.
     - `UploadedMedia` ORM model instantiation.
     - `db.add()` and `db.flush()`.
     - Scalar projection query (`select(*MEDIA_SCALAR_PROJECTION)`).
     - Response schema construction and `model_dump()`.
   - On any failure during this pre-commit phase, the session is rolled back, the promoted file is deleted via helper `_cleanup_promoted_file_pre_commit`, and if deletion fails, a `CLEANUP_PENDING` critical log is emitted without masking the original exception.
3. **Transaction Outcome Reconciliation & Evidence Preservation:**
   - Removed the unconstrained `is_aborted: bool` parameter from `reconcile_media_commit_failure`.
   - An immediate query returning no row is **never** treated as definitive proof of transaction rollback.
   - If a fresh database session confirms the record exists and matches metadata (`id`, `storage_path`, `media_format`), returns `HTTP 201 Created` (`CONFIRMED_PERSISTED`).
   - If the transaction outcome is uncertain (absent row or inquiry failure), the physical file is **strictly preserved** to protect disaster evidence, a `CRITICAL` `RECONCILIATION_PENDING` structured log is emitted, and `HTTP 503` (`MediaPersistenceUncertainError`) is returned.
   - Updated documentation and docstrings: SCOUT intentionally does **not** claim "zero orphaned files" under ambiguous commit outcomes; evidence preservation is the non-negotiable operational priority.
4. **Sanitized Image Content Validation:**
   - In `validate_image_content()`, raw Pillow exception strings (`{exc}`) and internal paths are stripped from client-facing errors.
   - Server logs retain detailed diagnostic traces at `WARNING` level.
   - Client receives clean, generic error messages (e.g. `"Corrupted or malformed image content."`).
5. **Observability & Cleanup Reliability:**
   - Checked Boolean return values from all `delete_temp_file` and `delete_file` calls across [`storage.py`](backend/app/core/storage.py) and [`media_service.py`](backend/app/services/media_service.py).
   - Logged explicit `CLEANUP_PENDING` events when deletions fail.

---

## 2. Architecture & Operational Workflow

```
                        +------------------------------------+
                        |       Client Multipart Upload      |
                        +-----------------+------------------+
                                          |
                                          v
                        +-----------------+------------------+
                        | Staging & Pillow Integrity Check   |
                        | (storage/tmp/upload_<uuid>.tmp)    |
                        +-----------------+------------------+
                                          |
                                          v
                        +-----------------+------------------+
                        | Atomic Promotion to Physical Store |
                        | 1. Stage in target dir (.tmp_*)    |
                        | 2. Atomic rename (no-overwrite)    |
                        | 3. Unlink source temp file         |
                        +-----------------+------------------+
                                          |
                                          v
                        +-----------------+------------------+
                        | Post-Promotion Pre-Commit Block    |
                        | 1. Construct WKTElement            |
                        | 2. Instantiate UploadedMedia       |
                        | 3. db.add() & db.flush()           |
                        | 4. Scalar projection query         |
                        | 5. Validate MediaResponse schema   |
                        +-----------------+------------------+
                                          |
                  +-----------------------+-----------------------+
                  | (Pre-Commit Succeeded)|                       | (Pre-Commit Failed: WKT/ORM/Flush/Schema)
                  v                       |                       v
        +---------+---------+             |             +---------+---------+
        |   db.commit()     |             |             |   db.rollback()   |
        +---------+---------+             |             | Delete promoted file
                  |                       |             | (CLEANUP_PENDING if delete fails)
        +---------+---------+             |             | Raise 409 / 500   |
        |                   |             |             +-------------------+
        v                   v             
 (Commit OK)        (Commit Exception)    
        |                   |             
 [HTTP 201 Created]         v             
 [Preserve File]    [reconcile_media_commit_failure()]
                            |
             +--------------+--------------+
             | (Query Fresh Session)       |
             v                             v
   [CONFIRMED_PERSISTED]          [OUTCOME_UNCERTAIN]
   (Record matches metadata)      (Record absent or DB unreachable)
             |                             |
   [Return HTTP 201 Created]      [STRICTLY PRESERVE PHYSICAL FILE]
   [Preserve Physical File]       [CRITICAL: RECONCILIATION_PENDING]
                                  [Raise MediaPersistenceUncertainError 503]
```

---

## 3. Code Modifications Summary

### 1. `backend/app/core/storage.py`
- Implemented `_cross_device_promote(temp_path, dest_path)`:
  - Creates staging file `dest_dir / f".tmp_{dest_path.name}_{uuid.uuid4().hex}"` with mode `"xb"`.
  - Stream copies with `shutil.copyfileobj(f_in, f_out)`, flushes and calls `os.fsync()`.
  - Atomically promotes staging file to `dest_path` without overwrite (`os.rename` on Windows, `os.link` + `os.unlink` on POSIX).
  - Unlinks `temp_path` using `self.delete_temp_file(temp_path)`; logs `CLEANUP_PENDING` if deletion fails.
  - On failure, unlinks `dest_staging` so partially written files are never left behind.
- Implemented `_promote_file_no_overwrite(temp_path, dest_path)`:
  - Attempts same-device atomic move first.
  - Catches `errno.EXDEV` / `winerror == 17` and transparently invokes `_cross_device_promote`.
- Updated `finalize_upload`: checked Boolean returns of `self.delete_temp_file(temp_path)` in all error handlers, logging `CLEANUP_PENDING` on failure.

### 2. `backend/app/services/media_service.py`
- Sanitized `validate_image_content`:
  - Replaced `{exc}` interpolations with generic `"Corrupted or malformed image content."` and `"Image exceeds safety limits (decompression bomb detected)."`.
  - Retained internal logging of actual exception details.
- Added helper `_cleanup_promoted_file_pre_commit(media_id, relative_path, context)`:
  - Calls `storage_manager.delete_file(relative_path)`.
  - If deletion fails, logs structured `CLEANUP_PENDING` at `CRITICAL` level with `media_id`, `storage_path`, and `context`.
- Updated `reconcile_media_commit_failure`:
  - Removed `is_aborted: bool` parameter.
  - Removed all code deleting files on commit exception.
  - Confirmed persisted: returns response.
  - Outcome uncertain: strictly preserves file, logs `CRITICAL` `RECONCILIATION_PENDING`, and raises `MediaPersistenceUncertainError` (HTTP 503).
  - Updated docstring to state evidence preservation on commit uncertainty.
- Updated `ingest_media`:
  - Checked Boolean return of `storage_manager.delete_temp_file(temp_path)` in chunk upload exception handler.
  - Wrapped `WKTElement` construction, `UploadedMedia` instantiation, `db.add`, `db.flush`, scalar query, and schema construction in a single pre-commit `try` block.
  - Handled `IntegrityError`, `SQLAlchemyError`, and generic `Exception` by rolling back and calling `_cleanup_promoted_file_pre_commit`.

### 3. `backend/tests/unit/test_storage.py`
Added unit tests covering all cross-device and cleanup scenarios:
- `test_cross_device_promote_success`: Proves cross-device promotion via staging file, source unlinking, and no leftover staging files.
- `test_cross_device_copy_failure_leaves_no_partial_destination`: Proves copy failure removes destination staging file and never creates target file.
- `test_cross_device_collision_preserves_existing_destination`: Proves collision preserves original destination file and removes destination staging file.
- `test_cross_device_cleanup_failure_logs_critical`: Proves failure to unlink staging file logs `CLEANUP_PENDING` at `CRITICAL` level.
- `test_promote_file_no_overwrite_handles_exdev`: Proves fallback to `_cross_device_promote` when `EXDEV` / `winerror 17` occurs.

### 4. `backend/tests/integration/test_media_api.py`
- Removed test relying on `is_aborted=True`.
- Added `test_post_promotion_wkt_failure_rolls_back_and_cleans_file`: Proves post-promotion WKT construction error rolls back and cleans promoted file.
- Added `test_post_promotion_orm_flush_failure_rolls_back_and_cleans_file`: Proves post-promotion flush error rolls back and cleans promoted file.
- Added `test_pre_commit_cleanup_failure_logs_critical_without_masking_original_error`: Proves that when pre-commit file cleanup fails, `CLEANUP_PENDING` is logged at `CRITICAL` level and original HTTP 500 is returned.
- Added `test_sanitized_image_validation_errors`: Proves corrupted image uploads return HTTP 415 with generic message containing no `{exc}`, internal paths, or tracebacks.

---

## 4. Test Verification Evidence

### Pytest Full Suite Execution Output
```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\backend
configfile: pytest.ini
plugins: anyio-4.15.1
collecting ... collected 113 items

backend\tests\integration\test_db_connection.py::test_live_database_connection PASSED [  0%]
backend\tests\integration\test_health.py::test_health_check_endpoint PASSED [  1%]
backend\tests\integration\test_health.py::test_root_endpoint PASSED      [  2%]
backend\tests\integration\test_health.py::test_nonexistent_endpoint PASSED [  3%]
backend\tests\integration\test_incidents_api.py::test_create_incident_success PASSED [  4%]
backend\tests\integration\test_incidents_api.py::test_create_incident_validation_errors PASSED [  5%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_and_counts PASSED [  6%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_with_postgis_perimeter PASSED [  7%]
backend\tests\integration\test_incidents_api.py::test_get_incident_not_found_and_malformed_uuid PASSED [  7%]
backend\tests\integration\test_incidents_api.py::test_list_incidents_filtering_and_pagination PASSED [  8%]
backend\tests\integration\test_incidents_api.py::test_list_incidents_sorting_options PASSED [  9%]
backend\tests\integration\test_incidents_api.py::test_patch_incident_fields_and_transitions PASSED [ 10%]
backend\tests\integration\test_incidents_api.py::test_patch_rejection_of_invalid_transitions PASSED [ 11%]
backend\tests\integration\test_incidents_api.py::test_patch_rejection_of_null_and_empty_payload PASSED [ 12%]
backend\tests\integration\test_incidents_api.py::test_patch_metadata_full_replacement PASSED [ 13%]
backend\tests\integration\test_incidents_api.py::test_archive_incident_and_immutability PASSED [ 14%]
backend\tests\integration\test_media_api.py::test_upload_jpeg_with_incident_and_coordinates PASSED [ 15%]
backend\tests\integration\test_media_api.py::test_upload_png_without_incident PASSED [ 15%]
backend\tests\integration\test_media_api.py::test_upload_webp_format PASSED [ 16%]
backend\tests\integration\test_media_api.py::test_upload_empty_file_rejected PASSED [ 17%]
backend\tests\integration\test_media_api.py::test_upload_disguised_fake_bytes_rejected PASSED [ 18%]
backend\tests\integration\test_media_api.py::test_upload_unsupported_format_pdf_rejected PASSED [ 19%]
backend\tests\integration\test_media_api.py::test_upload_oversized_file_rejected PASSED [ 20%]
backend\tests\integration\test_media_api.py::test_upload_single_coordinate_rejected PASSED [ 21%]
backend\tests\integration\test_media_api.py::test_upload_out_of_bounds_coordinates_rejected PASSED [ 22%]
backend\tests\integration\test_media_api.py::test_upload_nonexistent_incident_id_returns_404 PASSED [ 23%]
backend\tests\integration\test_media_api.py::test_get_media_by_id_and_not_found PASSED [ 23%]
backend\tests\integration\test_media_api.py::test_list_media_filtering_and_pagination PASSED [ 24%]
backend\tests\integration\test_media_api.py::test_failed_database_flush_cleans_up_file PASSED [ 25%]
backend\tests\integration\test_media_api.py::test_upload_jpeg_with_corrupt_body_rejected PASSED [ 26%]
backend\tests\integration\test_media_api.py::test_upload_truncated_png_rejected PASSED [ 27%]
backend\tests\integration\test_media_api.py::test_upload_invalid_webp_structure_rejected PASSED [ 28%]
backend\tests\integration\test_media_api.py::test_upload_source_type_empty_or_whitespace_rejected PASSED [ 29%]
backend\tests\integration\test_media_api.py::test_upload_source_type_too_long_rejected PASSED [ 30%]
backend\tests\integration\test_media_api.py::test_upload_source_type_custom_extensible_accepted PASSED [ 30%]
backend\tests\integration\test_media_api.py::test_commit_failure_fresh_session_finds_no_record_preserves_file_and_returns_503 PASSED [ 31%]
backend\tests\integration\test_media_api.py::test_commit_uncertainty_db_unreachable_preserves_file_and_returns_503 PASSED [ 32%]
backend\tests\integration\test_media_api.py::test_commit_failure_but_record_persisted_preserves_file PASSED [ 33%]
backend\tests\integration\test_media_api.py::test_post_promotion_wkt_failure_rolls_back_and_cleans_file PASSED [ 34%]
backend\tests\integration\test_media_api.py::test_post_promotion_orm_flush_failure_rolls_back_and_cleans_file PASSED [ 35%]
backend\tests\integration\test_media_api.py::test_pre_commit_cleanup_failure_logs_critical_without_masking_original_error PASSED [ 36%]
backend\tests\integration\test_media_api.py::test_sanitized_image_validation_errors PASSED [ 37%]
backend\tests\integration\test_media_api.py::test_recovery_error_never_accidentally_deletes_image PASSED [ 38%]
backend\tests\integration\test_media_api.py::test_pre_commit_serialization_failure_rolls_back_and_cleans_file PASSED [ 38%]
backend\tests\integration\test_media_api.py::test_client_facing_error_responses_contain_no_internal_details PASSED [ 39%]
backend\tests\integration\test_media_api.py::test_safe_error_messages_contain_no_internal_paths PASSED [ 40%]
backend\tests\unit\test_alembic.py::test_alembic_config_initialization PASSED [ 41%]
backend\tests\unit\test_alembic.py::test_include_object_filter PASSED    [ 42%]
backend\tests\unit\test_alembic_migrations.py::test_alembic_discovers_migration_history PASSED [ 43%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_upgrade_generation PASSED [ 44%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_downgrade_generation PASSED [ 45%]
backend\tests\unit\test_config.py::test_settings_load_from_environment PASSED [ 46%]
backend\tests\unit\test_config.py::test_settings_default_values PASSED   [ 47%]
backend\tests\unit\test_config.py::test_cors_origins_parsing PASSED      [ 47%]
backend\tests\unit\test_config.py::test_sqlalchemy_database_uri_assembly PASSED [ 48%]
backend\tests\unit\test_db_engine.py::test_engine_configuration PASSED   [ 49%]
backend\tests\unit\test_db_engine.py::test_connection_pool_settings PASSED [ 50%]
backend\tests\unit\test_db_session.py::test_session_factory PASSED       [ 51%]
backend\tests\unit\test_db_session.py::test_get_db_yields_and_closes_normally PASSED [ 52%]
backend\tests\unit\test_db_session.py::test_get_db_closes_on_exception PASSED [ 53%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_valid PASSED [ 54%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_boundary_limits PASSED [ 55%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_nan_and_infinities PASSED [ 56%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_extra_fields PASSED [ 57%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_point_server_srid_default PASSED [ 57%]
backend\tests\unit\test_incident_schemas.py::test_incident_create_valid PASSED [ 58%]
backend\tests\unit\test_incident_schemas.py::test_incident_create_invalid_title PASSED [ 59%]
backend\tests\unit\test_incident_schemas.py::test_incident_create_rejects_unexpected_fields PASSED [ 60%]
backend\tests\unit\test_incident_schemas.py::test_incident_update_omitted_fields PASSED [ 61%]
backend\tests\unit\test_incident_schemas.py::test_incident_update_rejects_empty_payload PASSED [ 62%]
backend\tests\unit\test_incident_schemas.py::test_incident_update_rejects_explicit_null_on_non_nullable PASSED [ 63%]
backend\tests\unit\test_incident_schemas.py::test_incident_update_metadata_replacement PASSED [ 64%]
backend\tests\unit\test_incident_service.py::test_status_transition_matrix_rules PASSED [ 65%]
backend\tests\unit\test_incident_service.py::test_invalid_status_transitions_rejected PASSED [ 65%]
backend\tests\unit\test_incident_service.py::test_severity_ranking_hierarchy PASSED [ 66%]
backend\tests\unit\test_media_schemas.py::test_magic_byte_format_detection PASSED [ 67%]
backend\tests\unit\test_media_schemas.py::test_validate_coordinates_valid PASSED [ 68%]
backend\tests\unit\test_media_schemas.py::test_validate_coordinates_single_coordinate_rejected PASSED [ 69%]
backend\tests\unit\test_media_schemas.py::test_validate_coordinates_bounds_and_nan PASSED [ 70%]
backend\tests\unit\test_media_schemas.py::test_media_response_schema PASSED [ 71%]
backend\tests\unit\test_media_schemas.py::test_validate_source_type_valid_and_defaults PASSED [ 72%]
backend\tests\unit\test_media_schemas.py::test_validate_source_type_rejected PASSED [ 73%]
backend\tests\unit\test_media_schemas.py::test_validate_image_content_valid_formats PASSED [ 73%]
backend\tests\unit\test_media_schemas.py::test_validate_image_content_rejected PASSED [ 74%]
backend\tests\unit\test_models_base.py::test_declarative_base_naming_conventions PASSED [ 75%]
backend\tests\unit\test_models_base.py::test_approved_tables_registered PASSED [ 76%]
backend\tests\unit\test_models_schema.py::test_uuid_primary_keys PASSED  [ 77%]
backend\tests\unit\test_models_schema.py::test_spatial_column_types_and_srid PASSED [ 78%]
backend\tests\unit\test_models_schema.py::test_jsonb_columns PASSED      [ 79%]
backend\tests\unit\test_models_schema.py::test_timezone_aware_timestamps PASSED [ 80%]
backend\tests\unit\test_models_schema.py::test_foreign_keys_and_restrict_policy PASSED [ 81%]
backend\tests\unit\test_models_schema.py::test_relationships_and_back_populates PASSED [ 81%]
backend\tests\unit\test_models_schema.py::test_check_constraints_present PASSED [ 82%]
backend\tests\unit\test_models_schema.py::test_spatial_and_functional_indexes PASSED [ 83%]
backend\tests\unit\test_models_schema.py::test_exact_columns_and_rejection_of_unapproved_fields PASSED [ 84%]
backend\tests\unit\test_models_schema.py::test_column_nullability_and_immutability PASSED [ 85%]
backend\tests\unit\test_models_schema.py::test_metadata_declarative_base_preservation PASSED [ 86%]
backend\tests\unit\test_storage.py::test_storage_manager_initialization PASSED [ 87%]
backend\tests\unit\test_storage.py::test_storage_create_and_delete_temp_file PASSED [ 88%]
backend\tests\unit\test_storage.py::test_storage_finalize_upload PASSED  [ 88%]
backend\tests\unit\test_storage.py::test_storage_path_traversal_rejection PASSED [ 89%]
backend\tests\unit\test_storage.py::test_storage_overwrite_prevention PASSED [ 90%]
backend\tests\unit\test_storage.py::test_storage_directory_creation_failure PASSED [ 91%]
backend\tests\unit\test_storage.py::test_storage_promotion_failure PASSED [ 92%]
backend\tests\unit\test_storage.py::test_cross_device_promote_success PASSED [ 93%]
backend\tests\unit\test_storage.py::test_cross_device_copy_failure_leaves_no_partial_destination PASSED [ 94%]
backend\tests\unit\test_storage.py::test_cross_device_collision_preserves_existing_destination PASSED [ 95%]
backend\tests\unit\test_storage.py::test_cross_device_cleanup_failure_logs_critical PASSED [ 96%]
backend\tests\unit\test_storage.py::test_promote_file_no_overwrite_handles_exdev PASSED [ 96%]

======================= 113 passed, 1 warning in 8.19s ========================
```

### Dependency Audit (`pip check`)
```
No broken requirements found.
```

### Live Database & Storage Audit
```
POSTGIS VERSION: POSTGIS="3.4.3 e365945" [EXTENSION] PGSQL="160" GEOS="3.9.0-CAPI-1.16.2" PROJ="7
ALEMBIC REVISION: 0001_initial_schema
APPLICATION TABLES (count 5): ['detection_results', 'environmental_observations', 'hazard_predictions', 'incidents', 'uploaded_media']
UPLOADED MEDIA COUNT: 0
STORAGE FILES: storage/media (0 files), storage/tmp (0 files)
```

### Model & Migration Immutability Verification (SHA-256)
| File | SHA-256 Digest | Status |
|---|---|---|
| [`backend/app/models/base.py`](backend/app/models/base.py) | `60f323a84a4bad8aff9c1d0419e593577b5da1a43bc33efc23dccfb5efe04af9` | UNCHANGED |
| [`backend/app/models/incident.py`](backend/app/models/incident.py) | `192223d7563511e900921f0d342577f7fff20fc8fdf6dd44d1856c096beb8126` | UNCHANGED |
| [`backend/app/models/uploaded_media.py`](backend/app/models/uploaded_media.py) | `7c3546277d74d867d9abe6f6f2a5a5b498d68830f83238afec6f956777a0f464` | UNCHANGED |
| [`backend/app/models/detection_result.py`](backend/app/models/detection_result.py) | `ed663ed9adfc4ecfe2bf6179e6c58a01ff1b3d036e5f4af4d270e6d99077d526` | UNCHANGED |
| [`backend/app/models/environmental_observation.py`](backend/app/models/environmental_observation.py) | `7e222c5e73713cfd172a71485b2f7b0fc0674298ddacdaf44a19ea826e98e0ac` | UNCHANGED |
| [`backend/app/models/hazard_prediction.py`](backend/app/models/hazard_prediction.py) | `01895c24466e50592498575af7a3afeb061070852d9774b224112c99077e1470` | UNCHANGED |
| [`backend/alembic/versions/20261030_0001_initial_schema.py`](backend/alembic/versions/20261030_0001_initial_schema.py) | `492f701fc963ae473bcd8d729c1b93a025039938a49621961bc326a6fac231b2` | UNCHANGED |

---

## 5. Architectural Trade-offs & Limitations

1. **Intentional Preservation of Lingering Files on Commit Uncertainty:**
   - SCOUT explicitly does **not** claim "zero orphaned files" when a database commit fails ambiguously.
   - Preserving files on uncertain commit outcomes is an intentional architectural safety trade-off: in a disaster intelligence platform, visual crisis evidence (drone footage, satellite feeds) is irreplaceable. A temporary lingering file awaiting operator reconciliation is infinitely preferable to permanently destroying crisis data.
2. **Synchronous In-Process Reconciliation:**
   - Reconciliation currently executes within the HTTP request lifecycle. A periodic background reconciliation worker (or outbox pattern) can be integrated in future phases to automate the resolution of files flagged with `RECONCILIATION_PENDING`.
3. **Uncommitted Working Tree:**
   - All changes remain unstaged in the local Git working tree on branch `main`. No commits or pushes have been executed.
