# SCOUT Milestone 09 — Pre-Implementation Workspace Audit Report

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Milestone:** Milestone 09 — Environmental Data Integration  
**Stage:** Stage 1 — Workspace Audit and Architecture Reconciliation  
**Date:** October 31, 2026  
**Auditor:** Senior Software Architect, Backend Engineer & Scientific Computing Engineer  

---

## 1. Executive Summary

In accordance with Section 2 of the Milestone 09 Master Engineering Prompt, a comprehensive pre-implementation audit of the `SCOUT` repository was conducted at `C:\Users\TANOOJ\OneDrive\Desktop\SCOUT`. 

The purpose of this audit is to baseline the existing architecture, inspect the actual source code, verify database constraints and relationships, confirm test suite health, and record the exact working tree state before creating any new environmental subsystem components.

### Core Audit Baseline:
- **Backend Architecture:** FastAPI modular monolith under `backend/app/` with clean separation between API routers, domain logic, database models, schemas, and services.
- **Database Schema:** Synchronous SQLAlchemy 2.0 with PostgreSQL/PostGIS. Initial migration `20261030_0001_initial_schema.py` establishes five core tables (`incidents`, `uploaded_media`, `detection_results`, `environmental_observations`, `hazard_predictions`).
- **Critical Architectural Invariant:** `environmental_observations.incident_id` is currently non-nullable (`nullable=False`), and the table lacks independent spatial coordinates. To support live and historical environmental retrieval independent of active incidents, while allowing shared observations across multiple incidents, an Alembic migration is required in Stage 4 to make `incident_id` nullable, add provider-resolved spatial attributes, introduce an `incident_environmental_observations` association table, and apply partial unique indexes.
- **Geospatial Compatibility (M08):** Coordinate validation, dynamic local UTM metric buffering, geodesic distance math (`pyproj.Geod`), and exposure analysis are operational under `backend/app/geospatial/`.
- **Git State:** Single commit foundation `65f8933` (*"chore: initialize SCOUT project foundation"*). Nine tracked modified files preserve previous milestones (M05–M08) under strict "no commit" directives. Zero application code has been modified for Milestone 09 yet.

---

## 2. Directory Structure and Entry Points

### 2.1 Backend Layout
```
backend/
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 20261030_0001_initial_schema.py
├── app/
│   ├── __init__.py
│   ├── main.py                          <-- FastAPI entry point; mounts CORS, exceptions, API router, dashboard
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── router.py                <-- Mounts health, incidents, media, geospatial routers
│   │       └── endpoints/
│   │           ├── health.py
│   │           ├── incidents.py
│   │           ├── media.py
│   │           └── geospatial.py
│   ├── core/
│   │   ├── config.py                    <-- Centralized Pydantic settings with .env loading
│   │   ├── exceptions.py                <-- SCOUTException hierarchy and uniform error handlers
│   │   ├── logging.py                   <-- Logging configuration
│   │   └── storage.py                   <-- Upload staging and permanent media storage manager
│   ├── db/
│   │   └── session.py                   <-- Engine instantiation, SessionLocal, get_db dependency
│   ├── geospatial/                      <-- M08 Geospatial Intelligence Engine
│   │   ├── coordinates.py               <-- WGS 84 validation, geodesic math, UTM zones
│   │   ├── geometry.py                  <-- Shapely 2.0 geometry models, metric UTM buffers
│   │   ├── spatial_queries.py           <-- PostGIS ST_DWithin and geography queries
│   │   ├── context.py                   <-- GeographicContextCatalog and layer availability
│   │   ├── exposure.py                  <-- ExposureEngine and proximity calculation
│   │   ├── risk.py                      <-- Disaster-specific risk assessors
│   │   └── schemas.py                   <-- Geospatial Pydantic schemas
│   ├── models/                          <-- SQLAlchemy 2.0 declarative models
│   │   ├── base.py                      <-- Base DeclarativeBase
│   │   ├── incident.py                  <-- Incident model (location, perimeter, status)
│   │   ├── uploaded_media.py            <-- UploadedMedia model
│   │   ├── detection_result.py          <-- DetectionResult model (M07 predictions)
│   │   ├── environmental_observation.py <-- EnvironmentalObservation model
│   │   └── hazard_prediction.py         <-- HazardPrediction model (references observations)
│   ├── schemas/                         <-- Pydantic request/response schemas
│   │   ├── common.py                    <-- Pagination, ErrorDetail, ErrorResponse
│   │   ├── incident.py                  <-- Incident schemas
│   │   └── media.py                     <-- Media schemas
│   └── services/                        <-- Service business logic layer
│       ├── geospatial_service.py        <-- Geospatial orchestration
│       ├── incident_service.py          <-- Incident lifecycle
│       └── media_service.py             <-- Media upload pipeline
└── tests/
    ├── conftest.py                      <-- Pytest fixtures (client, db_session, db_client)
    ├── integration/                     <-- API and DB integration tests
    └── unit/                            <-- Fast isolated unit tests (124 tests passing)
```

