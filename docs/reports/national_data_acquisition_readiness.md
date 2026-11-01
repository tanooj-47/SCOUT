# SCOUT — National Geographic Data Acquisition Readiness Report
## India-Wide Real-World Dataset Integration (Milestone 10 Phase A)

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Subsystem:** National Geographic Data Acquisition Architecture  
**Role:** Senior Geospatial Data Engineer, GIS Specialist & Data Acquisition Architect  
**Date:** 2026-10-31  
**Workspace:** `C:\Users\TANOOJ\OneDrive\Desktop\SCOUT`  
**Phase:** Phase A — Mandatory Workspace & Source Audit  
**Status:** Readiness Complete / Pre-Acquisition Authorization  

---

## 1. Executive Summary & National Scope

SCOUT has successfully completed Milestones 07 (Wildfire Computer Vision), 08 (Geospatial Intelligence Engine), 09 (Environmental Data Integration), and 10 (Persistent Geospatial Data Integration). Milestone 10 established PostgreSQL/PostGIS persistence, bounded batch ingestion, topological exposure calculations, and disaster-specific risk assessors, but operated on an engineering calibration test fixture (`calibration_dehradun_features.geojson`).

We now transition from localized calibration fixtures to **National Geographic Data Acquisition** covering the entire sovereign territory of India across all 28 States and 8 Union Territories.

### Core Objectives
1. **Authentic, Traceable National Data:** Acquire official, authoritative, and geographically valid datasets covering administrative boundaries, transport lifelines, healthcare facilities, emergency infrastructure, settlements, waterways, forest/vegetation cover, land cover, population density, elevation/terrain, flood hazard zones, active fire observations, and historical meteorology.
2. **Explicit Provenance & Rigorous Governance:** Maintain full license compliance (ODbL 1.0, CC BY 4.0, Open Government Data, NASA Data Terms) with immutable audit manifests tracking origin URLs, publication dates, acquisition timestamps, file checksums (SHA-256), and operational restrictions.
3. **No Synthetic Shortcuts:** Prohibit fabricated features, idealized bounding boxes, or arbitrary city/district substitutions for national scope. Where national coverage is incomplete or access is gated by government registration, document the exact state of availability and user acquisition procedures honestly.

---

## 2. Mandatory Workspace Audit

### 2.1 Operating Environment & Hardware Constraints
An exhaustive inspection of the runtime environment was conducted:

| Environment Property | Value / Status | Architectural Impact |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 Enterprise (Build 10.0.26200-SP0) | Shell execution via PowerShell; standard path length and newline semantics. |
| **Python Runtime** | Python 3.14.7 (MSC v.1944 64-bit AMD64) | Active virtual environment at `.venv\Scripts\python.exe`. |
| **Total Disk Space** | 250.21 GB (Drive C:) | Total partition capacity. |
| **Used Disk Space** | 215.25 GB | Pre-existing OS, software, models, and datasets. |
| **Available Disk Space** | **34.96 GB** | **Crucial Invariant:** National dataset acquisition, temporary staging, and extracted layers must operate strictly within a disciplined storage budget (< 10 GB). |

### 2.2 Geospatial Dependency Census
Inspection of installed Python modules against acquisition and processing requirements:

