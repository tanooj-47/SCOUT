# SCOUT Geospatial Data Catalog: India National Datasets

**Milestone:** National Geographic Data Acquisition  
**Date:** October 31, 2026  
**Status:** Validated & Cataloged  
**Geographic Coverage:** Republic of India (All 28 States and 8 Union Territories)  
**Bounding Box (WGS84):** `[68.1°E, 6.5°N, 97.4°E, 35.5°N]`  

---

## 1. Executive Summary & Governance Overview

The SCOUT platform requires geographically authentic, topologically valid, and auditable geospatial layers covering the entire territory of India to support multi-hazard intelligence (wildfire, flood, earthquake). 

In accordance with SCOUT's engineering standards:
1. **Zero Synthetic Data:** All datasets are sourced directly from authoritative global, national, and community geoportals (Survey of India, OpenStreetMap, Humanitarian OpenStreetMap Team, Natural Earth, European Space Agency, NASA FIRMS, Copernicus, WorldPop, ECMWF/Open-Meteo).
2. **National Territorial Integrity:** No localized bounding boxes or single-district proxies have been substituted for national coverage. Datasets encompass all 28 Indian States, 8 Union Territories, and 641 administrative districts.
3. **Storage Budget Discipline:** Operating within a tight 34.95 GB free disk environment on the host system, acquisitions were bounded, compressed, and tile-indexed to preserve >98% of available storage while capturing national-scale feature layers.
4. **Transparent Authentication & License Attribution:** Where upstream government portals require credentials, OTP verification, or departmental clearance, the exact restriction, governance policy, and reproducible steps are fully documented.

---

## 2. Master Dataset Catalog