---

## 3. Configuration & Dependency Inspection

### 3.1 Existing Configuration (`backend/app/core/config.py`)
- Powered by `pydantic-settings.BaseSettings`.
- Discovers `.env` at project root or `backend/.env`.
- Database parameters: `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, with connection pooling configuration (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_PRE_PING`).
- Storage parameters: `STORAGE_DIR`, `MAX_UPLOAD_SIZE_BYTES`.
- Geospatial parameters: `GEOSPATIAL_PRIORITY_THRESHOLD_METERS: float = 1000.0`.
- Typed connection string generation: `SQLALCHEMY_DATABASE_URI` via `sqlalchemy.URL.create()`.

### 3.2 Installed Dependencies (`backend/requirements.txt`)
- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.32.0`
- `pydantic>=2.9.0`
- `pydantic-settings>=2.6.0`
- `python-dotenv>=1.0.0`
- `pytest>=8.3.0`
- `httpx>=0.27.0` (v0.28.1 installed in `.venv`)
- `psycopg2-binary>=2.9.9`
- `SQLAlchemy>=2.0.35,<2.1`
- `GeoAlchemy2>=0.15.2`
- `alembic>=1.13.3`
- `python-multipart>=0.0.20`
- `Pillow>=10.0.0`
- `shapely>=2.0.0`
- `pyproj>=3.6.0`

---

## 4. Existing Database Models & Migrations

### 4.1 Initial Schema Migration (`20261030_0001_initial_schema.py`)
- Establishes `incidents`, `uploaded_media`, `detection_results`, `environmental_observations`, and `hazard_predictions`.
- `environmental_observations` table definition:
  ```python
  sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
  sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),  # <-- To be made nullable
  sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
  sa.Column("source", sa.String(length=64), nullable=False),
  sa.Column("temperature_celsius", sa.Float(), nullable=True),
  sa.Column("relative_humidity", sa.Float(), nullable=True),
  sa.Column("wind_speed_mps", sa.Float(), nullable=True),
  sa.Column("wind_direction_degrees", sa.Float(), nullable=True),
  sa.Column("precipitation_mm", sa.Float(), nullable=True),
  sa.Column("metrics_payload", postgresql.JSONB(), nullable=False),
  sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
  sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="RESTRICT")
  ```
- `hazard_predictions` table relationship:
  ```python
  sa.Column("primary_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
  sa.ForeignKeyConstraint(["primary_observation_id"], ["environmental_observations.id"], ondelete="RESTRICT")
  ```

### 4.2 Migration Strategy for Milestone 09:
To support non-incident environmental queries, multi-incident observation sharing, and strict spatial-temporal deduplication without breaking foreign keys:
1. Make `environmental_observations.incident_id` nullable (`nullable=True`).
2. Add location identity and spatial attributes:
   - `location_type`: String(32) discriminator (`station`, `grid`, `incident`, `point`).
   - `location_id`: String(128) canonical namespaced identifier.
   - `requested_latitude`: Float (nullable).
   - `requested_longitude`: Float (nullable).
   - `resolved_latitude`: Float (nullable).
   - `resolved_longitude`: Float (nullable).
   - `location`: Geometry(Point, 4326) spatial column.
3. Add provenance, temporal, and classification attributes:
   - `typology`: String(32) (`station_observed`, `model_analysis`, `reanalysis`, `forecast`, `derived`).
   - `init_time_utc`: DateTime(timezone=True) (nullable).
   - `lead_time_hours`: Float (nullable).
   - `surface_pressure_hpa`: Float (nullable).
   - `algorithm_name`: String(64) (nullable).
   - `algorithm_version`: String(32) (nullable).
   - `source_fingerprint`: String(64) (nullable).
   - `retrieved_at_utc`: DateTime(timezone=True) (nullable).
4. Create association table `incident_environmental_observations`:
   - `id`: UUID primary key.
   - `incident_id`: UUID FK -> `incidents.id` (`ondelete="CASCADE"`).
   - `observation_id`: UUID FK -> `environmental_observations.id` (`ondelete="RESTRICT"`).
   - `association_type`: String(32) (e.g. `primary`, `concurrent`, `pre_event`, `forecast`).
   - `created_at`: DateTime(timezone=True).
   - Unique constraint: `UNIQUE (incident_id, observation_id, association_type)`.
5. Create PostgreSQL Partial Unique Indexes (`uq_env_obs_ground_and_reanalysis`, `uq_env_obs_model_analysis`, `uq_env_obs_forecast`, `uq_env_obs_derived`).

---

## 5. Geospatial Integration Baseline (M08)

Milestone 08 delivered:
- `validate_coordinates()`: Validates coordinates in $[-90, 90]$ and $[-180, 180]$, rejecting non-finite IEEE-754 numbers.
- `geodesic_distance_meters()`: Ellipsoidal Karney geodesic distance calculation using `pyproj.Geod` with Haversine fallback.
- `create_metric_buffer_polygon()`: Planar Euclidean buffering inside auto-resolved local UTM projection zones.
- `GeographicContextCatalog`: In-memory spatial catalog tracking features and layer indicators.
- `ExposureEngine`: Aggregates category counts, closest feature distances, and operational high-priority exposed features ($d \le 1,000\text{m}$).

Milestone 09 will integrate with M08 by correlating environmental wind vectors (speed and azimuth) with exposed assets downwind of active incidents.

---

## 6. Git Status & Safety Verification

```
$ git status --short
 M .env.example
 M .gitignore
 M README.md
 M backend/app/api/v1/router.py
 M backend/app/core/config.py
 M backend/app/main.py
 M backend/requirements.txt
 M backend/tests/conftest.py
 M backend/tests/unit/test_config.py
?? docs/reports/milestone_09_pre_implementation_audit.md
```

### Safety Confirmations:
- No commits or pushes will be performed.
- No files will be reverted or reset.
- All pre-existing user modifications from M05–M08 are preserved.
- Historical ML checkpoints, training datasets, and reports remain 100% untouched.

---

## 7. Implementation Execution Roadmap (Stages 2–10)

1. **Stage 2: Provider Clients** (`backend/app/environmental/providers/`):
   - `base.py`: Abstract `BaseWeatherProvider` and typed payload classes.
   - `open_meteo.py`: Open-Meteo client (current nowcast, historical reanalysis, forecast).
   - `nasa_power.py`: NASA POWER client (hourly & daily point requests, explicit `time-standard=UTC`).
   - Mocked provider unit tests (`backend/tests/unit/environmental/test_providers.py`).
2. **Stage 3: Canonical Schemas & Normalization** (`backend/app/environmental/`):
   - `schemas.py`: Canonical Pydantic v2 models (`CanonicalWeatherVariables`, `ModelRunProvenance`, `EnvironmentalObservationItem`).
   - `normalizer.py`: SI unit conversions (°C, m/s, mm, hPa), range checks, typology tagging.
   - Normalizer unit tests (`backend/tests/unit/environmental/test_normalizer.py`).
3. **Stage 4: Database Evolution & Migrations** (`backend/app/models/`, `backend/alembic/`):
   - Alembic migration `20261031_0002_environmental_observations_upgrade.py`.
   - Update `EnvironmentalObservation` model and add `IncidentEnvironmentalObservation` association model.
   - Partial unique indexes for deduplication.
4. **Stage 5: Ingestion & Repository Services** (`backend/app/environmental/`):
   - `repository.py`: Idempotent upserts and spatial-temporal queries.
   - `ingestion.py`: End-to-end ingestion lifecycle coordinator.
5. **Stage 6: Reliability & Caching** (`backend/app/environmental/`):
   - `cache.py`: In-memory TTL cache with namespaced compound keys and stale fallback.
   - Client retry policies with exponential backoff and timeout handling.
6. **Stage 7: FWI Subsystem** (`backend/app/environmental/fwi/`):
   - Canadian Forest Fire Weather Index (Van Wagner 1985 / 1987).
   - Component equations: FFMC, DMC, DC, ISI, BUI, FWI.
   - 49-day benchmark test vector verification (FTR 33 Appendix 2).
7. **Stage 8: FastAPI Integration** (`backend/app/api/v1/endpoints/environmental.py`):
   - REST endpoints: `/health`, `/current`, `/historical`, `/forecast`, `/ingest`, `/observations`, `/fwi/calculate`.
   - Mount in `api_router`.
8. **Stage 9: Geospatial Integration**:
   - Helper correlating wind vectors with M08 exposed assets downwind.
9. **Stage 10: Full Verification & Final Documentation**:
   - Execute all unit, integration, and regression suites.
   - Perform limited live provider connectivity check.
   - Final completion report (`docs/reports/milestone_09_implementation_report.md`).
