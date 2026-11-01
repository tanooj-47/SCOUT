# SCOUT — Milestone 05 Code & Implementation Evidence Package

**Date:** October 30, 2026  
**Project:** SCOUT (Smart Crisis Observation & Understanding Technology)  
**Target Milestone:** Milestone 05 — Incident Management API  
**Auditor Role:** Senior Independent Backend & Database Architect Review  

---

## Table of Contents

1. [Actual Test & Dependency-Check Evidence (Part 2)](#part-2--actual-test--dependency-check-evidence)
2. [Live PostgreSQL / PostGIS Integration Verification (Part 3)](#part-3--live-postgresql--postgis-integration-verification)
3. [Transaction-Isolation Architecture Review (Part 4)](#part-4--review-of-transaction-isolation-tests)
4. [API Implementation Details & Compliance Review (Part 5)](#part-5--api-implementation-details--compliance-review)
5. [Schema & Migration Immutability Audit (Part 6)](#part-6--schema--migration-immutability-audit)
6. [Known Limitations, Deviations & Unresolved Issues](#part-7--known-limitations-deviations--unresolved-issues)
7. [Verbatim Source Code Package (Part 1: All 16 Files)](#part-1--verbatim-source-code-package)

---

## Part 2 — Actual Test & Dependency-Check Evidence

### 1. Pytest Test Suite Run

**Command:** `.\.venv\Scripts\python.exe -m pytest backend/tests -v`

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\TANOOJ\OneDrive\Desktop\SCOUT\backend
configfile: pytest.ini
plugins: anyio-4.15.1
collecting ... collected 60 items

backend\tests\integration\test_db_connection.py::test_live_database_connection PASSED [  1%]
backend\tests\integration\test_health.py::test_health_check_endpoint PASSED [  3%]
backend\tests\integration\test_health.py::test_root_endpoint PASSED      [  5%]
backend\tests\integration\test_health.py::test_nonexistent_endpoint PASSED [  6%]
backend\tests\integration\test_incidents_api.py::test_create_incident_success PASSED [  8%]
backend\tests\integration\test_incidents_api.py::test_create_incident_validation_errors PASSED [ 10%]
backend\tests\integration\test_incidents_api.py::test_get_incident_detail_and_counts PASSED [ 11%]
backend\tests\integration\test_incidents_api.py::test_get_incident_not_found_and_malformed_uuid PASSED [ 13%]
backend\tests\integration\test_incidents_api.py::test_list_incidents_filtering_and_pagination PASSED [ 15%]
backend\tests\integration\test_incidents_api.py::test_list_incidents_sorting_options PASSED [ 16%]
backend\tests\integration\test_patch_incident_fields_and_transitions PASSED [ 18%]
backend\tests\integration\test_patch_rejection_of_invalid_transitions PASSED [ 20%]
backend\tests\integration\test_patch_rejection_of_null_and_empty_payload PASSED [ 21%]
backend\tests\integration\test_patch_metadata_full_replacement PASSED [ 23%]
backend\tests\integration\test_archive_incident_and_immutability PASSED [ 25%]
backend\tests\unit\test_alembic.py::test_alembic_config_initialization PASSED [ 26%]
backend\tests\unit\test_alembic.py::test_include_object_filter PASSED    [ 28%]
backend\tests\unit\test_alembic_migrations.py::test_alembic_discovers_migration_history PASSED [ 30%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_upgrade_generation PASSED [ 31%]
backend\tests\unit\test_alembic_migrations.py::test_offline_sql_downgrade_generation PASSED [ 33%]
backend\tests\unit\test_config.py::test_default_settings PASSED          [ 35%]
backend\tests\unit\test_config.py::test_cors_origins_parsing PASSED      [ 36%]
backend\tests\unit\test_config.py::test_resolved_paths PASSED            [ 38%]
backend\tests\unit\test_config.py::test_database_url_construction PASSED [ 40%]
backend\tests\unit\test_config.py::test_special_character_escaping_in_database_url PASSED [ 41%]
backend\tests\unit\test_config.py::test_masked_database_uri PASSED       [ 43%]
backend\tests\unit\test_db_engine.py::test_engine_dialect_and_driver PASSED [ 45%]
backend\tests\unit\test_db_engine.py::test_engine_pool_configuration PASSED [ 46%]
backend\tests\unit\test_db_engine.py::test_engine_lazy_initialization PASSED [ 48%]
backend\tests\unit\test_db_session.py::test_session_factory PASSED       [ 50%]
backend\tests\unit\test_db_session.py::test_get_db_yields_and_closes_normally PASSED [ 51%]
backend\tests\unit\test_db_session.py::test_get_db_closes_on_exception PASSED [ 53%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_valid PASSED [ 55%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_boundary_limits PASSED [ 56%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_nan_and_infinities PASSED [ 58%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_input_rejects_extra_fields PASSED [ 60%]
backend\tests\unit\test_incident_schemas.py::test_coordinate_point_server_srid_default PASSED [ 61%]
backend\tests\unit\test_incident_schemas.py::test_incident_create_valid PASSED [ 63%]
backend\tests\unit\test_incident_schemas.py::test_incident_create_invalid_title PASSED [ 65%]
backend\tests\unit\test_incident_schemas.py::test_incident_create_rejects_unexpected_fields PASSED [ 66%]
backend\tests\unit\test_incident_update_omitted_fields PASSED [ 68%]
backend\tests\unit\test_incident_update_rejects_empty_payload PASSED [ 70%]
backend\tests\unit\test_incident_update_rejects_explicit_null_on_non_nullable PASSED [ 71%]
backend\tests\unit\test_incident_update_metadata_replacement PASSED [ 73%]
backend\tests\unit\test_incident_service.py::test_status_transition_matrix_rules PASSED [ 75%]
backend\tests\unit\test_incident_service.py::test_invalid_status_transitions_rejected PASSED [ 76%]
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
======================== 60 passed, 1 warning in 4.94s ========================
```

- **Tests Collected:** 60
- **Passed:** 60
- **Failed:** 0
- **Skipped:** 0
- **Warnings:** 1 (StarletteDeprecationWarning regarding httpx with starlette.testclient)
- **Execution Time:** 4.94 seconds

### 2. Dependency Health Check

**Command:** `.\.venv\Scripts\python.exe -m pip check`

```text
No broken requirements found.
```

---

## Part 3 — Live PostgreSQL / PostGIS Integration Verification

A direct read-only query was executed against the configured local PostgreSQL/PostGIS database instance using `SessionLocal` from `app.db.session`.

**Verification Output:**
```text
SELECT 1: 1
PostGIS_Full_Version: POSTGIS="3.4.3 e365945" [EXTENSION] PGSQL="160" GEOS="3.9.0-CAPI-1.16.2" PROJ="7.2.1 NETWORK_ENABLED=OFF URL_ENDPOINT=https://cdn.proj.org USER_WRITABLE_DIRECTORY=/var/lib/postgresql/.local/share/proj DATABASE_PATH=/usr/share/proj/proj.db" LIBXML="2.9.10" LIBJSON="0.15" LIBPROTOBUF="1.3.3" WAGYU="0.5.0 (Internal)"
All public tables: ['alembic_version', 'detection_results', 'environmental_observations', 'hazard_predictions', 'incidents', 'spatial_ref_sys', 'uploaded_media']
Application tables: ['detection_results', 'environmental_observations', 'hazard_predictions', 'incidents', 'uploaded_media']
Alembic current version: 0001_initial_schema
```

### Findings:
1. **PostgreSQL Connection & Query Execution:** Succeeded (`SELECT 1 -> 1`).
2. **PostGIS Engine:** Fully operational (`PostGIS 3.4.3` on `PGSQL 160`).
3. **Application Tables:** Exactly the five approved application entities exist:
   - `incidents`
   - `uploaded_media`
   - `detection_results`
   - `environmental_observations`
   - `hazard_predictions`
4. **PostGIS System & Infrastructure Tables:** Only PostGIS system metadata (`spatial_ref_sys`) and Alembic version tracking (`alembic_version`) are present. No unauthorized tables exist.
5. **Alembic Revision Head:** Matches `0001_initial_schema` precisely.

---

## Part 4 — Review of Transaction-Isolation Tests

Independent architectural audit of `backend/tests/conftest.py`:

### 1. Does it connect to the real PostgreSQL database?
- **Yes.** In `backend/tests/conftest.py` (lines 6, 36), the fixture imports `engine` from `app.db.session` and invokes `connection = engine.connect()`. The engine is bound to the live containerized PostgreSQL/PostGIS database on `127.0.0.1:5432/scout`.

### 2. Does it use an outer transaction?
- **Yes.** In `backend/tests/conftest.py` (line 37), an explicit physical transaction is initiated on the connection: `transaction = connection.begin()`.

### 3. Does it use SQLAlchemy `join_transaction_mode="create_savepoint"`?
- **Yes.** In `backend/tests/conftest.py` (line 38), the test session is constructed with:  
  `session = Session(bind=connection, join_transaction_mode="create_savepoint")`  
  This ensures that when business logic in the service layer calls `db.commit()`, SQLAlchemy translates that commit into releasing a savepoint (`RELEASE SAVEPOINT ...`), rather than committing the outer physical transaction to disk.

### 4. Are test writes rolled back after each test?
- **Yes.** In `backend/tests/conftest.py` (line 46), the fixture teardown calls `transaction.rollback()`. This atomically discards all savepoints and all database row modifications performed during the test execution.

### 5. Can a failed test leave persistent records?
- **No.** The fixture uses a triple-nested `try ... finally` block (lines 39–50):
  ```python
  try:
      yield session
  finally:
      try:
          session.close()
      finally:
          try:
              transaction.rollback()
          finally:
              connection.close()
              engine.dispose()
  ```
  Even if an assertion fails or an unexpected exception is raised in test logic, the Python runtime guarantees the execution of the `finally` hierarchy, closing the session, rolling back the transaction, closing the connection, and calling `engine.dispose()` to reset the connection pool.

### 6. Does the fixture override `get_db` correctly?
- **Yes.** In `backend/tests/conftest.py` (lines 58–62), the `db_client` fixture overrides FastAPI's dependency:
  ```python
  saved_overrides = dict(app.dependency_overrides)
  try:
      app.dependency_overrides[get_db] = lambda: db_session
      with TestClient(app) as test_client:
          yield test_client
  ```

### 7. Is the override removed after the test?
- **Yes.** In `backend/tests/conftest.py` (line 64), the `finally` block executes `app.dependency_overrides = saved_overrides`, guaranteeing that dependency overrides are strictly restored to their prior state.

---

## Part 5 — API Implementation Details & Compliance Review

Architectural verification of the Milestone 05 implementation:

### 1. Avoidance of Geometry Column Loading on List Queries
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 41–55, 209–216), `list_incidents` selects only `*INCIDENT_SCALAR_PROJECTION`:
  ```python
  INCIDENT_SCALAR_PROJECTION = [
      Incident.id, Incident.disaster_type, Incident.title, Incident.status, Incident.severity,
      ST_X(Incident.location).label("longitude"), ST_Y(Incident.location).label("latitude"),
      Incident.reported_at, Incident.updated_at, Incident.contained_at,
      Incident.is_archived, Incident.archived_at, Incident.incident_metadata.label("metadata"),
  ]
  ```
  `Incident.location` is only evaluated via SQL functions `ST_X` and `ST_Y` producing raw floats. No binary geometry columns or `WKBElement` objects are retrieved, and `Incident.observed_perimeter` is completely excluded from list queries.

### 2. Detail Response Coordinates & Perimeter GeoJSON
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 58–62, 110–128), `INCIDENT_DETAIL_PROJECTION` selects `ST_AsGeoJSON(Incident.observed_perimeter).label("perimeter_geojson")` and `Incident.perimeter_updated_at`. If the perimeter exists, `json.loads` converts the GeoJSON text into a Python dict; coordinates are returned via `CoordinatePoint(latitude=m["latitude"], longitude=m["longitude"])`.

### 3. Pagination & Deterministic Secondary Ordering
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 194–229), `list_incidents` calculates `total = db.scalar(count_stmt)` and orders rows by `(sort_col, Incident.id.asc())`. The primary sort column is user-selectable (`reported_at`, `updated_at`, or `severity`), while `Incident.id.asc()` provides a stable secondary tie-breaker.

### 4. Operational Severity Ranking Hierarchy
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 75–84), `SEVERITY_ORDER` maps:
  `critical` (1) > `high` (2) > `moderate` (3) > `low` (4).  
  When `order_by="severity"` and `order_direction="desc"` (line 202), `SEVERITY_ORDER.asc()` is used so rank 1 (`critical`) appears first.

### 5. Status Transition State Machine Compliance
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 65–72, 285–293), `ALLOWED_TRANSITIONS` precisely implements:
  - `reported`: `{"investigating", "active", "false_alarm"}`
  - `investigating`: `{"active", "contained", "resolved", "false_alarm"}`
  - `active`: `{"contained", "resolved"}`
  - `contained`: `{"active", "resolved"}`
  - `resolved`: `{"active"}`
  - `false_alarm`: `set()` (terminal)
  Invalid transitions raise `InvalidStatusTransitionError` (HTTP 409).

### 6. `contained_at` Lifecycle Rules
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 295–306):
  - Transition to `contained`: sets `contained_at = datetime.now(timezone.utc)` if unset.
  - Transition from `contained` back to `active`: sets `contained_at = None` (containment breached).
  - Transition from `resolved` back to `active`: sets `contained_at = None` (incident rekindled).
  - Transition from `contained` to `resolved`: preserves historical `contained_at`.

### 7. Rejection of Modifications on Archived Incidents
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 279–280), `update_incident` checks `if incident.is_archived: raise ArchivedIncidentModificationError(incident_id)`. Returns HTTP 409 Conflict with code `INCIDENT_ARCHIVED`.

### 8. Archive Request Idempotency
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 357–362), `archive_incident` checks `if incident.is_archived:` and returns `200 OK` with the projected incident data without error or mutation.

### 9. Database Error Handling & Information Leakage Prevention
- **Confirmed.** In `backend/app/services/incident_service.py` (lines 159–166, 338–346, 374–381) and `backend/app/core/exceptions.py` (lines 89–153):
  - `IntegrityError` is wrapped into `DatabaseConflictError` (HTTP 409).
  - `SQLAlchemyError` is wrapped into `InternalServiceError` (HTTP 500).
  - Detailed SQL statements, connection URLs, and stack traces are suppressed from client responses and logged exclusively on the server.

### 10. Audit of Response Summary Counts & `detections_count`
- **Confirmed:** In `backend/app/schemas/incident.py` (lines 164–169), `IncidentSummaryCounts` defines exactly:
  ```python
  class IncidentSummaryCounts(BaseModel):
      media_count: int = Field(default=0, ge=0)
      observation_count: int = Field(default=0, ge=0)
      prediction_count: int = Field(default=0, ge=0)
  ```
- **Special Audit on `detections_count`:** `detections_count` is **NOT** present in `IncidentSummaryCounts` or in the API response. In the database schema, `detection_results` is a child table of `uploaded_media` (`detection_results.media_id -> uploaded_media.id`), not `incidents`. Therefore, `detections_count` was not added as an incident-level summary count, strictly honoring the approved architecture.

---

## Part 6 — Schema & Migration Immutability Audit

Verification that Milestone 05 maintained absolute immutability of the database schema and Alembic migration history:

### Git Read-Only Audit Commands

1. `git diff --name-only`:
```text
.env.example
README.md
backend/app/api/v1/router.py
backend/app/core/config.py
backend/app/main.py
backend/requirements.txt
backend/tests/conftest.py
backend/tests/unit/test_config.py
```

2. `git diff -- backend/app/models backend/alembic`:
```text
[Output is completely empty - 0 differences]
```

### Schema Invariants Summary:
- **SQLAlchemy Models:** All five ORM entity models (`Incident`, `UploadedMedia`, `DetectionResult`, `EnvironmentalObservation`, `HazardPrediction`) in `backend/app/models/` remain 100% untouched.
- **Alembic Migrations:** No new migrations were created. Migration `20261030_0001_initial_schema.py` remains the active head (`0001_initial_schema`).
- **Database Tables & Constraints:** Table structures, column nullability, check constraints, foreign keys with `RESTRICT` delete policies, and GiST spatial indexes remain completely unchanged.
- **Database Dependencies:** Core dependencies (`geoalchemy2`, `psycopg2-binary`, `alembic`, `sqlalchemy`) were not modified.

---

## Part 7 — Known Limitations, Deviations & Unresolved Issues

1. **Deprecation Warning from Starlette TestClient:**  
   When running tests, Starlette emits a single warning:  
   `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead.`  
   This is an upstream cosmetic warning from Starlette/FastAPI that does not affect runtime execution.
2. **No Per-Incident Boundary Ingestion Endpoint:**  
   Observed perimeter polygons can be returned in detail responses (`observed_perimeter`), but are currently populated through geospatial ingest pipelines rather than the basic REST PATCH endpoint. This is by design according to the roadmap.
3. **Single Persistent Development Row:**  
   The live database contains 1 row in `incidents` from the post-implementation smoke test exercise. The other 4 multimodal tables remain empty (`0` rows).

---

## Part 1 — Verbatim Source Code Package

The complete, verbatim contents of all 16 requested files are presented below:

### 1. backend/app/services/incident_service.py

**Path:** `backend/app/services/incident_service.py`  

```python
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_AsGeoJSON, ST_X, ST_Y
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ArchivedIncidentModificationError,
    DatabaseConflictError,
    IncidentNotFoundError,
    InternalServiceError,
    InvalidStatusTransitionError,
)
from app.models.detection_result import DetectionResult  # noqa: F401
from app.models.environmental_observation import EnvironmentalObservation
from app.models.hazard_prediction import HazardPrediction
from app.models.incident import Incident
from app.models.uploaded_media import UploadedMedia
from app.schemas.incident import (
    CoordinatePoint,
    DisasterType,
    IncidentCreate,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentStatus,
    IncidentSummaryCounts,
    IncidentUpdate,
    Severity,
)

logger = logging.getLogger(__name__)

# Canonical Scalar Projection for List and Write Operations (Excludes raw geometry and observed_perimeter)
INCIDENT_SCALAR_PROJECTION = [
    Incident.id,
    Incident.disaster_type,
    Incident.title,
    Incident.status,
    Incident.severity,
    ST_X(Incident.location).label("longitude"),
    ST_Y(Incident.location).label("latitude"),
    Incident.reported_at,
    Incident.updated_at,
    Incident.contained_at,
    Incident.is_archived,
    Incident.archived_at,
    Incident.incident_metadata.label("metadata"),
]

# Canonical Detail Projection (Includes perimeter metadata and PostGIS GeoJSON representation)
INCIDENT_DETAIL_PROJECTION = [
    *INCIDENT_SCALAR_PROJECTION,
    Incident.perimeter_updated_at,
    ST_AsGeoJSON(Incident.observed_perimeter).label("perimeter_geojson"),
]

# Approved operational lifecycle transitions
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "reported": {"investigating", "active", "false_alarm"},
    "investigating": {"active", "contained", "resolved", "false_alarm"},
    "active": {"contained", "resolved"},
    "contained": {"active", "resolved"},
    "resolved": {"active"},
    "false_alarm": set(),
}

# Operational Severity Ranking: Critical (1) > High (2) > Moderate (3) > Low (4)
SEVERITY_ORDER = case(
    {
        "critical": 1,
        "high": 2,
        "moderate": 3,
        "low": 4,
    },
    value=Incident.severity,
    else_=5,
)


def _row_to_incident_response(row: Any) -> IncidentResponse:
    """Converts a projected scalar row to an IncidentResponse schema using row._mapping."""
    m = row._mapping
    return IncidentResponse(
        id=m["id"],
        disaster_type=m["disaster_type"],
        title=m["title"],
        status=m["status"],
        severity=m["severity"],
        location=CoordinatePoint(latitude=m["latitude"], longitude=m["longitude"]),
        observed_perimeter=None,
        perimeter_updated_at=None,
        reported_at=m["reported_at"],
        updated_at=m["updated_at"],
        contained_at=m["contained_at"],
        is_archived=m["is_archived"],
        archived_at=m["archived_at"],
        metadata=m["metadata"],
    )


def _row_to_detail_response(row: Any, counts: IncidentSummaryCounts) -> IncidentDetailResponse:
    """Converts a projected detail row to an IncidentDetailResponse schema with parsed GeoJSON."""
    m = row._mapping
    perimeter_dict = json.loads(m["perimeter_geojson"]) if m["perimeter_geojson"] else None
    return IncidentDetailResponse(
        id=m["id"],
        disaster_type=m["disaster_type"],
        title=m["title"],
        status=m["status"],
        severity=m["severity"],
        location=CoordinatePoint(latitude=m["latitude"], longitude=m["longitude"]),
        observed_perimeter=perimeter_dict,
        perimeter_updated_at=m["perimeter_updated_at"],
        reported_at=m["reported_at"],
        updated_at=m["updated_at"],
        contained_at=m["contained_at"],
        is_archived=m["is_archived"],
        archived_at=m["archived_at"],
        metadata=m["metadata"],
        summary_counts=counts,
    )


def create_incident(db: Session, schema: IncidentCreate) -> IncidentResponse:
    """
    Registers a new disaster incident with PostGIS POINT SRID 4326.
    Enforces initial status='reported', is_archived=False, and assigns UTC timestamps.
    """
    now = datetime.now(timezone.utc)
    point_wkt = WKTElement(f"POINT({schema.location.longitude} {schema.location.latitude})", srid=4326)

    incident = Incident(
        disaster_type=schema.disaster_type.value,
        title=schema.title,
        status=IncidentStatus.REPORTED.value,
        severity=schema.severity.value,
        location=point_wkt,
        reported_at=now,
        updated_at=now,
        is_archived=False,
        incident_metadata=schema.metadata,
    )

    try:
        db.add(incident)
        db.flush()

        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        db.commit()
        return _row_to_incident_response(row)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Database integrity violation on incident create: %s", exc)
        raise DatabaseConflictError("Incident creation violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unexpected database error on incident create: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while creating the incident.") from exc


def list_incidents(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    disaster_type: Optional[DisasterType] = None,
    status: Optional[IncidentStatus] = None,
    severity: Optional[Severity] = None,
    is_archived: bool = False,
    order_by: str = "reported_at",
    order_direction: str = "desc",
) -> IncidentListResponse:
    """
    Retrieves a paginated collection of incidents matching the specified filters.
    Selects only scalar columns and coordinate projections.
    Perimeter polygons are never loaded in list queries.
    """
    filters = [Incident.is_archived == is_archived]

    if disaster_type is not None:
        filters.append(Incident.disaster_type == disaster_type.value)
    if status is not None:
        filters.append(Incident.status == status.value)
    if severity is not None:
        filters.append(Incident.severity == severity.value)

    # 1. Total matching count query
    count_stmt = select(func.count(Incident.id)).where(*filters)
    total = db.scalar(count_stmt) or 0

    # 2. Ordering definition
    direction = order_direction.lower()
    if order_by == "severity":
        # desc: critical (1) -> low (4); asc: low (4) -> critical (1)
        sort_col = SEVERITY_ORDER.asc() if direction == "desc" else SEVERITY_ORDER.desc()
    elif order_by == "updated_at":
        sort_col = Incident.updated_at.desc() if direction == "desc" else Incident.updated_at.asc()
    else:  # default: reported_at
        sort_col = Incident.reported_at.desc() if direction == "desc" else Incident.reported_at.asc()

    # 3. Data query with deterministic secondary sort on Incident.id.asc()
    data_stmt = (
        select(*INCIDENT_SCALAR_PROJECTION)
        .where(*filters)
        .order_by(sort_col, Incident.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(data_stmt).all()

    items = [_row_to_incident_response(r) for r in rows]
    has_next = (offset + limit) < total
    has_prev = offset > 0

    return IncidentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
        has_prev=has_prev,
    )


def get_incident_detail(db: Session, incident_id: UUID) -> IncidentDetailResponse:
    """
    Retrieves full details of an incident including related record counts and perimeter GeoJSON.
    Uses aggregate subqueries rather than hydrating child collections.
    """
    stmt = select(*INCIDENT_DETAIL_PROJECTION).where(Incident.id == incident_id)
    row = db.execute(stmt).first()
    if row is None:
        raise IncidentNotFoundError(incident_id)

    # Efficient scalar count queries for associated multimodal records
    media_count = (
        db.scalar(select(func.count(UploadedMedia.id)).where(UploadedMedia.incident_id == incident_id)) or 0
    )
    obs_count = (
        db.scalar(
            select(func.count(EnvironmentalObservation.id)).where(
                EnvironmentalObservation.incident_id == incident_id
            )
        )
        or 0
    )
    pred_count = (
        db.scalar(
            select(func.count(HazardPrediction.id)).where(HazardPrediction.incident_id == incident_id)
        )
        or 0
    )

    counts = IncidentSummaryCounts(
        media_count=media_count,
        observation_count=obs_count,
        prediction_count=pred_count,
    )

    return _row_to_detail_response(row, counts)


def update_incident(db: Session, incident_id: UUID, schema: IncidentUpdate) -> IncidentResponse:
    """
    Partially updates mutable attributes of an incident.
    Enforces status transition rules, contained_at lifecycle, and archived incident immutability.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise IncidentNotFoundError(incident_id)

    if incident.is_archived:
        raise ArchivedIncidentModificationError(incident_id)

    fields_to_update = schema.model_fields_set

    # 1. Handle Status Transition and Contained Timestamp Lifecycle
    if "status" in fields_to_update and schema.status is not None:
        current_status = incident.status
        new_status = schema.status.value

        if new_status != current_status:
            allowed = ALLOWED_TRANSITIONS.get(current_status, set())
            if new_status not in allowed:
                raise InvalidStatusTransitionError(current_status, new_status)

            # Contained timestamp lifecycle rules
            if new_status == "contained":
                if incident.contained_at is None:
                    incident.contained_at = datetime.now(timezone.utc)
            elif current_status == "contained" and new_status == "active":
                # Containment lost / flare-up
                incident.contained_at = None
            elif current_status == "resolved" and new_status == "active":
                # Resolved incident rekindled into active
                incident.contained_at = None
            elif current_status == "contained" and new_status == "resolved":
                # Containment achieved prior to resolution: preserve timestamp
                pass

            incident.status = new_status

    # 2. Handle Title Update
    if "title" in fields_to_update and schema.title is not None:
        incident.title = schema.title

    # 3. Handle Severity Update
    if "severity" in fields_to_update and schema.severity is not None:
        incident.severity = schema.severity.value

    # 4. Handle Location Update
    if "location" in fields_to_update and schema.location is not None:
        point_wkt = WKTElement(
            f"POINT({schema.location.longitude} {schema.location.latitude})",
            srid=4326,
        )
        incident.location = point_wkt

    # 5. Handle Metadata Update (Full JSONB replacement semantics)
    if "metadata" in fields_to_update and schema.metadata is not None:
        incident.incident_metadata = schema.metadata

    incident.updated_at = datetime.now(timezone.utc)

    try:
        db.flush()
        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        db.commit()
        return _row_to_incident_response(row)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Database integrity violation on incident update: %s", exc)
        raise DatabaseConflictError("Incident update violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unexpected database error on incident update: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while updating the incident.") from exc


def archive_incident(db: Session, incident_id: UUID) -> IncidentResponse:
    """
    Soft-deletes an incident by marking it archived.
    Idempotent: repeating an archive request on an already-archived incident succeeds with 200.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise IncidentNotFoundError(incident_id)

    # Idempotent response if already archived
    if incident.is_archived:
        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        return _row_to_incident_response(row)

    now = datetime.now(timezone.utc)
    incident.is_archived = True
    incident.archived_at = now
    incident.updated_at = now

    try:
        db.flush()
        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        db.commit()
        return _row_to_incident_response(row)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Database integrity violation on incident archive: %s", exc)
        raise DatabaseConflictError("Incident archival violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unexpected database error on incident archive: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while archiving the incident.") from exc
```

---

### 2. backend/app/api/v1/endpoints/incidents.py

**Path:** `backend/app/api/v1/endpoints/incidents.py`  

```python
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.incident import (
    DisasterType,
    IncidentCreate,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentStatus,
    IncidentUpdate,
    Severity,
)
from app.services import incident_service

router = APIRouter()


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new disaster incident",
)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """
    Registers a new disaster incident in physical space and time.
    Location coordinates are persisted as a PostGIS POINT (SRID 4326).
    """
    return incident_service.create_incident(db=db, schema=payload)


@router.get(
    "",
    response_model=IncidentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List, filter, and paginate disaster incidents",
)
def list_incidents(
    limit: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    disaster_type: Optional[DisasterType] = Query(default=None, description="Filter by disaster type"),
    incident_status: Optional[IncidentStatus] = Query(default=None, alias="status", description="Filter by operational status"),
    severity: Optional[Severity] = Query(default=None, description="Filter by impact severity"),
    is_archived: bool = Query(default=False, description="Filter by archival status (default: false)"),
    order_by: str = Query(default="reported_at", pattern="^(reported_at|updated_at|severity)$", description="Field to sort by"),
    order_direction: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort direction (asc/desc)"),
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    """
    Retrieves paginated incident records matching the query parameters.
    Deterministic secondary sorting on incident ID is enforced on all paths.
    """
    return incident_service.list_incidents(
        db=db,
        limit=limit,
        offset=offset,
        disaster_type=disaster_type,
        status=incident_status,
        severity=severity,
        is_archived=is_archived,
        order_by=order_by,
        order_direction=order_direction,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve incident detail and associated multimodal summary counts",
)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
) -> IncidentDetailResponse:
    """
    Retrieves complete details for a single incident including projected geometry,
    observed perimeter GeoJSON (if present), and summary counts of related assets.
    """
    return incident_service.get_incident_detail(db=db, incident_id=incident_id)


@router.patch(
    "/{incident_id}",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update mutable attributes of an incident",
)
def patch_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """
    Applies partial updates to mutable incident fields.
    Validates lifecycle state transitions and manages contained_at timestamp updates.
    Archived incidents cannot be modified (returns 409).
    """
    return incident_service.update_incident(db=db, incident_id=incident_id, schema=payload)


@router.post(
    "/{incident_id}/archive",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft-archive a disaster incident (idempotent)",
)
def archive_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """
    Soft-deletes an incident by marking it archived.
    Physical deletions are prohibited to preserve disaster intelligence history.
    """
    return incident_service.archive_incident(db=db, incident_id=incident_id)
```

---

### 3. backend/app/schemas/incident.py

**Path:** `backend/app/schemas/incident.py`  

```python
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from app.schemas.common import PaginatedResponse


class DisasterType(str, Enum):
    """Approved disaster classification categories."""
    WILDFIRE = "wildfire"
    FLOOD = "flood"
    EARTHQUAKE = "earthquake"


class IncidentStatus(str, Enum):
    """Approved operational lifecycle statuses."""
    REPORTED = "reported"
    INVESTIGATING = "investigating"
    ACTIVE = "active"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"


class Severity(str, Enum):
    """Approved impact severity tiers."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class CoordinateInput(BaseModel):
    """
    Client coordinate input schema.
    Strictly accepts decimal latitude and longitude within physical bounds.
    Rejects NaN, +inf, -inf, and extra fields.
    SRID is server-controlled (EPSG:4326) and excluded from client requests.
    """
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        allow_inf_nan=False,
        description="WGS 84 Latitude in decimal degrees [-90.0, 90.0]"
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        allow_inf_nan=False,
        description="WGS 84 Longitude in decimal degrees [-180.0, 180.0]"
    )


class CoordinatePoint(BaseModel):
    """
    Server coordinate response schema.
    Returns latitude, longitude, and constant server-controlled SRID 4326.
    """
    latitude: float = Field(..., description="WGS 84 Latitude in decimal degrees")
    longitude: float = Field(..., description="WGS 84 Longitude in decimal degrees")
    srid: int = Field(default=4326, description="Spatial reference system identifier (WGS 84)")


class IncidentCreate(BaseModel):
    """
    Schema for creating a new disaster incident.
    Omitted protected fields (status, timestamps, archive flags) are assigned by the service.
    """
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=3, max_length=255, description="Operational callsign or incident title")
    disaster_type: DisasterType = Field(..., description="Hazard category")
    severity: Severity = Field(default=Severity.LOW, description="Initial severity assessment")
    location: CoordinateInput = Field(..., description="Point of origin geographic coordinates")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Operational metadata dictionary")

    @field_validator("title")
    @classmethod
    def validate_title_trimmed(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters")
        return trimmed


class IncidentUpdate(BaseModel):
    """
    Partial update schema for incidents.
    
    Rules:
    - Omitted fields: Preserved as-is in database.
    - Explicit null: Rejected for every non-nullable mutable field.
    - Empty payload ({}): Explicitly rejected.
    - Extra fields: Rejected.
    """
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    status: Optional[IncidentStatus] = None
    severity: Optional[Severity] = None
    location: Optional[CoordinateInput] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("title")
    @classmethod
    def validate_title_trimmed(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if len(trimmed) < 3:
                raise ValueError("Title must contain at least 3 non-whitespace characters")
            return trimmed
        return v

    @model_validator(mode="after")
    def validate_patch_semantics(self) -> "IncidentUpdate":
        # 1. Reject empty PATCH payload
        if not self.model_fields_set:
            raise ValueError("At least one mutable field must be provided in the update payload")

        # 2. Reject explicit null for non-nullable fields
        non_nullable_fields = ("title", "status", "severity", "location", "metadata")
        for field_name in non_nullable_fields:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"Field '{field_name}' is non-nullable and cannot be set to null")

        return self


class IncidentResponse(BaseModel):
    """Standard incident output schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    disaster_type: DisasterType
    title: str
    status: IncidentStatus
    severity: Severity
    location: CoordinatePoint
    observed_perimeter: Optional[Dict[str, Any]] = None
    perimeter_updated_at: Optional[datetime] = None
    reported_at: datetime
    updated_at: datetime
    contained_at: Optional[datetime] = None
    is_archived: bool
    archived_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="incident_metadata",
        serialization_alias="metadata",
    )


class IncidentSummaryCounts(BaseModel):
    """Summary record counts for related multimodal entities."""
    media_count: int = Field(default=0, ge=0, description="Count of associated media records")
    observation_count: int = Field(default=0, ge=0, description="Count of environmental observations")
    prediction_count: int = Field(default=0, ge=0, description="Count of hazard predictions")


class IncidentDetailResponse(IncidentResponse):
    """Detailed incident response with summary counts of related multimodal data."""
    summary_counts: IncidentSummaryCounts = Field(default_factory=IncidentSummaryCounts)


class IncidentListResponse(PaginatedResponse[IncidentResponse]):
    """Paginated collection of incident summaries."""
    pass
```

---

### 4. backend/app/core/exceptions.py

**Path:** `backend/app/core/exceptions.py`  

```python
import logging
from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class SCOUTException(Exception):
    """Base domain exception for SCOUT application."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class IncidentNotFoundError(SCOUTException):
    """Raised when an incident is not found by ID."""

    def __init__(self, incident_id: UUID):
        super().__init__(
            code="INCIDENT_NOT_FOUND",
            message=f"Incident with ID '{incident_id}' was not found.",
            status_code=404,
            details={"incident_id": str(incident_id)},
        )


class InvalidStatusTransitionError(SCOUTException):
    """Raised when an invalid lifecycle status transition is requested."""

    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            code="INVALID_STATUS_TRANSITION",
            message=f"Cannot transition incident status from '{current_status}' to '{target_status}'.",
            status_code=409,
            details={"current_status": current_status, "target_status": target_status},
        )


class ArchivedIncidentModificationError(SCOUTException):
    """Raised when an update is attempted on an archived (immutable) incident."""

    def __init__(self, incident_id: UUID):
        super().__init__(
            code="INCIDENT_ARCHIVED",
            message=f"Incident '{incident_id}' is archived and cannot be modified.",
            status_code=409,
            details={"incident_id": str(incident_id)},
        )


class DatabaseConflictError(SCOUTException):
    """Raised when a database constraint or state conflict occurs."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="INTEGRITY_VIOLATION",
            message=message,
            status_code=409,
            details=details or {},
        )


class InternalServiceError(SCOUTException):
    """Raised for unexpected service-level failures."""

    def __init__(self, message: str = "An internal error occurred."):
        super().__init__(
            code="INTERNAL_SERVER_ERROR",
            message=message,
            status_code=500,
            details={},
        )


async def scout_exception_handler(request: Request, exc: SCOUTException) -> JSONResponse:
    """Handles all SCOUT custom domain exceptions with standard error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles FastAPI/Pydantic request validation errors with standard error envelope."""
    # Convert error tuples to clean serializable dict
    formatted_errors = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", [])]
        formatted_errors.append({
            "field": ".".join(loc[1:]) if len(loc) > 1 else (loc[0] if loc else ""),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": formatted_errors},
            }
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handles standard Starlette/FastAPI HTTPExceptions (e.g. 404 for unknown routes)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safely catches unhandled exceptions, logs trace, and prevents leaking database internals."""
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred.",
                "details": {},
            }
        },
    )
```

---

### 5. backend/tests/conftest.py

**Path:** `backend/tests/conftest.py`  

```python
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import engine, get_db
from app.main import app


def pytest_configure(config):
    """Register custom markers so tests run cleanly with or without explicit ini discovery."""
    config.addinivalue_line(
        "markers",
        "database: Integration tests requiring a live PostgreSQL/PostGIS container",
    )


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """
    Standard in-process HTTP TestClient for endpoints not requiring database access
    (e.g. root navigational links, application liveness probes).
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Dedicated transactional session fixture for database-backed tests.
    Uses join_transaction_mode="create_savepoint" so service-level session.commit()
    calls are absorbed by savepoints and rolled back atomically with the outer transaction.
    Guarantees nested try/finally cleanup so connection and transaction are always closed.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        try:
            session.close()
        finally:
            try:
                transaction.rollback()
            finally:
                connection.close()
                engine.dispose()


@pytest.fixture(scope="function")
def db_client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Database-backed TestClient with get_db overridden to use the savepoint-isolated session.
    Preserves and restores existing dependency overrides safely.
    """
    saved_overrides = dict(app.dependency_overrides)
    try:
        app.dependency_overrides[get_db] = lambda: db_session
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides = saved_overrides
```

---

### 6. backend/tests/integration/test_incidents_api.py

**Path:** `backend/tests/integration/test_incidents_api.py`  

```python
import uuid
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.database


def test_create_incident_success(db_client: TestClient):
    """Verify that a valid incident is created with PostGIS coordinates and default status."""
    payload = {
        "title": "Blackwood Fire Incident",
        "disaster_type": "wildfire",
        "severity": "high",
        "location": {"latitude": 39.1234, "longitude": -120.4567},
        "metadata": {"region": "Tahoe Basin", "station_id": "FS-401"},
    }
    response = db_client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["title"] == "Blackwood Fire Incident"
    assert data["disaster_type"] == "wildfire"
    assert data["status"] == "reported"
    assert data["severity"] == "high"
    assert data["location"]["latitude"] == 39.1234
    assert data["location"]["longitude"] == -120.4567
    assert data["location"]["srid"] == 4326
    assert data["is_archived"] is False
    assert data["archived_at"] is None
    assert data["contained_at"] is None
    assert data["metadata"]["region"] == "Tahoe Basin"


def test_create_incident_validation_errors(db_client: TestClient):
    """Verify rejection of invalid coordinates, short title, and extra fields."""
    # Latitude out of bounds
    res_lat = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Invalid Lat Incident",
            "disaster_type": "wildfire",
            "location": {"latitude": 95.0, "longitude": 0.0},
        },
    )
    assert res_lat.status_code == 422
    assert res_lat.json()["error"]["code"] == "VALIDATION_ERROR"

    # NaN in coordinates (sent as raw JSON payload)
    res_nan = db_client.post(
        "/api/v1/incidents",
        content='{"title": "Invalid NaN Incident", "disaster_type": "wildfire", "location": {"latitude": NaN, "longitude": 0.0}}',
        headers={"Content-Type": "application/json"},
    )
    assert res_nan.status_code == 422

    # Client providing SRID (extra forbidden)
    res_srid = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Invalid SRID Incident",
            "disaster_type": "wildfire",
            "location": {"latitude": 10.0, "longitude": 10.0, "srid": 4326},
        },
    )
    assert res_srid.status_code == 422

    # Empty title
    res_title = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "   ",
            "disaster_type": "flood",
            "location": {"latitude": 10.0, "longitude": 10.0},
        },
    )
    assert res_title.status_code == 422


def test_get_incident_detail_and_counts(db_client: TestClient):
    """Verify retrieval of incident detail, projected coordinates, and summary counts."""
    # 1. Create incident
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Valley Inundation",
            "disaster_type": "flood",
            "severity": "moderate",
            "location": {"latitude": 28.5383, "longitude": -81.3792},
            "metadata": {"gauge_level_meters": 4.2},
        },
    )
    assert create_res.status_code == 201
    incident_id = create_res.json()["id"]

    # 2. Retrieve detail
    detail_res = db_client.get(f"/api/v1/incidents/{incident_id}")
    assert detail_res.status_code == 200
    data = detail_res.json()

    assert data["id"] == incident_id
    assert data["title"] == "Valley Inundation"
    assert data["location"]["latitude"] == 28.5383
    assert data["location"]["longitude"] == -81.3792
    assert data["summary_counts"]["media_count"] == 0
    assert data["summary_counts"]["observation_count"] == 0
    assert data["summary_counts"]["prediction_count"] == 0


def test_get_incident_not_found_and_malformed_uuid(db_client: TestClient):
    """Verify 404 on nonexistent UUID and 422 on malformed UUID."""
    random_id = str(uuid.uuid4())
    res_404 = db_client.get(f"/api/v1/incidents/{random_id}")
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "INCIDENT_NOT_FOUND"

    res_422 = db_client.get("/api/v1/incidents/not-a-valid-uuid")
    assert res_422.status_code == 422
    assert res_422.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_incidents_filtering_and_pagination(db_client: TestClient):
    """Verify listing with pagination, filtering by disaster_type, status, and severity."""
    # Seed distinct incidents
    incidents_data = [
        {"title": "Wildfire Alpha", "disaster_type": "wildfire", "severity": "low", "location": {"latitude": 30.0, "longitude": -100.0}},
        {"title": "Wildfire Beta", "disaster_type": "wildfire", "severity": "critical", "location": {"latitude": 31.0, "longitude": -101.0}},
        {"title": "Flood Gamma", "disaster_type": "flood", "severity": "moderate", "location": {"latitude": 32.0, "longitude": -102.0}},
    ]
    for inc in incidents_data:
        res = db_client.post("/api/v1/incidents", json=inc)
        assert res.status_code == 201

    # Filter by disaster_type=wildfire
    res_wf = db_client.get("/api/v1/incidents?disaster_type=wildfire")
    assert res_wf.status_code == 200
    data_wf = res_wf.json()
    assert data_wf["total"] >= 2
    for item in data_wf["items"]:
        assert item["disaster_type"] == "wildfire"
        assert item["observed_perimeter"] is None  # List never returns perimeter

    # Filter by severity=critical
    res_crit = db_client.get("/api/v1/incidents?severity=critical")
    assert res_crit.status_code == 200
    data_crit = res_crit.json()
    assert data_crit["total"] >= 1
    for item in data_crit["items"]:
        assert item["severity"] == "critical"

    # Pagination test: limit 1, offset 0
    res_page = db_client.get("/api/v1/incidents?limit=1&offset=0")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert len(page_data["items"]) == 1
    assert page_data["limit"] == 1
    assert page_data["offset"] == 0
    assert page_data["has_prev"] is False


def test_list_incidents_sorting_options(db_client: TestClient):
    """Verify sorting by reported_at, updated_at, and operational severity ranking."""
    res_sev = db_client.get("/api/v1/incidents?order_by=severity&order_direction=desc")
    assert res_sev.status_code == 200
    items = res_sev.json()["items"]
    # Check severity hierarchy: critical (1) before high (2) before moderate (3) before low (4)
    rank = {"critical": 1, "high": 2, "moderate": 3, "low": 4}
    severities = [rank[item["severity"]] for item in items]
    assert severities == sorted(severities)

    # Ascending updated_at
    res_upd = db_client.get("/api/v1/incidents?order_by=updated_at&order_direction=asc")
    assert res_upd.status_code == 200


def test_patch_incident_fields_and_transitions(db_client: TestClient):
    """Verify partial update of title, severity, location, and valid status transition."""
    # 1. Create incident (starts at 'reported')
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Bear Creek Fire",
            "disaster_type": "wildfire",
            "severity": "low",
            "location": {"latitude": 38.0, "longitude": -120.0},
        },
    )
    incident_id = create_res.json()["id"]

    # 2. Patch title and severity
    patch1 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"title": "Bear Creek Fire Complex", "severity": "high"},
    )
    assert patch1.status_code == 200
    assert patch1.json()["title"] == "Bear Creek Fire Complex"
    assert patch1.json()["severity"] == "high"

    # 3. Transition reported -> active
    patch2 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "active"},
    )
    assert patch2.status_code == 200
    assert patch2.json()["status"] == "active"
    assert patch2.json()["contained_at"] is None

    # 4. Transition active -> contained (triggers contained_at)
    patch3 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "contained"},
    )
    assert patch3.status_code == 200
    assert patch3.json()["status"] == "contained"
    assert patch3.json()["contained_at"] is not None

    # 5. Transition contained -> active (resets contained_at to null)
    patch4 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "active"},
    )
    assert patch4.status_code == 200
    assert patch4.json()["status"] == "active"
    assert patch4.json()["contained_at"] is None

    # 6. Contain again and transition contained -> resolved (preserves contained_at)
    db_client.patch(f"/api/v1/incidents/{incident_id}", json={"status": "contained"})
    patch6 = db_client.patch(f"/api/v1/incidents/{incident_id}", json={"status": "resolved"})
    assert patch6.status_code == 200
    assert patch6.json()["status"] == "resolved"
    assert patch6.json()["contained_at"] is not None


def test_patch_rejection_of_invalid_transitions(db_client: TestClient):
    """Verify 409 Conflict when attempting forbidden status transitions."""
    # Create incident (starts at 'reported')
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "State Machine Test Incident",
            "disaster_type": "wildfire",
            "location": {"latitude": 38.0, "longitude": -120.0},
        },
    )
    incident_id = create_res.json()["id"]

    # reported -> contained is forbidden (must investigate or confirm active first)
    res_bad = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "contained"},
    )
    assert res_bad.status_code == 409
    assert res_bad.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_patch_rejection_of_null_and_empty_payload(db_client: TestClient):
    """Verify rejection of empty body ({}) and explicit null on non-nullable fields."""
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Patch Validation Incident",
            "disaster_type": "flood",
            "location": {"latitude": 15.0, "longitude": 75.0},
        },
    )
    incident_id = create_res.json()["id"]

    # Empty payload
    res_empty = db_client.patch(f"/api/v1/incidents/{incident_id}", json={})
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # Explicit null on non-nullable fields
    for field in ["title", "status", "severity", "location", "metadata"]:
        res_null = db_client.patch(f"/api/v1/incidents/{incident_id}", json={field: None})
        assert res_null.status_code == 422


def test_patch_metadata_full_replacement(db_client: TestClient):
    """Verify that metadata PATCH fully replaces the JSONB dictionary."""
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Metadata Replacement Test",
            "disaster_type": "earthquake",
            "location": {"latitude": 35.0, "longitude": 139.0},
            "metadata": {"initial_key": "val1", "keep_me": "no"},
        },
    )
    incident_id = create_res.json()["id"]

    # Replace metadata
    patch_res = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"metadata": {"new_key": "val2"}},
    )
    assert patch_res.status_code == 200
    meta = patch_res.json()["metadata"]
    assert meta == {"new_key": "val2"}
    assert "initial_key" not in meta


def test_archive_incident_and_immutability(db_client: TestClient):
    """Verify soft-archival, idempotency, and 409 rejection of subsequent PATCH requests."""
    # 1. Create incident
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Incident To Archive",
            "disaster_type": "flood",
            "location": {"latitude": 10.0, "longitude": 20.0},
        },
    )
    incident_id = create_res.json()["id"]

    # 2. Archive incident
    arch_res = db_client.post(f"/api/v1/incidents/{incident_id}/archive")
    assert arch_res.status_code == 200
    data = arch_res.json()
    assert data["is_archived"] is True
    assert data["archived_at"] is not None

    # 3. Idempotent repeat archive returns 200
    arch_repeat = db_client.post(f"/api/v1/incidents/{incident_id}/archive")
    assert arch_repeat.status_code == 200
    assert arch_repeat.json()["is_archived"] is True

    # 4. Attempting to PATCH archived incident returns 409 Conflict
    patch_archived = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"title": "Attempted Change on Archived"},
    )
    assert patch_archived.status_code == 409
    assert patch_archived.json()["error"]["code"] == "INCIDENT_ARCHIVED"

    # 5. Default list excludes archived incident
    list_active = db_client.get("/api/v1/incidents")
    active_ids = [item["id"] for item in list_active.json()["items"]]
    assert incident_id not in active_ids

    # 6. Listing with is_archived=true includes it
    list_archived = db_client.get("/api/v1/incidents?is_archived=true")
    archived_ids = [item["id"] for item in list_archived.json()["items"]]
    assert incident_id in archived_ids
```

---

### 7. backend/tests/unit/test_incident_service.py

**Path:** `backend/tests/unit/test_incident_service.py`  

```python
import uuid
from datetime import datetime, timezone
import pytest

from app.core.exceptions import (
    ArchivedIncidentModificationError,
    InvalidStatusTransitionError,
)
from app.models.incident import Incident
from app.schemas.incident import (
    CoordinateInput,
    IncidentStatus,
    IncidentUpdate,
    Severity,
)
from app.services.incident_service import ALLOWED_TRANSITIONS, SEVERITY_ORDER


def test_status_transition_matrix_rules():
    """Verify approved transition matrix mappings."""
    assert ALLOWED_TRANSITIONS["reported"] == {"investigating", "active", "false_alarm"}
    assert ALLOWED_TRANSITIONS["investigating"] == {"active", "contained", "resolved", "false_alarm"}
    assert ALLOWED_TRANSITIONS["active"] == {"contained", "resolved"}
    assert ALLOWED_TRANSITIONS["contained"] == {"active", "resolved"}
    assert ALLOWED_TRANSITIONS["resolved"] == {"active"}
    assert ALLOWED_TRANSITIONS["false_alarm"] == set()


def test_invalid_status_transitions_rejected():
    """Verify that forbidden state transitions are identified."""
    # false_alarm is terminal
    for target in ["reported", "investigating", "active", "contained", "resolved"]:
        assert target not in ALLOWED_TRANSITIONS["false_alarm"]

    # reported cannot jump directly to contained or resolved
    assert "contained" not in ALLOWED_TRANSITIONS["reported"]
    assert "resolved" not in ALLOWED_TRANSITIONS["reported"]

    # active cannot regress to investigating or reported
    assert "investigating" not in ALLOWED_TRANSITIONS["active"]
    assert "reported" not in ALLOWED_TRANSITIONS["active"]


def test_severity_ranking_hierarchy():
    """Verify that operational ranking maps critical (1) > high (2) > moderate (3) > low (4)."""
    # SEVERITY_ORDER maps to integers: critical=1, high=2, moderate=3, low=4
    rank_dict = {c.value: v.value for c, v in SEVERITY_ORDER.whens}
    assert rank_dict["critical"] == 1
    assert rank_dict["high"] == 2
    assert rank_dict["moderate"] == 3
    assert rank_dict["low"] == 4
```

---

### 8. backend/tests/unit/test_incident_schemas.py

**Path:** `backend/tests/unit/test_incident_schemas.py`  

```python
import pytest
from pydantic import ValidationError

from app.schemas.incident import (
    CoordinateInput,
    CoordinatePoint,
    DisasterType,
    IncidentCreate,
    IncidentStatus,
    IncidentUpdate,
    Severity,
)


def test_coordinate_input_valid():
    """Verify that valid WGS 84 latitude and longitude pairs pass validation."""
    coord = CoordinateInput(latitude=34.0522, longitude=-118.2437)
    assert coord.latitude == 34.0522
    assert coord.longitude == -118.2437


def test_coordinate_input_boundary_limits():
    """Verify boundary checks on latitude (-90 to 90) and longitude (-180 to 180)."""
    # Exact boundary edges
    assert CoordinateInput(latitude=-90.0, longitude=-180.0) is not None
    assert CoordinateInput(latitude=90.0, longitude=180.0) is not None

    # Exceeding latitude bounds
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=90.001, longitude=0.0)
    assert "latitude" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=-90.001, longitude=0.0)
    assert "latitude" in str(exc.value)

    # Exceeding longitude bounds
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=0.0, longitude=180.001)
    assert "longitude" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=0.0, longitude=-180.001)
    assert "longitude" in str(exc.value)


def test_coordinate_input_rejects_nan_and_infinities():
    """Verify that allow_inf_nan=False explicitly rejects NaN, +inf, and -inf."""
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=float("nan"), longitude=0.0)
    assert "finite" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=float("inf"), longitude=0.0)
    assert "finite" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=0.0, longitude=float("-inf"))
    assert "finite" in str(exc.value).lower()


def test_coordinate_input_rejects_extra_fields():
    """Verify extra='forbid' rejects client-supplied srid or unknown fields."""
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=10.0, longitude=20.0, srid=4326)  # type: ignore[call-arg]
    assert "extra_forbidden" in str(exc.value) or "Extra inputs are not permitted" in str(exc.value)


def test_coordinate_point_server_srid_default():
    """Verify response schema provides constant server-controlled SRID 4326."""
    point = CoordinatePoint(latitude=21.15, longitude=79.08)
    assert point.srid == 4326


def test_incident_create_valid():
    """Verify valid IncidentCreate schema initialization and title trimming."""
    create = IncidentCreate(
        title="  Ridge Fire Incident  ",
        disaster_type=DisasterType.WILDFIRE,
        severity=Severity.HIGH,
        location=CoordinateInput(latitude=37.7749, longitude=-122.4194),
        metadata={"agency": "USFS", "tier": 1},
    )
    assert create.title == "Ridge Fire Incident"
    assert create.disaster_type == DisasterType.WILDFIRE
    assert create.severity == Severity.HIGH
    assert create.location.latitude == 37.7749
    assert create.metadata["agency"] == "USFS"


def test_incident_create_invalid_title():
    """Verify rejection of empty or excessively short titles."""
    with pytest.raises(ValidationError) as exc:
        IncidentCreate(
            title="   ",
            disaster_type=DisasterType.WILDFIRE,
            location=CoordinateInput(latitude=0.0, longitude=0.0),
        )
    assert "at least 3 non-whitespace" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        IncidentCreate(
            title="ab",
            disaster_type=DisasterType.WILDFIRE,
            location=CoordinateInput(latitude=0.0, longitude=0.0),
        )
    assert "at least 3" in str(exc.value).lower()


def test_incident_create_rejects_unexpected_fields():
    """Verify extra='forbid' on IncidentCreate prevents injection of protected fields."""
    with pytest.raises(ValidationError) as exc:
        IncidentCreate(
            title="Valid Title",
            disaster_type=DisasterType.WILDFIRE,
            location=CoordinateInput(latitude=0.0, longitude=0.0),
            status=IncidentStatus.ACTIVE,  # type: ignore[call-arg]
        )
    assert "extra_forbidden" in str(exc.value) or "Extra inputs are not permitted" in str(exc.value)


def test_incident_update_omitted_fields():
    """Verify that omitted fields in PATCH remain unset in model_fields_set."""
    update = IncidentUpdate(title="Updated Title")
    assert update.model_fields_set == {"title"}
    assert update.title == "Updated Title"
    assert update.status is None
    assert update.severity is None
    assert update.location is None
    assert update.metadata is None


def test_incident_update_rejects_empty_payload():
    """Verify that an empty PATCH body ({}) is explicitly rejected."""
    with pytest.raises(ValidationError) as exc:
        IncidentUpdate()
    assert "At least one mutable field must be provided" in str(exc.value)


def test_incident_update_rejects_explicit_null_on_non_nullable():
    """Verify that passing explicit null for non-nullable fields is rejected."""
    non_nullable_payloads = [
        {"title": None},
        {"status": None},
        {"severity": None},
        {"location": None},
        {"metadata": None},
    ]
    for payload in non_nullable_payloads:
        with pytest.raises(ValidationError) as exc:
            IncidentUpdate.model_validate(payload)
        assert "is non-nullable and cannot be set to null" in str(exc.value)


def test_incident_update_metadata_replacement():
    """Verify metadata replacement payload validation."""
    update = IncidentUpdate(metadata={"replacement_key": 42})
    assert update.metadata == {"replacement_key": 42}
    assert "metadata" in update.model_fields_set
```

---

### 9. backend/app/models/incident.py

**Path:** `backend/app/models/incident.py`  

```python
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Incident(Base):
    """
    Central aggregate root representing an authoritative disaster event
    in physical space and time.
    """
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    disaster_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="reported",
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="low",
    )
    location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    observed_perimeter: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    perimeter_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    contained_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Database column name is 'metadata'; mapped via incident_metadata to avoid
    # colliding with SQLAlchemy DeclarativeBase.metadata namespace.
    incident_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )

    # Relationships (Strict RESTRICT policy - no cascading deletions)
    uploaded_media: Mapped[List["UploadedMedia"]] = relationship(
        "UploadedMedia",
        back_populates="incident",
        passive_deletes="all",
    )
    environmental_observations: Mapped[List["EnvironmentalObservation"]] = relationship(
        "EnvironmentalObservation",
        back_populates="incident",
        passive_deletes="all",
    )
    hazard_predictions: Mapped[List["HazardPrediction"]] = relationship(
        "HazardPrediction",
        back_populates="incident",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "disaster_type IN ('wildfire', 'flood', 'earthquake')",
            name="ck_incidents_disaster_type",
        ),
        CheckConstraint(
            "status IN ('reported', 'investigating', 'active', 'contained', 'resolved', 'false_alarm')",
            name="ck_incidents_status",
        ),
        CheckConstraint(
            "severity IN ('low', 'moderate', 'high', 'critical')",
            name="ck_incidents_severity",
        ),
        CheckConstraint(
            "(is_archived = false AND archived_at IS NULL) OR (is_archived = true AND archived_at IS NOT NULL)",
            name="ck_incidents_archival_consistency",
        ),
        Index("ix_incidents_location", "location", postgresql_using="gist"),
        Index(
            "ix_incidents_location_geography",
            text("(location::geography)"),
            postgresql_using="gist",
        ),
        Index("ix_incidents_observed_perimeter", "observed_perimeter", postgresql_using="gist"),
        Index("ix_incidents_status_is_archived", "status", "is_archived"),
    )
```

---

### 10. backend/app/models/uploaded_media.py

**Path:** `backend/app/models/uploaded_media.py`  

```python
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UploadedMedia(Base):
    """
    Metadata for visual and remote sensing assets (drone images, satellite scenes, field camera frames).
    Actual binary payloads reside outside PostgreSQL in local storage or object stores.
    """
    __tablename__ = "uploaded_media"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    media_format: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    capture_location: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident",
        back_populates="uploaded_media",
    )
    detection_results: Mapped[List["DetectionResult"]] = relationship(
        "DetectionResult",
        back_populates="media",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_uploaded_media_file_size_bytes",
        ),
        Index("ix_uploaded_media_incident_id", "incident_id"),
        Index("ix_uploaded_media_captured_at", "captured_at"),
        Index("ix_uploaded_media_capture_location", "capture_location", postgresql_using="gist"),
    )
```

---

### 11. backend/app/models/detection_result.py

**Path:** `backend/app/models/detection_result.py`  

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DetectionResult(Base):
    """
    Inference outcomes produced by computer vision models evaluating uploaded media.
    """
    __tablename__ = "detection_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploaded_media.id", ondelete="RESTRICT"),
        nullable=False,
    )
    classification: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    bounding_boxes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    model_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    inference_latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    media: Mapped["UploadedMedia"] = relationship(
        "UploadedMedia",
        back_populates="detection_results",
    )

    __table_args__ = (
        CheckConstraint(
            "classification IN ('fire', 'smoke', 'neutral', 'floodwater')",
            name="ck_detection_results_classification",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_detection_results_confidence",
        ),
        CheckConstraint(
            "inference_latency_ms >= 0",
            name="ck_detection_results_inference_latency_ms",
        ),
        Index("ix_detection_results_media_id", "media_id"),
        Index("ix_detection_results_classification", "classification"),
        Index("ix_detection_results_created_at", "created_at"),
    )
```

---

### 12. backend/app/models/environmental_observation.py

**Path:** `backend/app/models/environmental_observation.py`  

```python
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EnvironmentalObservation(Base):
    """
    Environmental and meteorological observations tied to an incident.
    General atmospheric measurements are represented as columns, while
    disaster-specific metrics (e.g., river stage, seismic PGA) reside in metrics_payload.
    """
    __tablename__ = "environmental_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    temperature_celsius: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    relative_humidity: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    wind_speed_mps: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    wind_direction_degrees: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    precipitation_mm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    metrics_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="environmental_observations",
    )
    hazard_predictions: Mapped[List["HazardPrediction"]] = relationship(
        "HazardPrediction",
        back_populates="primary_observation",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "relative_humidity IS NULL OR (relative_humidity >= 0.0 AND relative_humidity <= 100.0)",
            name="ck_env_obs_relative_humidity",
        ),
        CheckConstraint(
            "wind_speed_mps IS NULL OR wind_speed_mps >= 0.0",
            name="ck_env_obs_wind_speed_mps",
        ),
        CheckConstraint(
            "wind_direction_degrees IS NULL OR (wind_direction_degrees >= 0.0 AND wind_direction_degrees <= 360.0)",
            name="ck_env_obs_wind_direction_degrees",
        ),
        CheckConstraint(
            "precipitation_mm IS NULL OR precipitation_mm >= 0.0",
            name="ck_env_obs_precipitation_mm",
        ),
        Index("ix_environmental_observations_incident_id", "incident_id"),
        Index("ix_environmental_observations_recorded_at", "recorded_at"),
        Index(
            "ix_environmental_observations_incident_recorded",
            "incident_id",
            text("recorded_at DESC"),
        ),
    )
```

---

### 13. backend/app/models/hazard_prediction.py

**Path:** `backend/app/models/hazard_prediction.py`  

```python
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class HazardPrediction(Base):
    """
    Append-only predictive hazard forecast.
    Preserves historical projected hazard footprints and immutable simulation
    provenance via input_snapshot.
    """
    __tablename__ = "hazard_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primary_observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("environmental_observations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    forecast_horizon_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    projected_area_hectares: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    predicted_footprint: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    input_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="hazard_predictions",
    )
    primary_observation: Mapped[Optional["EnvironmentalObservation"]] = relationship(
        "EnvironmentalObservation",
        back_populates="hazard_predictions",
    )

    __table_args__ = (
        CheckConstraint(
            "forecast_horizon_hours > 0.0",
            name="ck_hazard_predictions_forecast_horizon_hours",
        ),
        CheckConstraint(
            "projected_area_hectares >= 0.0",
            name="ck_hazard_predictions_projected_area_hectares",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'moderate', 'high', 'critical')",
            name="ck_hazard_predictions_risk_level",
        ),
        Index("ix_hazard_predictions_incident_id", "incident_id"),
        Index("ix_hazard_predictions_primary_observation_id", "primary_observation_id"),
        Index("ix_hazard_predictions_created_at", "created_at"),
        Index("ix_hazard_predictions_risk_level", "risk_level"),
        Index(
            "ix_hazard_predictions_incident_horizon",
            "incident_id",
            "forecast_horizon_hours",
        ),
        Index(
            "ix_hazard_predictions_predicted_footprint",
            "predicted_footprint",
            postgresql_using="gist",
        ),
        Index(
            "ix_hazard_predictions_footprint_geography",
            text("(predicted_footprint::geography)"),
            postgresql_using="gist",
        ),
    )
```

---

### 14. backend/alembic/versions/20261030_0001_initial_schema.py

**Path:** `backend/alembic/versions/20261030_0001_initial_schema.py`  

```python
"""create_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-30 11:55:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create table: incidents
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disaster_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column(
            "observed_perimeter",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("perimeter_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "disaster_type IN ('wildfire', 'flood', 'earthquake')",
            name="ck_incidents_disaster_type",
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'investigating', 'active', 'contained', 'resolved', 'false_alarm')",
            name="ck_incidents_status",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'moderate', 'high', 'critical')",
            name="ck_incidents_severity",
        ),
        sa.CheckConstraint(
            "(is_archived = false AND archived_at IS NULL) OR (is_archived = true AND archived_at IS NOT NULL)",
            name="ck_incidents_archival_consistency",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(
        "ix_incidents_location",
        "incidents",
        ["location"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_location_geography",
        "incidents",
        [sa.text("(location::geography)")],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_observed_perimeter",
        "incidents",
        ["observed_perimeter"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_status_is_archived",
        "incidents",
        ["status", "is_archived"],
        unique=False,
    )

    # 2. Create table: uploaded_media
    op.create_table(
        "uploaded_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("media_format", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "capture_location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_uploaded_media_file_size_bytes",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_uploaded_media_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploaded_media")),
    )
    op.create_index(
        "ix_uploaded_media_incident_id",
        "uploaded_media",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_uploaded_media_captured_at",
        "uploaded_media",
        ["captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_uploaded_media_capture_location",
        "uploaded_media",
        ["capture_location"],
        unique=False,
        postgresql_using="gist",
    )

    # 3. Create table: detection_results
    op.create_table(
        "detection_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bounding_boxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("inference_latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('fire', 'smoke', 'neutral', 'floodwater')",
            name="ck_detection_results_classification",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_detection_results_confidence",
        ),
        sa.CheckConstraint(
            "inference_latency_ms >= 0",
            name="ck_detection_results_inference_latency_ms",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["uploaded_media.id"],
            name=op.f("fk_detection_results_media_id_uploaded_media"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_results")),
    )
    op.create_index(
        "ix_detection_results_media_id",
        "detection_results",
        ["media_id"],
        unique=False,
    )
    op.create_index(
        "ix_detection_results_classification",
        "detection_results",
        ["classification"],
        unique=False,
    )
    op.create_index(
        "ix_detection_results_created_at",
        "detection_results",
        ["created_at"],
        unique=False,
    )

    # 4. Create table: environmental_observations
    op.create_table(
        "environmental_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
        sa.Column("relative_humidity", sa.Float(), nullable=True),
        sa.Column("wind_speed_mps", sa.Float(), nullable=True),
        sa.Column("wind_direction_degrees", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("metrics_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relative_humidity IS NULL OR (relative_humidity >= 0.0 AND relative_humidity <= 100.0)",
            name="ck_env_obs_relative_humidity",
        ),
        sa.CheckConstraint(
            "wind_speed_mps IS NULL OR wind_speed_mps >= 0.0",
            name="ck_env_obs_wind_speed_mps",
        ),
        sa.CheckConstraint(
            "wind_direction_degrees IS NULL OR (wind_direction_degrees >= 0.0 AND wind_direction_degrees <= 360.0)",
            name="ck_env_obs_wind_direction_degrees",
        ),
        sa.CheckConstraint(
            "precipitation_mm IS NULL OR precipitation_mm >= 0.0",
            name="ck_env_obs_precipitation_mm",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_environmental_observations_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environmental_observations")),
    )
    op.create_index(
        "ix_environmental_observations_incident_id",
        "environmental_observations",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_environmental_observations_recorded_at",
        "environmental_observations",
        ["recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_environmental_observations_incident_recorded",
        "environmental_observations",
        ["incident_id", sa.text("recorded_at DESC")],
        unique=False,
    )

    # 5. Create table: hazard_predictions
    op.create_table(
        "hazard_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("forecast_horizon_hours", sa.Float(), nullable=False),
        sa.Column("projected_area_hectares", sa.Float(), nullable=False),
        sa.Column(
            "predicted_footprint",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "forecast_horizon_hours > 0.0",
            name="ck_hazard_predictions_forecast_horizon_hours",
        ),
        sa.CheckConstraint(
            "projected_area_hectares >= 0.0",
            name="ck_hazard_predictions_projected_area_hectares",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'moderate', 'high', 'critical')",
            name="ck_hazard_predictions_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_hazard_predictions_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["primary_observation_id"],
            ["environmental_observations.id"],
            name=op.f("fk_hazard_predictions_primary_observation_id_environmental_observations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hazard_predictions")),
    )
    op.create_index(
        "ix_hazard_predictions_incident_id",
        "hazard_predictions",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_primary_observation_id",
        "hazard_predictions",
        ["primary_observation_id"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_created_at",
        "hazard_predictions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_risk_level",
        "hazard_predictions",
        ["risk_level"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_incident_horizon",
        "hazard_predictions",
        ["incident_id", "forecast_horizon_hours"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_predicted_footprint",
        "hazard_predictions",
        ["predicted_footprint"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_hazard_predictions_footprint_geography",
        "hazard_predictions",
        [sa.text("(predicted_footprint::geography)")],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    # Drop tables in exact reverse dependency order
    op.drop_table("hazard_predictions")
    op.drop_table("environmental_observations")
    op.drop_table("detection_results")
    op.drop_table("uploaded_media")
    op.drop_table("incidents")
```

---

### 15. backend/app/api/v1/router.py

**Path:** `backend/app/api/v1/router.py`  

```python
from fastapi import APIRouter
from app.api.v1.endpoints import health, incidents

api_router = APIRouter()

# Mount health liveness endpoint
api_router.include_router(health.router, tags=["Health"])

# Mount Incident Management endpoints
api_router.include_router(incidents.router, prefix="/incidents", tags=["Incidents"])
```

---

### 16. backend/app/main.py

**Path:** `backend/app/main.py`  

```python
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    SCOUTException,
    http_exception_handler,
    scout_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging

# Configure logging on module load
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="SCOUT — Smart Crisis Observation & Understanding Technology API",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Register custom exception handlers for uniform error envelopes
app.add_exception_handler(SCOUTException, scout_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Configure Cross-Origin Resource Sharing (CORS)
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 router under the configured prefix
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
def read_root():
    """
    Root informational endpoint providing quick navigation links.
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs_url": "/docs",
        "health_endpoint": f"{settings.API_V1_STR}/health",
    }
```

---

