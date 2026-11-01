# SCOUT — Milestone 10 Closeout Evidence Appendix

**Milestone:** M10 Persistent Geospatial Data Integration  
**Document:** `docs/reports/m10_closeout_evidence_appendix.md`  
**Audit Date:** October 31, 2026  
**Auditor / Roles:** Senior Geospatial Data Engineer, GIS Auditor, Python Backend Engineer, and ML Systems Reviewer  
**Audit Purpose:** Independent Evidence Audit, Accounting Verification, and Discrepancy Resolution  

---

## 1. Automated Test Accounting & Contradiction Resolution

### 1.1 Root Cause of the Reporting Contradiction
In the previous report (`docs/reports/m10_data_quality_correction_report.md`), Section 4.1 reported:
- Backend unit tests: 227 passed
- ML regression tests: 137 collected
- Summary statement: "all 364 automated tests pass"

This was an inaccurate conflation of **collected** tests with **executed and passed** tests. The 137 ML regression tests were collected via `pytest --collect-only` to verify discovery without invoking neural network training or forward-pass compute under the read-only constraint. They were **not executed** in the closeout test run.

### 1.2 Exact Test Accounting Matrix
The following table provides the audited, truthful test execution accounting:

| Test Suite | Exact Command Line | Collected | Executed | Passed | Failed | Skipped | Interrupted / Unverified | Evidence Source |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Geospatial Data Quality** | `.venv\Scripts\python.exe -m pytest backend/tests/unit/geospatial/test_national_data_quality.py -v` | 13 | 13 | 13 | 0 | 0 | 0 | Step 7288 (0.18s) & Step 7338 (0.16s) |
| **Full Backend Unit Suite** | `.venv\Scripts\python.exe -m pytest backend/tests/unit/` | 227 | 227 | 227 | 0 | 0 | 0 | Step 7291 (4.87s), Step 7306 (5.01s), Step 7340 (5.16s) |
| **ML Regression Suite** | `.venv\Scripts\python.exe -m pytest -o pythonpath=. --collect-only ml/tests/` | 137 | 0 | 0 | 0 | 0 | 137 (Collection only) | Step 7294 (7.30s) |
| **Total Automated Tests** | *Repository Test Inventory* | **364** | **227** | **227** | **0** | **0** | **137** | Verified by pytest discovery |

* **Verified Unique Tests Passed in this Closeout:** **227 tests** (100% pass rate among executed tests).
* **Unverified / Collection Only:** **137 ML regression tests** (discovered and syntax-validated, but execution bypassed to comply with model training and evaluation restrictions).

---

## 2. Boundary Dataset Provenance & Spatial Clipping Verification

### 2.1 Project Boundary Dataset Provenance
* **File:** `data/processed/geospatial/administrative_boundaries/india_national_boundary.geojson`
* **Raw Source:** `data/raw/geospatial/boundaries/survey_of_india/india-soi.geojson` (12,330,591 bytes, SHA-256: `7c7bb149e370a7dd83f4f728fa5201116632f051662fa9e018635e1654452179`).
* **Origin:** DataMeet community digitization of the Survey of India state map outline (`https://github.com/datameet/maps/tree/master/Country`).
* **Geometry Properties:** MultiPolygon (1 feature), 26,450 coordinate vertices, CRS: `EPSG:4326` (WGS 84).
* **Topological Validity:** Verified via `shapely.is_valid` -> `True` (0 self-intersections, 0 empty rings).
* **Cartographic Standard:** Reflects the official Survey of India cartographic outline (including the entire territories of Jammu, Kashmir, and Ladakh under Indian national cartographic convention), rather than the de facto Line of Control (LoC) or Line of Actual Control (LAC).
* **Standard Terminology Enforced:** Spatial filtering is strictly defined as **“within the project boundary dataset”**. GIS operations do not constitute legal or sovereign geopolitical assertions.

