# SCOUT — Milestone 05 Final API Contract Correction Report

**Status:** COMPLETE & VERIFIED  
**Date:** October 30, 2026  
**Project:** SCOUT (Smart Crisis Observation & Understanding Technology)  
**Milestone:** Milestone 05 — Incident Management API  
**Review Type:** Final Contract Alignments & PostGIS Perimeter Verification  

---

## 1. Executive Summary

In response to the independent architectural review, two targeted corrections were performed on the Milestone 05 codebase:

1. **Summary Count Field Pluralization:** The summary counts response schema and service layer were brought into exact alignment with the approved contract:
   - `media_count`
   - `observations_count` (plural)
   - `predictions_count` (plural)
   The singular variants (`observation_count` and `prediction_count`) were completely retired. No `detections_count` was introduced, as `detection_results` foreign keys point to `uploaded_media` (`media_id`), not `incidents`.
2. **Real PostGIS Perimeter Integration Test:** A new integration test (`test_get_incident_detail_with_postgis_perimeter`) was implemented in `backend/tests/integration/test_incidents_api.py`. The test inserts a real `MULTIPOLYGON` geometry (SRID 4326) into PostgreSQL, updates `perimeter_updated_at`, verifies GeoJSON MultiPolygon deserialization and coordinate fidelity via `GET /api/v1/incidents/{incident_id}`, and verifies that the perimeter polygon is strictly excluded from list endpoint queries (`GET /api/v1/incidents`).

All 61 tests passed across unit and live database integration suites in 5.13s. Zero models or migrations were modified.

---

## 2. Files Modified

| File | Change Description |
|---|---|
| [`backend/app/schemas/incident.py`](backend/app/schemas/incident.py) | Renamed `observation_count` -> `observations_count` and `prediction_count` -> `predictions_count` in `IncidentSummaryCounts`. |
| [`backend/app/services/incident_service.py`](backend/app/services/incident_service.py) | Updated `counts = IncidentSummaryCounts(...)` instantiation to use `observations_count` and `predictions_count`. |
| [`backend/tests/integration/test_incidents_api.py`](backend/tests/integration/test_incidents_api.py) | Updated existing detail count assertions; added new integration test `test_get_incident_detail_with_postgis_perimeter`. |
| [`README.md`](README.md) | Synchronized API response documentation example to reflect `observations_count` and `predictions_count`. |

---

## 3. Exact Response-Field Names: Before vs. After

### In `backend/app/schemas/incident.py` (`IncidentSummaryCounts`):

**Before:**
```python
class IncidentSummaryCounts(BaseModel):
    media_count: int = Field(default=0, ge=0, description="Count of associated media records")
    observation_count: int = Field(default=0, ge=0, description="Count of environmental observations")
    prediction_count: int = Field(default=0, ge=0, description="Count of hazard predictions")
```

**After:**
```python
class IncidentSummaryCounts(BaseModel):
    media_count: int = Field(default=0, ge=0, description="Count of associated media records")
    observations_count: int = Field(default=0, ge=0, description="Count of environmental observations")
    predictions_count: int = Field(default=0, ge=0, description="Count of hazard predictions")
```

### In `backend/app/services/incident_service.py` (`get_incident_detail`):

**Before:**
```python
    counts = IncidentSummaryCounts(
        media_count=media_count,
        observation_count=obs_count,
        prediction_count=pred_count,
    )
```

**After:**
```python
    counts = IncidentSummaryCounts(
        media_count=media_count,
        observations_count=obs_count,
        predictions_count=pred_count,
    )
```

### Serialized API JSON Response:

```json
{
  "summary_counts": {
    "media_count": 0,
    "observations_count": 0,
    "predictions_count": 0
  }
}
```

---

## 4. PostGIS Perimeter Integration Test