| Library / Tool | Version | Status | Technical Role & Feasibility |
| :--- | :---: | :---: | :--- |
| **`shapely`** | `2.2.0` | **INSTALLED** | Core computational geometry: point-in-polygon, metric buffers, planar intersection, WKT/GeoJSON serialization, and `make_valid` topological repairs. |
| **`pyproj`** | `3.8.0` | **INSTALLED** | Geodetic coordinate transformations (EPSG:4326 to UTM zones, Web Mercator, and regional projected coordinate systems). |
| **`geoalchemy2`** | `0.20.0` | **INSTALLED** | Spatial ORM column mappings and PostGIS SQL generation. |
| **`sqlalchemy`** | `2.0.55` | **INSTALLED** | Relational queries, batch commits, and schema management. |
| **`fastapi`** | `0.162.0` | **INSTALLED** | Core REST API services. |
| **`httpx`** | `0.28.1` | **INSTALLED** | High-performance asynchronous and synchronous HTTP/HTTPS client with streaming support. |
| **`Pillow`** | `12.1.1` | **INSTALLED** | Image decoding and basic raster handling (TIFF, PNG, JPEG). |
| **`numpy`** | `2.5.4` | **INSTALLED** | Numerical array processing and raster matrix operations. |
| **`gdal` / `osgeo`** | None | **NOT INSTALLED** | C-extension GIS library. No official precompiled wheels for Python 3.14 on Windows currently on PyPI. |
| **`rasterio`** | None | **NOT INSTALLED** | Depends on GDAL C-libraries; not installed. Raster inspection must use pure-Python TIFF/COG chunk readers or Pillow + NumPy. |
| **`geopandas`** | None | **NOT INSTALLED** | Spatial dataframe wrapper; pure Shapely + JSON/GeoJSON processing used across SCOUT. |
| **`pyogrio` / `pyarrow`** | None | **NOT INSTALLED** | Fast OGR/Parquet bindings; not available in Python 3.14 on Windows. |
| **`osmium` (PyOsmium)** | None | **NOT INSTALLED** | C++ Osmium parser bindings; not installed for Python 3.14. PBF processing strategy detailed in Section 5. |

### 2.3 Database & PostGIS Accessibility Audit
- **Database Engine:** PostgreSQL 16 + PostGIS 3.4 specified in configuration.
- **Connection Endpoint:** `postgresql+psycopg2://scout_admin:***@127.0.0.1:5432/scout`.
- **Runtime Accessibility:** The local PostgreSQL service is currently offline/unreachable in the host environment (`psycopg2.OperationalError: connection to 127.0.0.1:5432 failed: Permission denied`).
- **Architectural Policy:** In accordance with M10 guidelines, all data schemas, validation scripts, and vector transformations will execute and validate offline using SQLite and mock PostGIS dialects. Ingestion into persistent tables will be reported strictly as `NOT VERIFIED (infrastructure dependent)` until a live containerized PostgreSQL daemon is active.

### 2.4 Existing Codebase & Directory Structure
1. **Existing M10 Components:**
   - Ingestion CLI: [`backend/app/geospatial/ingestion/cli.py`](../../backend/app/geospatial/ingestion/cli.py)
   - Normalizer: [`backend/app/geospatial/ingestion/normalizer.py`](../../backend/app/geospatial/ingestion/normalizer.py)
   - Pipeline: [`backend/app/geospatial/ingestion/pipeline.py`](../../backend/app/geospatial/ingestion/pipeline.py)
   - Database Models: [`backend/app/models/geospatial.py`](../../backend/app/models/geospatial.py)
   - Service Layer: [`backend/app/services/geospatial_service.py`](../../backend/app/services/geospatial_service.py)
2. **Existing Data Hierarchy:**
   - `data/geospatial/calibration_dehradun_features.geojson` (Synthetic calibration test fixture, preserved).
   - `data/external/fire_smoke_sources/` (BoWFire and D-Fire vision datasets, preserved).
   - `data/processed/fire_smoke_v1/` and `fire_smoke_v2/` (CV training/eval datasets, preserved).
   - `data/raw/` (Only `.gitkeep`, available for expansion).
3. **Preservation Status:**
   - 6 ML checkpoints (`baseline_cnn` and `mobilenet_v3_small` stages) 100% verified.
   - 4 historical reports 100% verified.
   - 2,936 v1 dataset files 100% verified.
   - Zero Git commits, pushes, resets, or stashes.

---

## 3. Approved Data Sources — Detailed Evaluation

