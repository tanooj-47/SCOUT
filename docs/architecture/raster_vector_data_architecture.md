# SCOUT — Dual Raster & Vector Geospatial Architecture

**Subsystem:** M10 Persistent Geospatial Data Integration  
**Scope:** Architectural Distinction, Ingestion Pathways, and Analytical Coexistence  
**Document:** `docs/architecture/raster_vector_data_architecture.md`  
**Status:** Approved Architectural Standard  

---

## 1. Architectural Philosophy: Discrete Entities vs. Continuous Fields

A foundational disaster-intelligence system must operate across two fundamentally distinct spatial data models:

```
+----------------------------------------------------------------------------------------------------+
|                                  SCOUT GEOSPATIAL DATA ENGINE                                      |
+--------------------------------------------------+-------------------------------------------------+
|               VECTOR SUBSYSTEM                   |                RASTER SUBSYSTEM                 |
|       (Discrete Geographical Entities)           |          (Continuous Surface Fields)            |
+--------------------------------------------------+-------------------------------------------------+
| Examples:                                        | Examples:                                       |
| - Sovereign & Subnational Admin Boundaries       | - WorldPop Population Density (1km)             |
| - Healthcare Facilities (Hospitals, Clinics)     | - Copernicus DEM GLO-30 Elevation & Slope (30m) |
| - Fire & Emergency Service Facilities            | - ESA WorldCover 10m Land Cover / Fuel Matrix   |
| - Transport Highway Networks & River Channels    | - Future Inundation Depth / Soil Moisture Grids |
| - Satellite Active Fire Hotspots (Points)        |                                                 |
+--------------------------------------------------+-------------------------------------------------+
| Primary Storage:                                 | Primary Storage:                                |
| PostgreSQL / PostGIS 3.4+ Database Engine        | Cloud-Optimized GeoTIFF (COG) / Object Storage  |
| - Tables: geospatial_features, admin_boundaries  | - Storage: AWS S3 / MinIO / Local Tiled NVMe    |
| - Spatial Index: GiST (Generalized Search Tree)  | - Internal Index: Tile IFDs & Overviews (Pyram) |
+--------------------------------------------------+-------------------------------------------------+
| Query Modality:                                  | Query Modality:                                 |
| Spatial SQL (ST_Contains, ST_Intersects,         | GDAL / Rasterio Windowed Reading & HTTP Range   |
| ST_DWithin, ST_Buffer, ST_Distance)              | Spatial Resampling, Zonal Stats, Map Algebra    |
+--------------------------------------------------+-------------------------------------------------+
```

### The Vectorization Anti-Pattern
Converting high-resolution continuous raster grids (such as 12.11 million WorldPop pixels or 1.296 billion ESA WorldCover cells) into individual PostGIS polygon vector records is strictly prohibited in SCOUT. Doing so introduces severe architectural degradation:
1. **Storage Bloat:** Vectorizing a 100 MB GeoTIFF generates dozens of gigabytes of GeoJSON polygons, coordinates, and bounding boxes.
2. **Index Degradation:** Millions of adjacent rectangular bounding boxes cause extreme degradation in R-tree / GiST indexing selectivity.
3. **Loss of Native Raster Processing:** Prevents hardware-accelerated SIMD map algebra, multi-scale pyramid lookups, and windowed raster queries.

---

## 2. Vector Subsystem Architecture

### 2.1 Scope & Datasets
The vector subsystem ingests, normalizes, and indexes discrete spatial entities:
* **Administrative Units:** `india_national_boundary.geojson`, `india_states_ut.geojson`, `india_districts.geojson`.
* **Critical Facilities:** `india_hospitals_healthcare.geojson` (121,613 records), `india_fire_stations_clipped.geojson` (146 sovereign records).
* **Transportation & Hydrology:** `india_transport_network.geojson` (1,461 highway corridors), `india_major_rivers.geojson` (95 continental river centerlines).
* **Point Observations:** `india_firms_active_fires_clipped.geojson` (5,851 satellite thermal detections), `india_era5_regional_weather_points.geojson` (6 agro-climatic reference points).

### 2.2 Storage Model & PostGIS Schema
All vector features map deterministically to the Pydantic schema `NormalizedFeature` and are persisted in PostgreSQL:
* **Table:** `geospatial_features`
* **Core Columns:**
  - `id`: UUID (Primary Key, deterministically generated via `uuid5(NAMESPACE_DNS, ...)`).
  - `feature_id`: String (upstream source identifier, e.g. `osm_node_264480826`).
  - `name`: String (canonical facility or unit name).
  - `category`: Enum (`administrative`, `infrastructure`, `hazard`, `settlement`).
  - `facility_type`: Nullable String (`hospital`, `fire_station`, `clinic`).
  - `hazard_relevance`: Array (`['wildfire', 'flood', 'earthquake']`).
  - `geometry`: `geometry(Geometry, 4326)` with strict GiST spatial indexing.
  - `source_provider`: String (origin provenance).
  - `properties`: JSONB (unstructured domain-specific tags and attributes).