**Test Function:** `test_get_incident_detail_with_postgis_perimeter(db_client: TestClient, db_session: Session)`  
**Location:** [`backend/tests/integration/test_incidents_api.py`](backend/tests/integration/test_incidents_api.py#L112-L194)

### Verification Steps Executed in Test:
1. **API Creation:** Registers an incident (`"Rim Fire Perimeter Survey"`) via `POST /api/v1/incidents`.
2. **Database Perimeter Injection:** Executes parameterized SQL on `db_session`:
   ```sql
   UPDATE incidents
   SET observed_perimeter = ST_GeomFromText(:wkt, 4326),
       perimeter_updated_at = :perimeter_updated_at
   WHERE id = :incident_id
   ```
   Injecting WKT: `MULTIPOLYGON(((-120.0 38.0, -120.0 38.5, -119.5 38.5, -119.5 38.0, -120.0 38.0)))`.
3. **Detail Retrieval:** Calls `GET /api/v1/incidents/{incident_id}`.
4. **Validations:**
   - Status code is `200 OK`.
   - Incident coordinates (`37.8651`, `-119.5383`, SRID 4326) are preserved.
   - `observed_perimeter` is returned as a valid GeoJSON object (`dict`).
   - `observed_perimeter["type"] == "MultiPolygon"`.
   - `observed_perimeter["coordinates"]` matches the exact polygon coordinates: `[[[[-120.0, 38.0], [-120.0, 38.5], [-119.5, 38.5], [-119.5, 38.0], [-120.0, 38.0]]]]`.
   - `perimeter_updated_at` is an ISO-8601 timezone-aware timestamp string.
5. **List Endpoint Isolation:** Calls `GET /api/v1/incidents` and verifies that for the same incident, `observed_perimeter` and `perimeter_updated_at` are `None`, confirming heavy geometry columns are never loaded in list queries.

---

## 5. Actual Test & Dependency Verification Evidence

### Pytest Execution:
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
collecting ... collected 61 items

backend\tests\integration\test_db_connection.py::test_live_database_connection PASSED [  1%]
backend\tests\integration\test_health.py::test_health_check_endpoint PASSED [  3%]
backend\tests\integration\test_health.py::test_root_endpoint PASSED      [  4%]
backend\tests\integration\test_health.py::test_nonexistent_endpoint PASSED [  6%]
backend\tests\integration\test_incidents_api.py::test_create_incident_success PASSED [  8%]
backend\tests\integration\test_incidents_api.py::test_create_incident_validation_errors PASSED [  9%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_and_counts PASSED [ 11%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_with_postgis_perimeter PASSED [ 13%]
backend\tests\integration\test_incidents_api.py::test_get_incident_not_found_and_malformed_uuid PASSED [ 14%]
backend\tests\integration\test_list_incidents_filtering_and_pagination PASSED [ 16%]
backend\tests\integration\test_list_incidents_sorting_options PASSED [ 18%]
backend\tests\integration\test_patch_incident_fields_and_transitions PASSED [ 19%]
backend\tests\integration\test_patch_rejection_of_invalid_transitions PASSED [ 21%]
backend\tests\integration\test_patch_rejection_of_null_and_empty_payload PASSED [ 22%]
backend\tests\integration\test_patch_metadata_full_replacement PASSED [ 24%]
backend\tests\integration\test_archive_incident_and_immutability PASSED [ 26%]
backend\tests\unit\test_alembic.py::test_alembic_config_initialization PASSED [ 27%]
backend\tests\unit\test_alembic.py::test_include_object_filter PASSED    [ 29%]
backend\tests\unit\test_alembic_migrations.py::test_alembic_discovers_migration_history PASSED [ 31%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_upgrade_generation PASSED [ 32%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_downgrade_generation PASSED [ 34%]
backend\tests\unit\test_config.py::test_default_settings PASSED          [ 36%]
backend\tests\unit\test_config.py::test_cors_origins_parsing PASSED      [ 37%]
backend\tests\unit\test_config.py::test_resolved_paths PASSED            [ 39%]
backend\tests\unit\test_config.py::test_database_url_construction PASSED [ 40%]
backend\tests\unit\test_config.py::test_special_character_escaping_in_database_url PASSED [ 42%]
backend\tests\unit\test_config.py::test_masked_database_uri PASSED       [ 44%]
backend\tests\unit\test_db_engine.py::test_engine_dialect_and_driver PASSED [ 45%]
backend\tests\unit\test_db_engine.py::test_engine_pool_configuration PASSED [ 47%]
backend\tests\unit\test_db_engine.py::test_engine_lazy_initialization PASSED [ 49%]
backend\tests\unit\test_db_session.py::test_session_factory PASSED       [ 50%]
backend\tests\unit\test_db_session.py::test_get_db_yields_and_closes_normally PASSED [ 52%]
backend\tests\unit\test_db_session.py::test_get_db_closes_on_exception PASSED [ 54%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_valid PASSED [ 55%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_boundary_limits PASSED [ 57%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_nan_and_infinities PASSED [ 59%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_extra_fields PASSED [ 60%]
backend\tests\unit\test_coordinate_point_server_srid_default PASSED [ 62%]
backend\tests\unit\test_incident_create_valid PASSED [ 63%]
backend\tests\unit\test_incident_create_invalid_title PASSED [ 65%]
backend\tests\unit\test_incident_create_rejects_unexpected_fields PASSED [ 67%]
backend\tests\unit\test_incident_update_omitted_fields PASSED [ 68%]
backend\tests\unit\test_incident_update_rejects_empty_payload PASSED [ 70%]
backend\tests\unit\test_incident_update_rejects_explicit_null_on_non_nullable PASSED [ 72%]
backend\tests\unit\test_incident_update_metadata_replacement PASSED [ 73%]
backend\tests\unit\test_incident_service.py::test_status_transition_matrix_rules PASSED [ 75%]
backend\tests\unit\test_incident_service.py::test_invalid_status_transitions_rejected PASSED [ 77%]
backend\tests\unit\test_incident_service.py::test_severity_ranking_hierarchy PASSED [ 78%]
backend\tests\unit\test_models_base.py::test_declarative_base_naming_conventions PASSED [ 80%]
backend\tests\unit\test_models_base.py::test_approved_tables_registered PASSED [ 81%]
backend\tests\unit\test_models_schema.py::test_uuid_primary_keys PASSED  [ 83%]
backend\tests\unit\test_models_schema.py::test_spatial_column_types_and_srid PASSED [ 85%]
backend\tests\unit\test_models_schema.py::test_jsonb_columns PASSED      [ 86%]
backend\tests\unit\test_models_schema.py::test_timezone_aware_timestamps PASSED [ 88%]
backend\tests\unit\test_models_schema.py::test_foreign_keys_and_restrict_policy PASSED [ 90%]
backend\tests\unit\test_models_schema.py::test_relationships_and_back_populates PASSED [ 91%]
backend\tests\unit\test_models_schema.py::test_check_constraints_present PASSED [ 93%]
backend\tests\unit\test_models_schema.py::test_spatial_and_functional_indexes PASSED [ 95%]
backend\tests\unit\test_models_schema.py::test_exact_columns_and_rejection_of_unapproved_fields PASSED [ 96%]
backend\tests\unit\test_models_schema.py::test_column_nullability_and_immutability PASSED [ 98%]
backend\tests\unit\test_models_schema.py::test_metadata_declarative_base_preservation PASSED [100%]

============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 61 passed, 1 warning in 5.13s ========================
```

- **Collected:** 61
- **Passed:** 61
- **Failed:** 0
- **Skipped:** 0
- **Warnings:** 1 (Starlette testclient deprecation warning)
- **Time:** 5.13s

### Dependency Hygiene Check:
```powershell
.\.venv\Scripts\python.exe -m pip check
```
```text
No broken requirements found.
```

---

## 6. Schema & Migration Immutability Audit

### Read-Only Git Diff on Models & Alembic:
```powershell
git diff -- backend/app/models backend/alembic
```
```text
[Output: 0 lines - completely clean]
```

### Git Status Check:
```powershell
git status --short
```
```text
 M README.md
 M backend/app/schemas/incident.py
 M backend/app/services/incident_service.py
 M backend/tests/integration/test_incidents_api.py
```

- All 5 ORM models remain strictly frozen.
- Alembic migration `0001_initial_schema` remains strictly frozen.
- No Git commit or push was performed.