### Source A: OpenStreetMap via Geofabrik (National Vector Base)
- **Official Portal:** `https://download.geofabrik.de/asia/india.html`
- **Primary Download URL:** `https://download.geofabrik.de/asia/india-latest.osm.pbf`
- **Checksum URL:** `https://download.geofabrik.de/asia/india-latest.osm.pbf.md5`
- **File Format:** OSM Protocolbuffer Binary Format (`.osm.pbf`).
- **File Size:** ~1.6 GB compressed (updated daily).
- **Extracted Footprint:** ~2.5–3.5 GB once filtered into thematic vector layers.
- **License & Terms:** Open Database License (ODbL 1.0). Attribution required: `"Data © OpenStreetMap contributors, ODbL 1.0"`.
- **Target Thematic Layers:**
  1. `roads`: Primary, secondary, tertiary, motorways, bridges, tunnels, evacuation corridors.
  2. `railways`: Rail lines, stations, halts.
  3. `hospitals`: Hospitals, emergency wards, clinics, trauma centers.
  4. `fire_stations`: Fire stations, emergency rescue dispatch centers.
  5. `emergency_facilities`: Police stations, community storm/flood shelters, disaster response centers.
  6. `settlements`: Towns, villages, urban residential areas.
  7. `water_bodies`: Rivers, canals, streams, lakes, reservoirs, wetlands.
  8. `forests`: Forest reserves, woodlands, vegetative fuel zones.
- **Acquisition Strategy:** Download `india-latest.osm.pbf` **exactly once** using resumable streaming with MD5 and SHA-256 checksum verification. Derive all target thematic layers sequentially from the single source file without redundant network requests.

### Source B: Survey of India (Official Administrative Boundaries)
- **Official Portals:**
  - `https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-`
  - `https://surveyofindia.gov.in/pages/village-boundary-data-base-of-entire-india`
  - `https://onlinemaps.surveyofindia.gov.in/`
- **Product Description:** Administrative Boundary Database (ABDB) covering State/UT, District, Subdistrict (Tehsil/Taluk), and Village boundaries.
- **Access Conditions & Constraints:**
  - Requires user account registration on `onlinemaps.surveyofindia.gov.in` with Indian mobile OTP and identity verification.
  - Usage governed by the National Geospatial Policy (NGP) and India Geospatial Data Guidelines.
  - Explicit agreement prohibiting the sharing or transmission of sensitive geospatial boundaries to foreign individuals or foreign entities.
- **Readiness Verdict:** **`RESTRICTED ACCESS (USER ACTION REQUIRED)`**.
  - In accordance with project instructions, automated public acquisition without user credentials is not permitted.
  - *Mitigation:* Document official download procedures for Indian domestic deployments. For open development and regression testing, use authentic OSM-derived national and state administrative boundaries (ODbL 1.0) and Datameet India community administrative boundaries (CC BY 4.0), recording exact provenance.

### Source C: ESA WorldCover (10m Land Cover / Land Use Raster)
- **Official Portal:** `https://esa-worldcover.org/en/data-access`
- **Primary Repository:** AWS Open Data Registry (`s3://esa-worldcover/v200/2021/map/` or direct HTTPS `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/`).
- **Product:** ESA WorldCover 2021 v200 (10m spatial resolution).
- **Tile Architecture:** $3^\circ \times 3^\circ$ Cloud-Optimized GeoTIFFs (COGs) referenced by lower-left coordinate (e.g. `ESA_WorldCover_10m_2021_v200_N24E078_Map.tif`).
- **License & Terms:** Creative Commons Attribution 4.0 International (CC BY 4.0). Attribution: `"© ESA WorldCover project 2021 / contains modified Copernicus Sentinel data"`.
- **Classes:** Tree cover (10), Shrubland (20), Grassland (30), Cropland (40), Built-up (50), Bare/sparse vegetation (60), Snow and ice (70), Permanent water bodies (80), Herbaceous wetland (90), Mangroves (95), Moss and lichen (100).
- **Storage & Acquisition Strategy:** India is covered by approximately 52 tiles. Total uncompressed size exceeds 12 GB.
  - To respect the 34.96 GB disk budget, we establish a **National Tile Index Manifest** cataloging all 52 India-intersecting tiles, and download an initial representative transect of high-hazard regional tiles (Himalayan wildfire/flood zone, Indo-Gangetic basin, Coastal cyclone zone).