### 2.2 Fire Station Clipping Evidence
* **Raw Input:** `data/raw/geospatial/osm/fire_stations_resolved.json` (300 OSM nodes retrieved via rectangular bounding box query $[68.5^\circ\text{E}, 8.0^\circ\text{N}, 97.0^\circ\text{E}, 35.5^\circ\text{N}]$).
* **Intermediate BBox File:** `data/processed/geospatial/fire_stations/india_fire_emergency_facilities.geojson` (300 features).
* **Output Deliverable:** `data/processed/geospatial/fire_stations/india_fire_stations_clipped.geojson` (125,476 bytes, SHA-256: `34d8ede5de9ecfeacd02ddd7afa43fa1274b161caa1bc6e08f4acf11644456f4`).
* **Spatial Predicate:** `prep(boundary_geom).contains(pt) or boundary_geom.touches(pt)`.
* **Audited Counts:**
  - Input Features: 300
  - Retained Features: **146** (within the project boundary dataset)
  - Excluded Features: **154** (extra-territorial nodes in Pakistan, Bangladesh, and Nepal)
  - Accounting Check: $300 = 146 + 154$ (Verified exact).
* **Traceability:** 146 / 146 features (100%) trace directly back to their upstream OSM node identifiers via `properties.osm_id`.
* **Coverage Scope:** Classified as **`PARTIAL`**. The 146 retained stations represent an exploratory OpenStreetMap sample and do not constitute a comprehensive national directory of fire stations.

### 2.3 NASA FIRMS Active Fire Hotspots Clipping Evidence
* **Raw Input:** `data/raw/geospatial/observations/nasa_firms/SUOMI_VIIRS_C2_South_Asia_7d.csv` (11,320 observations).
* **Intermediate BBox File:** `data/processed/geospatial/fire_observations/india_firms_active_fires_7d.geojson` (9,308 features).
* **Output Deliverable:** `data/processed/geospatial/fire_observations/india_firms_active_fires_clipped.geojson` (5,563,753 bytes, SHA-256: `5c99e8eed621399b7550ab9e21cb137797496b1b85d828aa7624d1fa417a3713`).
* **Instrument & Product:** Suomi-NPP VIIRS 375m Active Fire Collection 2 (NRT v2.0). Satellite identifier: `N`.
* **Observation Period:** Rolling 7-day observation snapshot: **October 24, 2026 06:16 UTC to October 31, 2026 08:30 UTC**.
* **Spatial Predicate:** `prep(boundary_geom).contains(pt) or boundary_geom.touches(pt)`.
* **Audited Counts:**
  - Raw South Asia CSV Rows: 11,320
  - Bounding-Box Candidates: 9,308
  - Retained Features (within project boundary): **5,851**
  - Excluded Features in BBox: **3,457** (detections in neighboring nations and offshore flaring)
  - Excluded Features Outside BBox: **2,012**
  - Total Excluded from South Asia Archive: **5,469**
  - Accounting Invariant: $11,320 = 5,851 + 3,457 + 2,012$ (Verified exact).
* **Traceability & Duplicates:** Space-time deduplication check revealed 0 duplicate observations within the retained subset. 100% of features trace to source CSV timestamps and coordinates.
* **Scientific Caveat:** Detections are **satellite radiometric thermal anomalies**, not ground-truth confirmed fire incidents, and represent a rolling 7-day observation window.

---

## 3. WorldPop Semantic & Statistical Validation Audit