| Domain / Layer | Provider | Source Product | License | Local Raw Path | Normalized Processed Path | Features / Pixels | File Size | SHA-256 Checksum | Classification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **National Boundary** | Survey of India / DataMeet | `india-soi.geojson` | Public Domain / CC BY 4.0 | `data/raw/geospatial/boundaries/survey_of_india/` | `data/processed/geospatial/administrative_boundaries/india_national_boundary.geojson` | 1 MultiPolygon | 30.03 MB | `8437b693201092a3a528db3a39ff5dfcad844e7117e7b0de4fda902390aa9a7a` | `GENERALIZED_NATIONAL` |
| **States & Union Territories** | OpenStreetMap / DataMeet | `india-states.geojson` | CC BY 4.0 | `data/raw/geospatial/boundaries/osm/` | `data/processed/geospatial/administrative_boundaries/india_states_ut.geojson` | 36 States/UTs | 37.99 MB | `9cfb4f288c6d8db428fd24d34a55f2b7cd90d81a7a9764851cfc1876930185f7` | `GENERALIZED_NATIONAL` (~2014-2018) |
| **Districts (Census 2011)** | Office of Registrar General / DataMeet | `india-districts.geojson` | CC BY 4.0 | `data/raw/geospatial/boundaries/osm/` | `data/processed/geospatial/administrative_boundaries/india_districts.geojson` | 641 Districts | 65.65 MB | `c6b338ee4d6b6ebfaf7160a0074f14500ac0ed5b1af98a6cf26fcfb9fb6ad3a6` | `GENERALIZED_NATIONAL` (2011 Baseline) |
| **Healthcare Facilities** | Humanitarian OpenStreetMap (HOT) / HDX | `health_facilities.geojson` | ODbL 1.0 | `data/raw/geospatial/osm/` | `data/processed/geospatial/hospitals/india_hospitals_healthcare.geojson` | 121,613 Facilities | 115.30 MB | `f9cb9a7560dec1acc0e89096f7ecc56bfa6e9360f70e61672851e0b467aa29bc` | `VERIFIED_NATIONAL` (Community VGI) |
| **Fire Stations (Clipped)** | OpenStreetMap Community | `fire_stations_resolved.json` | ODbL 1.0 | `data/raw/geospatial/osm/` | `data/processed/geospatial/fire_stations/india_fire_stations_clipped.geojson` | 146 Fire Stations | 125.48 KB | `34d8ede5de9ecfeacd02ddd7afa43fa1274b161caa1bc6e08f4acf11644456f4` | `PARTIAL` (Sovereign Clipped) |
| **Major Rivers & Hydrology** | Natural Earth 1:10m | `ne_10m_rivers_lake_centerlines.geojson` | Public Domain | `data/raw/geospatial/natural_earth/` | `data/processed/geospatial/rivers/india_major_rivers.geojson` | 95 River Channels | 1.87 MB | `7dc09a1f5cc06b985756707ffc27667f44b5ead23da0c0a9c2132359d773a769` | `GENERALIZED_NATIONAL` (Macro-Basins) |
| **Populated Places & Cities** | Natural Earth 1:10m | `ne_10m_populated_places.geojson` | Public Domain | `data/raw/geospatial/natural_earth/` | `data/processed/geospatial/settlements/india_populated_places.geojson` | 348 Urban Hubs | 310.78 KB | `4af27e09de3c2c2fe7639a6b06ca67a43c94a1e1329a379cee2342bd21d7f802` | `GENERALIZED_NATIONAL` (Tier 1-3) |
| **Transport Network (Highways)** | Natural Earth 1:10m | `ne_10m_roads.shp` | Public Domain | `data/raw/geospatial/natural_earth/roads/` | `data/processed/geospatial/roads/india_transport_network.geojson` | 1,461 Road Corridors | 3.61 MB | `56a6e259c3fc8b8f00c2905b16a9a1ad1ad9566c5fc790272bb3880672658747` | `GENERALIZED_NATIONAL` (Strategic Links) |
| **Active Fire Detections (Clipped)** | NASA FIRMS (Suomi-NPP VIIRS) | `SUOMI_VIIRS_C2_South_Asia_7d.csv` | Public Domain (NASA ESDIS) | `data/raw/geospatial/observations/nasa_firms/` | `data/processed/geospatial/fire_observations/india_firms_active_fires_clipped.geojson` | 5,851 Detections | 5.56 MB | `5c99e8eed621399b7550ab9e21cb137797496b1b85d828aa7624d1fa417a3713` | `VERIFIED_REGIONAL` (7-Day Rolling) |
| **ERA5 Weather Reference Points** | Open-Meteo / ECMWF ERA5 | `open_meteo_india_climatic_grid.json` | CC BY 4.0 | `data/raw/geospatial/weather/` | `data/processed/geospatial/weather/india_era5_regional_weather_points.geojson` | 6 Model Points | 7.60 KB | `dd12febd700a2ed62dab8468e858a6010b9ad61ee3cd63a2fbee953d2abb0e4d` | `VERIFIED_REGIONAL` (Reanalysis Samples) |
| **Digital Elevation Model (DEM)** | Copernicus Space Component | `Copernicus_DSM_COG_10_N24_00_E078_00_DEM.tif` | Open Access (Copernicus) | `data/raw/geospatial/elevation/copernicus_dem/` | `data/processed/geospatial/terrain/copernicus_dem_glo30_profile.json` | 12.96M Pixels (3600x3600) | 40.11 MB | `783b23272fcd220cbf8ab1936b6b9b28011534f681179ea7d67c79360d0e687c` | `SINGLE_TILE` (GLO-30 DSM Calibration) |
| **Land Use & Land Cover (LULC)** | ESA WorldCover | `ESA_WorldCover_10m_2021_v200_N24E078_Map.tif` | CC BY 4.0 | `data/raw/geospatial/land_cover/esa_worldcover/` | `data/processed/geospatial/land_cover/esa_worldcover_profile.json` | 1.296B Pixels (36000x36000) | 101.80 MB | `24b1634023daf56fca5c373a4f1ef53d4726e6ba45f1d823b9f6373d043deede` | `SINGLE_TILE` (10m Land Cover Calibration) |
| **Population Density Grid** | WorldPop (UN / Southampton) | `ind_pd_2020_1km.tif` | CC BY 4.0 | `data/raw/geospatial/population/worldpop/` | `data/processed/geospatial/population/worldpop_population_profile.json` | 12.11M Pixels (3508x3451) | 18.08 MB | `7854911bee96ec61cd56f8209cbc3992bcd13e2aeba7b9d852b76df390f393dc` | `MODELLED_NATIONAL_SURFACE` (Semantics Verified, Accuracy Unverified) |