### Source D: GHSL — Global Human Settlement Layer (Population & Built-Up Surface)
- **Official Portal:** `https://human-settlement.emergency.copernicus.eu/`
- **Direct Repository:** European Commission JRC Open Data (`https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/`).
- **Products Evaluated:**
  - `GHS-POP` (Global Population Grid, Epoch 2020 / 2025, 100m and 1km resolutions, World Mollweide `54009` and WGS84 `4326`).
  - `GHS-BUILT-S` (Built-up Surface Grid, Epoch 2020, 100m resolution).
- **License & Terms:** Creative Commons Attribution 4.0 (CC BY 4.0). Attribution: `"European Commission, Joint Research Centre (JRC)"`.
- **Storage & Acquisition Strategy:** Global 100m rasters exceed 8 GB per epoch. We acquire the 1km national grid and targeted 100m regional tiles for India, ensuring population counts represent resident density rather than real-time disaster census.

### Source E: Copernicus DEM (Digital Surface Model & Elevation)
- **Official Portal:** `https://dataspace.copernicus.eu/`
- **Cloud Access:** AWS Open Data Registry (`s3://copernicus-dem-30m/`) or Microsoft Planetary Computer STAC (`cop-dem-glo-30`).
- **Product:** Copernicus DEM GLO-30 (30m spatial resolution Digital Surface Model, WGS84 EGM96).
- **Tile Architecture:** $1^\circ \times 1^\circ$ COGs (e.g. `Copernicus_DSM_COG_10_N24_00_E078_00_DEM`).
- **License & Terms:** Open Access under Copernicus Data Policy. Attribution: `"© DLR e.V. and © Airbus Defence and Space GmbH (Copernicus DEM)"`.
- **Scientific Caveat:** GLO-30 is a Digital Surface Model (includes canopy and building tops), not a bare-earth Digital Terrain Model (DTM). Terrain slope calculations must record this distinction.
- **Storage Strategy:** India requires >300 $1^\circ \times 1^\circ$ tiles. We index the complete national tile grid and acquire representative tiles over critical flood basins and mountainous wildfire corridors.

### Source F: ISRO Bhuvan (National Flood & Thematic Services)
- **Official Portal:** `https://bhuvan.nrsc.gov.in/`
- **Web Services:** OGC WMS/WMTS endpoints (`https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms`, `https://bhuvan-ras2.nrsc.gov.in/cgi-bin/hazard.exe`).
- **Products:** Historical flood inundation maps (annual maximum flood envelopes), Land Use/Land Cover (LULC 1:50,000), and water bodies.
- **Usage Conditions & Limitations:**
  - WMS endpoints provide raster visualization overlays (`image/png`), not raw downloadable vector GIS geometries.
  - Automated bulk scraping is prohibited.
  - Disclaimers explicitly specify that near-real-time inundation boundaries are satellite-derived approximations subject to cloud cover gaps.
- **Readiness Verdict:** **`SERVICE MAPPED / DOCUMENTED`**. WMS service capabilities, layer identifiers, and attribution requirements cataloged for runtime dashboard consumption.