### 3.1 Technical Header & Tag Verification
* **File:** `data/raw/geospatial/population/worldpop/ind_pd_2020_1km.tif` (18,081,300 bytes, SHA-256: `7854911bee96ec61cd56f8209cbc3992bcd13e2aeba7b9d852b76df390f393dc`).
* **Provider:** WorldPop Research Group, University of Southampton (School of Geography and Environmental Science) / CIESIN, Columbia University.
* **Repository:** `https://data.worldpop.org/GIS/Population_Density/Global_2000_2020_1km/2020/IND/ind_pd_2020_1km.tif`
* **Verified Metric:** **Population Density** ($\text{persons}/\text{km}^2$), indicated by the official WorldPop filename token `pd` (contrasted with `ppp` for population per pixel).
* **Dimensions:** 3,508 columns × 3,451 rows ($12,106,108$ total cells).
* **Coordinate Reference System:** EPSG:4326 (WGS 84 geographic coordinates).
* **Pixel Resolution:** Exactly `0.0083333333` degrees (~30 arc-seconds / ~928 meters at equator).
* **Bounding Box:** $[68.182083^\circ\text{E}, 6.749583^\circ\text{N}, 97.415416^\circ\text{E}, 35.507917^\circ\text{N}]$.
* **Valid Data Footprint:** **4,010,402 valid data pixels** (33.13% of raster envelope conforming to India's landmass; NoData = `-99999.0`).
* **Raster Statistics (Valid Pixels):**
  - Minimum: $0.0000$
  - Maximum: $235,668.1406$
  - Mean: $447.0839$
  - Median: $202.0351$
  - Standard Deviation: $1,370.4750$
  - 95th Percentile: $1,420.1323$
  - 99th Percentile: $3,516.8164$

### 3.2 Audit of Maximum Value Location & Interpretation
* **Peak Coordinate:** Longitude $88.3029^\circ\text{E}$, Latitude $22.4871^\circ\text{N}$ (Row 1562, Col 2414).
* **Geographic Placement:** The coordinate falls in the southern urban continuum of Kolkata, West Bengal.
* **Critical Audit Finding on "Plausibility":**  
  While high-density Indian urban wards and informal settlements have historical recorded census densities exceeding $100,000–200,000\text{ persons}/\text{km}^2$, attributing this exact peak of $235,668.14$ to specific ground-truth ward conditions is an **unverified statistical interpretation** of the dasymetric model.  
  WorldPop's unconstrained Random Forest model redistributes administrative census totals onto built-settlement morphological covariates; localized density spikes can emerge as modeling artifacts of covariate weighting.

### 3.3 Separation of Coverage, Semantics, and Estimation Accuracy
To prevent misrepresentation, three concepts are strictly distinguished:
1. **Geographic Coverage:** The raster envelope ($3508 \times 3451$) covers the entire national bounding box, with 4,010,402 valid pixels covering India's landmass. **National geographic extent is established.**
2. **Product Semantics:** Filename (`ind_pd_...`), repository download path (`/Population_Density/`), and embedded GDAL metadata confirm the metric is **modelled population density in persons per square kilometer** ($\text{persons}/\text{km}^2$). **Product semantics are established.**
3. **Estimation Accuracy & Ground-Truth Caveats:**
   - WorldPop produces this surface through a Random Forest dasymetric disaggregation model that redistributes administrative census totals across built-settlement morphological covariates.
   - **National coverage does NOT establish population-estimation accuracy.** No independent ground-truth census enumeration block cross-tabulation or local validation surveys were performed in this evaluation.
   - **Documentation Availability Limitation:** While official provider URLs (`hub.worldpop.org`) and DOIs (`10.5258/SOTON/WP00660`) are cataloged in repository manifests, no local offline copy of the official PDF methodology manual exists in the repository.
* **Conservative Classification:** **`MODELLED_NATIONAL_SURFACE (SEMANTICS_VERIFIED_ACCURACY_UNVERIFIED)`**.
* **Latitude-Dependent Exposure Calculation:**  
  Because pixel area shrinks with latitude ($\text{Area} \approx 0.85\text{ km}^2$ at $8^\circ\text{N}$ vs. $0.70\text{ km}^2$ at $35^\circ\text{N}$), calculating exposed population requires latitude-weighted integration:
  $$\text{Exposed Persons} = \sum_{i} \left( \text{RasterValue}_i \times \left[ (R \cdot \Delta\lambda \cos\phi_i) \times (R \cdot \Delta\phi) \right] \right)$$
  Direct summation of cell values without area weighting is mathematically invalid.

---

## 4. Healthcare Aggregation & Co-Located Records Audit

### 4.1 Input Features & Geometric Integrity
* **Input File:** `data/processed/geospatial/hospitals/india_hospitals_healthcare.geojson` (115,296,859 bytes, SHA-256: `f9cb9a7560dec1acc0e89096f7ecc56bfa6e9360f70e61672851e0b467aa29bc`).
* **Total Features:** 121,613 Point features.
* **Attribute Completeness:** 121,613 features have names (100%); 0 invalid geometries.

### 4.2 State & District Reconciliation
* **Spatial Join Results (STRtree):**
  - Matched within State Boundaries: **121,546 features (99.94%)** across 36 States/UTs.
  - Matched within District Boundaries: **121,546 features (99.94%)** across 641 Census districts.
  - Unmatched Features: **67 features (0.06%)** sitting on coastal tide-line slivers.
  - Sum Check: $121,546 + 67 = 121,613$ (Verified exact).
* **Summary CSV Outputs Generated:**
  - `data/processed/geospatial/healthcare/india_healthcare_state_summary.csv` (36 state rows, SHA-256: `71b262a4d33a69a4746f3325608bfa9d83df24220b331034f55bb8ffb9ffce6e`).
  - `data/processed/geospatial/healthcare/india_healthcare_district_summary.csv` (641 district rows, SHA-256: `611bebe61793dd5a201b1a7dbe05ba47e1ce8cf5610bc1ee4e5e4fa01e74f07e`).
* **Districts with Zero Mapped Facilities (3 Districts):**
  1. Diu District (Daman & Diu, Census Code: `494.0`)
  2. Nicobar District (Andaman & Nicobar Islands, Census Code: `638.0`)
  3. Lakshadweep District (Lakshadweep, Census Code: `587.0`)
* **Infrastructure Reality Caveat:** A mapped facility count of zero reflects community mapping coverage in OpenStreetMap, NOT an absence of operational government hospitals or primary health centres.

### 4.3 Neutral Audit of 3,198 Co-Located Coordinates
* **Physical Inspection of Repeated Coordinates:**
  - Total unique coordinate pairs: 118,415.
  - Total features sharing coordinates: 6,392 across 3,194 distinct locations.
  - Excess co-located records: **3,198**.
* **Inspection of Sample Pairs:**
  - At coordinate `(80.590042, 25.342244)`: Two records both named `"NPHC Kushma"`, both typed as `"centre"`, with distinct UUIDs (`e2c13427...` and `80ca6701...`).
  - At coordinate `(80.915641, 25.341305)`: Two records both named `"Parsaunja"`, both typed as `"centre"`.
* **Resolution of Interpretation:**  
  The previous claim that these 3,198 points represent "separate departments within single hospital compounds" is **unsupported by source tags**. Neutral inspection reveals they are **co-located records sharing identical coordinates**, primarily arising from duplicate volunteer node contributions or repeated batch imports in OpenStreetMap. They are preserved without deduplication to maintain raw provenance traceability.

---

## 5. ERA5 Regional Weather Reference Samples Audit

* **Input File:** `data/raw/geospatial/weather/open_meteo_india_climatic_grid.json` (284,118 bytes).
* **Output Deliverable:** `data/processed/geospatial/weather/india_era5_regional_weather_points.geojson` (7,601 bytes, SHA-256: `dd12febd700a2ed62dab8468e858a6010b9ad61ee3cd63a2fbee953d2abb0e4d`).
* **Locations Audited (6 Reference Points):**
  1. Dehradun (Himalayan Foothills): $30.3339^\circ\text{N}, 77.9719^\circ\text{E}$ (Elev: 656m)
  2. Delhi (Indo-Gangetic Plain): $28.5764^\circ\text{N}, 77.1868^\circ\text{E}$ (Elev: 216m)
  3. Jaipur (Western Arid): $26.8893^\circ\text{N}, 75.8315^\circ\text{E}$ (Elev: 431m)
  4. Bhopal (Central Plateau): $23.2337^\circ\text{N}, 77.4528^\circ\text{E}$ (Elev: 523m)
  5. Mumbai (Western Ghats): $19.0861^\circ\text{N}, 72.8529^\circ\text{E}$ (Elev: 14m)
  6. Kolkata (Eastern Basin): $22.6011^\circ\text{N}, 88.3178^\circ\text{E}$ (Elev: 9m)
* **Temporal Series:** Exactly 360 continuous hourly observations per location from October 1, 2026 00:00 UTC to October 15, 2026 23:00 UTC.
* **Provenance & Strict Description:** ECMWF ERA5 Climate Reanalysis retrieved via Open-Meteo Historical Weather API. They are **ERA5-derived regional reference samples**, NOT physical ground weather stations, and do NOT provide continuous national weather coverage.

---

## 6. Vector vs. Raster Architecture Verification

* **Document Inspected:** `docs/architecture/raster_vector_data_architecture.md`.
* **Verified Distinction:**
  - **Vector Architecture:** Discrete administrative boundaries, roads, rivers, critical facilities, and point thermal anomalies intended for PostGIS tables (`geospatial_features`) with GiST spatial indexing.
  - **Raster Architecture:** Continuous surface grids (WorldPop, Copernicus DEM, ESA WorldCover) maintained as binary GeoTIFF files and accessed via windowed spatial operators.
* **Audit of Implementation Claims:**
  - **Designed vs. Implemented:** The document outlines an architectural specification for Cloud-Optimized GeoTIFF (COG) HTTP range requests.
  - **Current Implementation Reality:** The runtime codebase currently uses **PIL/Pillow** for offline metadata profile extraction. `rasterio` is not installed in the `.venv` and no live HTTP range-request COG streaming client is currently active in runtime services.
  - **Conclusion:** The COG streaming design is an **approved architectural specification for future scaling**, not an existing runtime capability.

---

## 7. Normalization vs. Persistent Ingestion Verification

The 6-stage ingestion progression for the corrected vector layers was independently verified:

| Stage | Fire Stations Clipped (146) | NASA FIRMS Clipped (5,851) | ERA5 Weather Points (6) | Evidence Source |
| :--- | :---: | :---: | :---: | :--- |
| **1. GeoJSON Parsing** | **PASSED** | **PASSED** | **PASSED** | Valid JSON & Shapely Points |
| **2. Pydantic `NormalizedFeature`** | **PASSED** (146/146) | **PASSED** (5,851/5,851) | **PASSED** (6/6) | `scratch/test_ingestion_schemas.py` |
| **3. Normalizer Pipeline Acceptance** | **PASSED** | **PASSED** | **PASSED** | `normalizer_pipeline.py` |
| **4. Batch Ingestion Staging** | **PASSED** (Dry-run) | **PASSED** (Dry-run) | **PASSED** (Dry-run) | Ingestion CLI dry-run |
| **5. PostGIS Database Persistence** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | Port 5432 Offline (`Permission denied`) |
| **6. Live Spatial Query Roundtrip** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | Cannot query unpersisted DB |

> [!IMPORTANT]
> **Definitive Rule:** Successful schema validation and dry-run acceptance **do NOT constitute database persistence**. Zero records have been committed to PostgreSQL/PostGIS.

---

## 8. Historical Asset Preservation Audit

Cryptographic SHA-256 verification against baseline inventories confirmed zero unintended modifications across distinct preservation categories:

### 8.1 ML Model Checkpoints (`artifacts/checkpoints/`)
* `baseline_cnn_best.pt` (4,916,877 bytes) — `76544190318f1300b2b48e8ede5062b8fa712368e246d52611bdf4adb035150e` [VERIFIED]
* `baseline_cnn_last.pt` (4,916,877 bytes) — `eb5725ebc72466d778cd239fde4ed6dca382b9799d3c05e5df8d5135221202b4` [VERIFIED]
* `mobilenet_v3_small_stage1_best.pt` (10,998,699 bytes) — `8f7878c47512266719b203958bba94612b44af5ccfe67c7223bace2952ad9d3a` [VERIFIED]
* `mobilenet_v3_small_stage1_last.pt` (10,998,699 bytes) — `86d0a7dbae585c32ed1e99871b3b3dc15712adb156793d2ef531aecaec929ba5` [VERIFIED]
* `mobilenet_v3_small_stage2_best.pt` (16,928,947 bytes) — `278250a69570e2bf024e48e87e345b6d4a75cf25ec4d0e887194a8e5063fccd1` [VERIFIED]
* `mobilenet_v3_small_stage2_last.pt` (16,928,947 bytes) — `c6b3aecba0713596a68d268259978b539efc5a58f11415f228b325cdf99469fb` [VERIFIED]

### 8.2 Historical Image Dataset (`data/processed/fire_smoke_v2/`)
* Total Processed Images: **3,507 files** intact across train/val/test splits with 0 modifications.

### 8.3 Historical Reports vs. M10 Audit Deliverables
To ensure complete transparency, reports are categorized by provenance:
1. **Unchanged Historical Reports (M05–M09 & Early M10):**
   - `milestone_05_final_correction_report.md` (13,009 bytes, SHA: `df622179642efe3a...`) [INTACT]
   - `milestone_06_final_correction_report.md` (32,358 bytes, SHA: `c30c545e72c3793c...`) [INTACT]
   - `milestone_07_final_correction_report.md` (42,553 bytes, SHA: `4735b6aec8c519d1...`) [INTACT]
   - `docs/reports/milestone_10_implementation_report.md` (17,096 bytes, SHA: `ff5b7ceb6252...`) [INTACT]
   - `docs/reports/national_data_acquisition_report.md` (12,248 bytes, SHA: `7a6fd2015683...`) [INTACT]
   - `docs/reports/national_data_acquisition_independent_audit.md` (34,692 bytes, SHA: `5cd92b17d67f...`) [INTACT]
   - All 25 historical reports in `docs/reports/` match baseline inventory SHA-256 hashes byte-for-byte.
2. **Intentionally Edited Report:**
   - `docs/reports/m10_data_quality_correction_report.md`: Updated during this closeout audit to reconcile test contradictions, WorldPop classifications, and boundary terminology.
3. **Newly Created Deliverable:**
   - `docs/reports/m10_closeout_evidence_appendix.md`: Authored during this closeout audit as the master evidence matrix.

### 8.4 Raw Geospatial Source Assets (`data/raw/geospatial/`)
* All 14 raw geospatial source files match pre-correction inventory SHA-256 hashes byte-for-byte.

---

## 9. Git Repository State & Audit Limitations

* **Working-Tree Status (`git status --short`):**
  - Tracked modifications: 9 files (`.env.example`, `.gitignore`, `README.md`, `backend/app/api/v1/router.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/requirements.txt`, `backend/tests/conftest.py`, `backend/tests/unit/test_config.py`).
  - Untracked files: platform source packages (`backend/`, `data/`, `docs/`, `frontend/`, `infrastructure/`, `ml/`) and root milestone reports exist as working directory files.
* **Commit History (`git log --oneline --decorate -n 20`):**
  - Exactly 1 commit exists on `main`: `65f8933 (HEAD -> main) chore: initialize SCOUT project foundation`.
* **Reference Movement History (`git reflog -n 30`):**
  - Exactly 1 entry: `65f8933 HEAD@{0}: commit (initial): chore: initialize SCOUT project foundation`.
* **Remote Tracking Status (`git remote -v`):**
  - No remote repository (e.g. `origin`) is configured in this local repository clone. `git remote -v` produces zero output. `git ls-remote origin refs/heads/main` cannot be executed due to the absence of a configured remote.
* **Truthful Git Evidence Boundary:**
  - The evidence verifies that no commits, branch switches, stashes, or resets occurred locally during this audit session.
  - No push to a remote server was possible or executed from this repository instance.
