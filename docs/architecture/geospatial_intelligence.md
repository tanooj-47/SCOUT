# SCOUT Geospatial Intelligence Engine — Architectural Specification

**Platform:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Component:** Geospatial Intelligence Engine (`backend/app/geospatial`)  
**Status:** Implemented & Verified (Milestone 08)  
**Primary Standards:** WGS 84 (EPSG:4326), Web Mercator (EPSG:3857), UTM Projections (EPSG:32601–32760), OGC Simple Features, GeoJSON (RFC 7946)  

---

## 1. Architectural Overview & Design Philosophy

The **SCOUT Geospatial Intelligence Engine** provides modular, scientifically grounded spatial reasoning, coordinate management, exposure analysis, and risk evaluation for disaster response operations.

```
+--------------------------------------------------------------------------------------------------+
|                                    SCOUT FASTAPI REST API                                        |
|  POST /api/v1/geospatial/validate-coordinate   |   POST /api/v1/geospatial/analyze               |
|  GET  /api/v1/geospatial/nearby                |   GET  /api/v1/geospatial/health                |
|  GET  /api/v1/geospatial/incidents/{id}/exposure                                                 |
+--------------------------------------------------------------------------------------------------+
                                                |
                                                v
+--------------------------------------------------------------------------------------------------+
|                                     GEOSPATIAL SERVICE LAYER                                     |
|                                (app.services.geospatial_service)                                 |
+--------------------------------------------------------------------------------------------------+
        |                                       |                                   |
        v                                       v                                   v
+-----------------------+           +-----------------------+           +-----------------------+
|  COORDINATE & CRS     |           |  GEOMETRIC OPERATIONS |           |  SPATIAL QUERY ENGINE |
|  - WGS84 Validation   |           |  - Shapely 2.0 Models |           |  - PostGIS ST_DWithin |
|  - NaN/Inf Rejection  |           |  - Metric UTM Buffers |           |  - Geography Distance |
|  - PyProj Geod (WGS84)|           |  - Hectares Area Calc |           |  - Spatial Indexes    |
|  - UTM Auto-Zone Res. |           |  - GeoJSON / WKT Ser. |           |  - Pure-Python Fallbk |
+-----------------------+           +-----------------------+           +-----------------------+
        |                                       |                                   |
        +---------------------------------------+-----------------------------------+
                                                |
                                                v
+--------------------------------------------------------------------------------------------------+
|                                  EXPOSURE & RISK ASSESSMENT ENGINE                               |
|  - Geographic Context Catalog (features, categories, provenance)                                 |
|  - ExposureEngine (radius query, shortest geodesic distance, topological relationships)          |
|  - Disaster-Specific Risk Assessors (WildfireRiskAssessor, FloodRiskAssessor, EarthquakeAssessor)|
|  - Transparent Evidence Formatting (contributing factors, missing layer indicators, limits)       |
+--------------------------------------------------------------------------------------------------+
```

### Core Design Principles

1. **Separation of Exposure from Hazard Prediction:**
   Geographic exposure (e.g. "settlement exists 850m from incident origin") is an objective, deterministic spatial fact. Hazard prediction (e.g. rate of wildfire spread or flood inundation) requires validated numerical simulation models (e.g. Rothermel, HEC-RAS). The engine strictly forbids presenting proximity indicators as validated disaster probabilities or speculative hazard scores.

2. **Accurate Geodesic & Planar Mathematics:**
   Geographic coordinates in decimal degrees must never be used directly for distance calculations or buffering. Buffering in degrees produces distorted ellipses whose ground width shrinks from ~111 km at the equator to 0 km at the poles. All metric buffering dynamically resolves local Universal Transverse Mercator (UTM) projections, buffers in exact meters, and transforms back to WGS 84. Distances are computed via Karney's ellipsoidal geodesic formulas (`pyproj.Geod`) or spherical Haversine.

3. **Graceful Degradation & Data Truthfulness:**
   When PostGIS is offline, the system relies on an in-memory/vector spatial catalog rather than fabricating a database response. Missing spatial layers (e.g. road networks, building footprints, river bathymetry) are explicitly enumerated as missing data indicators rather than silently assumed empty.

---

## 2. Module Responsibilities

The package resides under `backend/app/geospatial/`:

| Module | Primary Responsibility |
| :--- | :--- |
| [`coordinates.py`](../../backend/app/geospatial/coordinates.py) | WGS 84 boundary validation, NaN/Inf rejection, ellipsoidal geodesic distance, Haversine fallback, UTM zone auto-resolution, PyProj coordinate transformations. |
| [`geometry.py`](../../backend/app/geospatial/geometry.py) | Shapely 2.0 geometry construction (Point, Polygon), self-intersection repair (`make_valid`), metric UTM circular buffer generation, planar hectare area calculation, GeoJSON & WKT serialization. |
| [`spatial_queries.py`](../../backend/app/geospatial/spatial_queries.py) | PostGIS spatial queries using `ST_DWithin` and `ST_Distance` on geography types, query radius boundary validation ($100\text{m} \le r \le 100\text{km}$), PostGIS liveness probe. |
| [`context.py`](../../backend/app/geospatial/context.py) | In-memory spatial index and feature catalog (`GeographicContextCatalog`). Stores verified spatial features with categories, metadata, and provenance. Identifies missing layers. |
| [`exposure.py`](../../backend/app/geospatial/exposure.py) | Aggregates spatial exposure: category counts, shortest geodesic distance to feature perimeters, identification of intersecting or high-priority exposed assets. |
| [`risk.py`](../../backend/app/geospatial/risk.py) | Extensible risk evaluation architecture (`BaseRiskAssessor`, `WildfireRiskAssessor`, `FloodRiskAssessor`, `EarthquakeRiskAssessor`). Synthesizes explainable contributing factors and scientific limitations. |
| [`schemas.py`](../../backend/app/geospatial/schemas.py) | Strict Pydantic models for coordinate validation, nearby queries, exposure requests, GeoJSON geometries, and assessment responses. |
| [`exceptions.py`](../../backend/app/geospatial/exceptions.py) | Typed domain exceptions (`InvalidCoordinateError`, `InvalidGeometryError`, `RadiusOutOfBoundsError`, `PostGISUnavailableError`) integrated with SCOUT uniform error envelopes. |

---

## 3. Coordinate Reference Systems (CRS) & Geometry Policy

### 3.1 Primary Coordinate System: WGS 84 (EPSG:4326)
- **Axis Order:** Internal geometric representations conform strictly to the GeoJSON / OGC standard:
  $$\mathbf{x} = \text{longitude } [-180.0, 180.0], \quad \mathbf{y} = \text{latitude } [-90.0, 90.0]$$
- **Input Validation:** Coordinates are validated against IEEE-754 finiteness (`math.isfinite`) and physical Earth latitude/longitude boundaries.

### 3.2 Dynamic Local Projection: UTM (Universal Transverse Mercator)
For distance buffering and area calculations, coordinates are projected into their local 6-degree longitudinal UTM zone:
$$\text{Zone} = \left\lfloor \frac{\text{longitude} + 180^\circ}{6^\circ} \right\rfloor + 1$$
- Northern Hemisphere ($\text{lat} \ge 0^\circ$): $\text{EPSG: } 32600 + \text{Zone}$
- Southern Hemisphere ($\text{lat} < 0^\circ$): $\text{EPSG: } 32700 + \text{Zone}$

### 3.3 Metric Buffering Algorithm
```
Input: Latitude, Longitude, Radius (meters)
  │
  ├─► Validate coordinates in WGS 84 (EPSG:4326)
  ├─► Determine local UTM EPSG code (e.g. EPSG:32610 for California)
  ├─► Transform WGS 84 Point (lon, lat) -> UTM Point (Easting, Northing) in meters
  ├─► Execute Shapely buffer(radius_meters, quad_segs=16) in planar Euclidean space
  ├─► Transform resulting polygon vertices back from UTM -> WGS 84 (EPSG:4326)
  └─► Output: Valid, scientifically accurate WGS 84 geodesic circular polygon
```

---

## 4. PostGIS Database Integration

Where a live PostgreSQL/PostGIS database is active, spatial queries operate on the `incidents` table using spatial indexes (`GIST`):

```sql
SELECT 
    id,
    title,
    disaster_type,
    status,
    severity,
    ST_Y(location::geometry) AS latitude,
    ST_X(location::geometry) AS longitude,
    ST_Distance(
        location::geography,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
    ) AS distance_meters
FROM incidents
WHERE 
    is_archived = false
    AND ST_DWithin(
        location::geography,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
        :radius_meters
    )
ORDER BY distance_meters ASC
LIMIT :limit;
```

**Index Utilization:**
- `ST_DWithin(location::geography, ...)` leverages the functional GiST index `ix_incidents_location_geography` defined on `(location::geography)`.
- Eliminates sequential table scans over global incident databases.

---

## 5. Data Source Integration & Ingestion Design

SCOUT strictly prohibits automatic scraping or data fabrication. Future production deployments should ingest vector and raster data according to the following specifications:

| Layer Category | Recommended Authoritative Source | Coverage | Expected Format | License / Terms | Integration Method |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Settlements & Urban Footprints** | OpenStreetMap (OSM) via Geofabrik Extracts / US Census TIGER | Global / Regional | GeoPackage (`.gpkg`) / PostGIS polygon | ODbL (Open Database License) | Automated GDAL/OGR vector pipeline into PostGIS |
| **Transportation & Road Networks** | OpenStreetMap Highways (`highway=*`) / National Road Networks | Global | GeoPackage line strings | ODbL | Selective import of primary/secondary egress corridors |
| **Forest Canopy & Fuels** | USFS LANDFIRE Fuel Models / Copernicus Land Cover | US / Global | Cloud-Optimized GeoTIFF (COG) | Public Domain / CC-BY | Rasterio zonal stats & windowed extraction |
| **Hydrology & Water Bodies** | USGS National Hydrography Dataset (NHD) / OSM Water | Global / Regional | PostGIS Polygons / Lines | Public Domain | ST_Intersects and ST_DWithin distance filtering |
| **Critical Infrastructure** | Homeland Infrastructure Foundation-Level Data (HIFLD) / OpenStreetMap | Regional / National | PostGIS Points & Lines | Public Domain / ODbL | Spatial catalog ingestion with strict access controls |