### 2.3 Vector Ingestion Pipeline
Vector processing follows a deterministic 4-stage pipeline:
1. **Acquisition & Inspection:** Download raw source (GeoJSON, Shapefile, OSM JSON) with disk-space preflight validation and SHA-256 verification.
2. **Topological Validation:** Shapely validation, multi-part simplification, and sovereign polygon clipping (`prep(boundary_geom).contains(point)`).
3. **Normalization & Schema Mapping:** Transformation to Pydantic models with coordinate rounding (6 decimals for points, 5 for polygons).
4. **Idempotent Upsert:** Database ingestion using `ON CONFLICT (id) DO UPDATE`.

---

## 3. Raster Subsystem Architecture

### 3.1 Scope & Datasets
The raster subsystem manages continuous geospatial fields across India:
* **Human Population Density:** WorldPop India 2020 1km (`ind_pd_2020_1km.tif`, 18.08 MB, 32-bit float, $3508 \times 3451$ pixels).
* **Terrain & Elevation:** Copernicus DEM GLO-30 (`Copernicus_DSM_COG_10_N24_00_E078_00_DEM.tif`, 40.11 MB, 32-bit float, $3600 \times 3600$ pixels).
* **Land Cover / Fuel Matrix:** ESA WorldCover 10m 2021 (`ESA_WorldCover_10m_2021_v200_N24E078_Map.tif`, 101.80 MB, 8-bit paletted, $36000 \times 36000$ pixels).

### 3.2 Raster Metadata Profiles vs. Raster Datasets
A strict distinction is maintained between:
1. **Raster Dataset:** The binary GeoTIFF file (`.tif`) containing raw pixels, projection metadata, and tiepoint transforms.
2. **Raster Metadata Profile:** The lightweight companion JSON file (`_profile.json`) stored in `data/processed/geospatial/`.  
   *The profile JSON is strictly an operational catalog descriptor for fast service bootstrapping without reading raster headers. It is NEVER treated as a replacement for the underlying raster bytes.*

### 3.3 Storage & Access Standards
All production rasters are stored or reformatted as **Cloud-Optimized GeoTIFFs (COGs)**:
* **Tiling:** Internal $256 \times 256$ or $512 \times 512$ pixel blocks.
* **Overviews:** Multi-resolution pyramid downsamplings (2x, 4x, 8x, 16x) computed with cubic or average resampling.
* **Compression:** LZW or DEFLATE compression with horizontal predictor for floating-point bands.
* **Windowed Reading:** Python services use Rasterio / GDAL window reading (`src.read(1, window=window)`) to read only the spatial bounding box required by a disaster incident, bypassing the need to load the entire multi-gigabyte raster into system memory.

---

## 4. Hybrid Geospatial Analysis Workflows

In real-world disaster intelligence, vector entities and raster fields continuously intersect:

```
                              +---------------------------------------+
                              | Disaster Perimeter (Vector Polygon)   |
                              | e.g. Wildfire Inundation Zone         |
                              +-------------------+-------------------+
                                                  |
                    +-----------------------------+-----------------------------+
                    |                                                           |
                    v                                                           v
+---------------------------------------+                   +---------------------------------------+
|        Vector Spatial Query           |                   |         Raster Window Extraction      |
| SELECT * FROM geospatial_features     |                   | window = rasterio.windows.from_bounds |
| WHERE ST_DWithin(geom, hazard, 5000)  |                   | data = raster.read(1, window=window)  |
+-------------------+-------------------+                   +-------------------+-------------------+
                    |                                                           |
                    v                                                           v
  - Identified 4 Hospitals in Path                            - Sampled Terrain Slopes (28% slope)
  - Identified 1 Fire Station Available                       - Extracted Land Cover (Class 10 Forest)
  - Calculated Evacuation Road Bottlenecks                    - Integrated Population Exposure (42,500)
                    |                                                           |
                    +-----------------------------+-----------------------------+
                                                  |
                                                  v
                               +-------------------------------------+
                               | Unified Disaster Impact Assessment  |
                               +-------------------------------------+
```

### 4.1 Population Exposure Integration Equation
When intersecting a disaster perimeter with the WorldPop density raster, the total population exposed is computed via latitude-dependent cell area integration:
$$\text{Total Exposed Persons} = \sum_{j \in \text{Hazard Polygon}} \left( \rho_j \times \left[ (R \cdot \Delta\lambda \cos\phi_j) \times (R \cdot \Delta\phi) \right] \right)$$
Where:
* $\rho_j$ = pixel value from `ind_pd_2020_1km.tif` ($\text{persons}/\text{km}^2$).
* $\phi_j$ = latitude of pixel center in radians.
* $\Delta\lambda, \Delta\phi$ = pixel resolution in radians ($0.0083333333^\circ \times \frac{\pi}{180}$).
* $R = 6,371.0\text{ km}$.

---

## 5. Architectural Invariant Summary

1. **Vector pipelines MUST NOT** attempt to ingest continuous rasters into relational tables.
2. **Raster pipelines MUST NOT** convert multi-million pixel arrays into GeoJSON vectors.
3. **Database tables in M10** strictly store discrete vector features and operational raster catalog descriptors.
4. **Heavy raster processing** is performed via windowed streaming and SIMD map algebra using Rasterio, NumPy, and GDAL.