### Source G: Historical Weather & Environmental Reanalysis (Open-Meteo ERA5)
- **Official Portal:** `https://open-meteo.com/en/docs/historical-weather-api`
- **Products:** ECMWF ERA5 and ERA5-Land reanalysis.
- **Parameters:** 2m temperature, relative humidity, precipitation, 10m wind speed & direction, surface pressure.
- **Subsystem Reuse:** Completely integrates with SCOUT's existing M09 Environmental Subsystem ([`backend/app/environmental/`](../../backend/app/environmental/)). Reuses M09 caching, rate limiting, and Canadian FWI mathematical engine.
- **Strategy:** Bounded regional grids across Indian climatic zones (Himalayan, Indo-Gangetic, Western Ghats, Coastal, Deccan Plateau) to prevent unbounded storage expansion.

### Source H: NASA FIRMS (Satellite Active Fire Observations)
- **Official Portal:** `https://firms.modaps.eosdis.nasa.gov/`
- **API Endpoint:** `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}`.
- **Sensors:** MODIS (Terra/Aqua 1km), VIIRS (Suomi-NPP 375m, NOAA-20 375m, NOAA-21 375m).
- **Bounding Box for India:** `68.1, 6.5, 97.4, 35.5` (min_lon, min_lat, max_lon, max_lat).
- **Authentication:** Requires `NASA_FIRMS_MAP_KEY` configured in `.env` (free registration).
- **Scientific Caveat:** Satellite fire detections represent thermal anomalies (FRP in MW, brightness temp), not ground-confirmed wildfire incidents. Distinct from SCOUT's M07 computer vision classifier.

---

## 4. National Coordinate Systems & Spatial Processing Strategy

India spans $68.1^\circ\text{E}$ to $97.4^\circ\text{E}$ longitude and $6.5^\circ\text{N}$ to $35.5^\circ\text{N}$ latitude, traversing UTM zones 42N, 43N, 44N, 45N, 46N, and 47N.

```mermaid
flowchart TD
    Raw[Raw Ingested Data] --> Norm[Coordinate Normalization]
    Norm --> Storage[EPSG:4326 Storage & Interchange]
    Storage --> Geodesic[Geodesic Calculations ST_Distance / ST_DWithin on Geography]
    Storage --> Projected[Local UTM Projection via pyproj / PostGIS]
    Projected --> Metrics[Metric Distance & Area Calculations]
```

### Key Principles
1. **Interchange & Persistence:** WGS84 (`EPSG:4326`) is the canonical storage and interchange standard.
2. **Metric Operations:** Distance and area operations must **never** be computed directly in degrees. PostGIS calculations must cast to `GEOGRAPHY` (ellipsoidal distance on WGS84 spheroid), and offline Python calculations must use `pyproj` local UTM transformations or Haversine/Vincenty geodesic formulas.
3. **Geometry Validation:** Every vector feature must pass topological verification (`shapely.is_valid`). Self-intersecting rings must be repaired using `shapely.make_valid()`. Coordinate boundaries must strictly fall within valid geographic bounds ($[-180, 180]$, $[-90, 90]$).

---

## 5. Storage Budget & Capacity Planning

With **34.96 GB** of free disk space, disciplined storage allocation is mandatory:

| Subsystem / Data Category | Expected Raw Size | Processed / Extracted Size | Projected Total | Safety Margin Remaining |
| :--- | :---: | :---: | :---: | :---: |
| **OSM India PBF (`india-latest.osm.pbf`)** | 1.6 GB | 2.5 GB (Thematic GeoJSON/GPKG) | 4.1 GB | ~30.8 GB |
| **ESA WorldCover (Representative Tiles)** | 1.2 GB | 0.0 GB (Native COG retained) | 1.2 GB | ~29.6 GB |
| **GHSL Population (India Sub-grids)** | 0.8 GB | 0.2 GB (Extracted GeoTIFF) | 1.0 GB | ~28.6 GB |
| **Copernicus DEM (Representative Basins)**| 1.0 GB | 0.2 GB (Derived Slope/Aspect) | 1.2 GB | ~27.4 GB |
| **NASA FIRMS & Weather Observations** | 0.2 GB | 0.1 GB (Normalized JSON/CSV) | 0.3 GB | ~27.1 GB |
| **Temporary Staging & Pipeline Buffer** | 2.0 GB | 0.0 GB (Transient `.part` files) | 2.0 GB | ~25.1 GB |
| **Total Projected Allocation** | **6.8 GB** | **3.0 GB** | **9.8 GB** | **>25.0 GB Buffer** |