---

## 6. API Contracts

### `POST /api/v1/geospatial/validate-coordinate`
Validates latitude/longitude coordinates and resolves the optimal UTM projection.
- **Request:** `{"latitude": 37.7749, "longitude": -122.4194}`
- **Response:** `{"is_valid": true, "latitude": 37.7749, "longitude": -122.4194, "srid": 4326, "utm_epsg": 32610, "error_message": null}`

### `GET /api/v1/geospatial/nearby`
Retrieves spatial entities in proximity to coordinates.
- **Parameters:** `latitude`, `longitude`, `radius_meters` ($100 \le r \le 100,000$), `categories`, `limit`, `include_geometry`.
- **Response:** Array of `GeographicFeatureItem` with exact geodesic distances.

### `POST /api/v1/geospatial/analyze`
Executes an explainable spatial exposure assessment for an incident ID or arbitrary coordinate.
- **Request:** `{"latitude": 37.7749, "longitude": -122.4194, "search_radius_meters": 5000, "disaster_type": "wildfire"}`
- **Response:** `GeospatialAssessmentResponse` containing:
  - `incident_context`
  - `exposure_summary` (counts, closest distance, highlighted features)
  - `contributing_factors` (plain-language evidence)
  - `missing_data_indicators` (explicit listing of unavailable layers)
  - `assessment_limitations` (boundary disclaimers)

### `GET /api/v1/geospatial/health`
Probes PostGIS connectivity, Shapely, PyProj, and supported projections.

---

## 7. In-Memory Geographic Context Catalog (`GeographicContextCatalog`)

The runtime geospatial engine maintains an in-memory spatial catalog (`backend/app/geospatial/context.py`) used for pure-Python fallback querying, layer presence accounting, and exposure indexing.

### 7.1 Key Invariants & Deduplication Policy
- **Primary Key Uniqueness:** Each feature is indexed internally by a string `feature_id` in `_feature_by_id: Dict[str, Dict[str, Any]]`. Non-string or empty `feature_id` entries are strictly rejected with a `ValueError`.
- **Duplicate Handling:**
  - `add_feature(..., overwrite=True)` (default): Deterministically overwrites preexisting features with identical `feature_id`, updating attributes, geometries, categories, and metadata in place.
  - `add_feature(..., overwrite=False)`: Protects existing records; if a collision occurs on `feature_id`, the catalog returns `False` and leaves the existing feature untouched.
- **Dynamic Layer Synchronization:** When features are inserted, updated, or removed, the catalog dynamically recomputes its active layer set (`_recalculate_available_layers()`). If a feature's category changes from `ROAD` to `SETTLEMENT` (or if all features of a category are removed), `is_layer_available()` and `get_missing_layers()` reflect the exact state without drift.
- **Collection API:** Provides standard management methods:
  - `remove_feature(feature_id: str) -> bool`: Safely deletes a feature and resynchronizes layers.
  - `get_feature(feature_id: str) -> Optional[Dict[str, Any]]`: $O(1)$ lookup by ID.
  - `clear() -> None`: Purges all features and resets available layers to empty.
  - `__len__() -> int`: Returns current feature count.

---

## 8. High-Priority Exposure Threshold Configuration

The exposure analysis pipeline distinguishes between general proximity (within search radius) and high-priority operational exposure.

### 8.1 Configuration Specification
- **Configuration Parameter:** `GEOSPATIAL_PRIORITY_THRESHOLD_METERS: float = 1000.0` defined in `backend/app/core/config.py`.
- **Validation Rules:** Validated via Pydantic `@field_validator` ensuring value is finite and strictly positive ($v > 0.0$ and `math.isfinite(v)`). Non-numeric, non-finite (NaN, $\pm\infty$), or non-positive values raise a validation error during application bootstrap.
- **Operational Logic:**
  - In `ExposureEngine.analyze_exposure()`, features within the search radius are categorized and measured.
  - A feature is appended to `highlighted_exposed_features` (capped at top 10 closest) if:
    $$\text{relationship} = \text{INTERSECTS} \quad \lor \quad \text{distance\_meters} \le \text{threshold\_m}$$
- **Runtime Overridability:**
  - Default: Reads `settings.GEOSPATIAL_PRIORITY_THRESHOLD_METERS` (1,000.0m).
  - Instance-level: `ExposureEngine(catalog, priority_threshold_meters=2000.0)`.
  - Execution-level: `engine.analyze_exposure(..., priority_threshold_meters=2000.0)`.
  - Both instance and call-level overrides enforce identical finite positive validation.