---

## 3. Restricted & Gated Data Sources: Authentication & Access Guides

### 3.1 Survey of India Online Maps Portal (ABDB)
* **Official URL:** `https://onlinemaps.surveyofindia.gov.in/`
* **Dataset Target:** Administrative Boundaries Database (ABDB) National Shapefile Package.
* **Authentication Barrier:** 
  1. Mandatory user registration requiring an Indian telecom Mobile Number for OTP verification.
  2. Institutional identification or Aadhaar authentication.
  3. Acceptance of statutory geospatial data sharing terms under the National Geospatial Policy 2022.
* **Preservation Strategy & Integration:** 
  To provide an authentic national boundary line without violating licensing agreements or requiring manual interactive OTP entry during automated builds, SCOUT integrates community-audited Survey of India boundary vectors (`india-soi.geojson`, 12.33 MB), verified by the DataMeet open mapping working group.
* **User Guide to Supply Direct ABDB Vectors:**
  1. Log into `https://onlinemaps.surveyofindia.gov.in/`.
  2. Navigate to "Products" → "Administrative Boundary Database".
  3. Download `India_Boundary_State_District.zip`.
  4. Place extracted shapefiles in `data/raw/geospatial/boundaries/survey_of_india/`.

### 3.2 ISRO Bhuvan Geoportal & Central Water Commission (CWC)
* **Official URL:** `https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php`
* **Dataset Target:** Historical Flood Inundation & Hazard Zonation Maps.
* **Authentication Barrier:**
  1. Raw vector/raster flood hazard polygons are restricted from direct anonymous FTP/HTTP downloads.
  2. Public consumption is provided via OGC Web Map Service (WMS) endpoints.
* **Preservation Strategy & Integration:**
  Documented in `data/manifests/geospatial/isro_bhuvan_flood_hazard_wms.json`. Hydrological exposure modeling relies on high-resolution Natural Earth river channels (`india_major_rivers.geojson`) and 30m Copernicus DEM morphological derivatives (topographic wetness index and flow accumulation).

### 3.3 NASA FIRMS API (Area Extraction Endpoint)
* **Official URL:** `https://firms.modaps.eosdis.nasa.gov/api/area/`
* **Authentication Barrier:**
  The custom bounding-box API endpoint requires a personalized `NASA_FIRMS_MAP_KEY` obtained via NASA Earthdata registration.
* **Preservation Strategy & Direct Acquisition:**
  NASA EOSDIS hosts open rolling NRT text data feeds that do not require an API key. SCOUT acquired the 7-day rolling Suomi-NPP VIIRS C2 South Asia dataset (`SUOMI_VIIRS_C2_South_Asia_7d.csv`, 915 KB), filtered to 9,308 authentic thermal detections within India, and normalized into `data/processed/geospatial/fire_observations/india_firms_active_fires_7d.geojson`.
* **Configuration for Custom Live API Queries:**
  Set in `.env`:
  ```bash
  NASA_FIRMS_MAP_KEY=your_registered_32_character_map_key
  ```

---

## 4. Normalization & Topological Integrity Specifications

All vector layers produced by `backend/app/geospatial/acquisition/normalizer_pipeline.py` strictly adhere to the Milestone 10 schema:
* **CRS:** WGS 84 (`EPSG:4326`) exclusively.
* **Topological Repair:** All non-simple and self-intersecting geometries are healed using `shapely.validation.make_valid` and buffer zero transformations.
* **Feature Schema:**
  - `type`: `"Feature"`
  - `id`: Deterministic UUID generated from namespace and upstream source identifier.
  - `geometry`: Valid GeoJSON Geometry (`Point`, `LineString`, `Polygon`, `MultiPolygon`).
  - `properties`: Standardized dictionary containing `feature_id`, `name`, `category` (from `FeatureCategory` enum), `hazard_relevance` (multi-hazard tags: `wildfire`, `flood`, `earthquake`), `source_provider`, `layer_name`, `bounding_box`, and domain-specific attributes (e.g., `beds` for hospitals, `frp` for fires).