**Storage Enforcement Invariants:**
- Every download script must execute a pre-flight disk check: require `free_space > expected_size * 2.5`.
- Large archive downloads must utilize temporary `.part` files and rename atomically upon SHA-256 verification.
- Virtual rasters (VRT) and Cloud-Optimized GeoTIFFs (COG) must be favored over massive uncompressed TIFF duplicates.

---

## 6. Technical Risks & Mitigation Strategies

| # | Identified Risk | Severity | Mitigation Strategy |
|---|---|---|---|
| 1 | **Missing C-GIS Libraries (`gdal`, `rasterio`, `pyosmium`) on Python 3.14 Windows** | HIGH | Implement pure-Python / Shapely / GeoAlchemy2 streaming parsers for vector and metadata inspection. Structure raster handlers using Pillow, NumPy, and direct COG chunk readers. |
| 2 | **Network Disconnections during 1.6 GB PBF Download** | HIGH | Implement HTTP Range-based resumable downloads with exponential backoff and chunk validation. |
| 3 | **Survey of India Login / OTP Restriction** | MEDIUM | Fully document the restricted status and acquisition workflow in catalog. Use verified ODbL OSM boundaries and open Datameet boundaries for offline testing. |
| 4 | **Disk Space Exhaustion on India-Wide Raster Mosaics** | HIGH | Prohibit nationwide full-resolution raster mosaics. Maintain a national tile index manifest and download prioritized representative tiles. |
| 5 | **Local PostgreSQL/PostGIS Unavailability** | MEDIUM | Execute validation offline. Do not claim persistent live database persistence until Docker daemon is verified. |

---

## 7. Recommended Acquisition Sequence (Phased Roadmap)

```mermaid
flowchart LR
    PhaseB[Phase B: Acquisition Framework] --> PhaseC[Phase C: Initial Real Acquisition]
    PhaseC --> PhaseD[Phase D: Vector Extraction]
    PhaseD --> PhaseE[Phase E: Raster Inventory]
    PhaseE --> PhaseF[Phase F: Observations & Weather]
    PhaseF --> PhaseG[Phase G: Pipeline Integration]
    PhaseG --> PhaseH[Phase H: Validation & Catalog]
```

1. **Phase B (Framework):** Implement directory structure (`data/raw/geospatial/`, `data/processed/geospatial/`, `data/manifests/geospatial/`), reusable download utility with resumable chunks and SHA-256 hashing, dry-run simulation mode, and manifest generator.
2. **Phase C (Initial Acquisition):** Acquire `india-latest.osm.pbf` (~1.6 GB), verify SHA-256 / MD5, and acquire open administrative boundaries. Stop and document credential requirements for SOI.
3. **Phase D (Vector Extraction):** Extract and normalize target OSM thematic layers (roads, healthcare, emergency, water, settlements, forests) preserving OSM IDs and tags.
4. **Phase E (Raster Preparation):** Generate national tile index manifests for ESA WorldCover, GHSL, and Copernicus DEM; acquire calibrated representative hazard tiles.
5. **Phase F (Environmental & Observations):** Query Open-Meteo reanalysis across representative climate zones; configure NASA FIRMS client with `NASA_FIRMS_MAP_KEY` support.
6. **Phase G (M10 Integration):** Validate extracted vector layers against M10 normalizer and ingestion CLI in dry-run mode.
7. **Phase H (Validation & Closure):** Run complete test suite, verify historical asset preservation, and generate `geospatial_data_catalog.md` and `national_data_acquisition_report.md`.
