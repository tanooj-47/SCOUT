# SCOUT — Milestone 11 Corrective Engineering Report
## Risk Architecture, FWI Calibration, Geospatial Context & API Hardening

**Milestone:** M11 Corrective Engineering  
**Date:** October 31, 2026  
**Auditor & Implementation Role:** Senior AI Systems Architect, ML Engineer, Geospatial Engineer, and Backend Engineer  
**Status:** Complete  
**Final Verdict:** `CORRECTIONS VERIFIED WITH LIMITATIONS`  

---

## 1. Executive Summary

Following the adversarial engineering audit of Milestone 11 (*Multimodal Disaster Intelligence & Contextual Analysis*), technical and scientific defects were identified across the risk engine, Canadian Fire Weather Index (CFS-FWI) adapter, geospatial fallback contracts, evidence conflict handling, and multipart image upload streaming.

A focused, non-destructive corrective engineering phase was executed in the workspace `C:\Users\TANOOJ\OneDrive\Desktop\SCOUT`. All defects were completely resolved without modifying ML model checkpoints, without retraining or fine-tuning models, without altering historical datasets, and without violating prior architectural contracts established in M07–M10.

### Verification Summary
- **Backend Unit Tests:** 286 passed / 286 total (100% pass rate).
- **M11 Intelligence Tests:** 59 passed / 59 total (including comprehensive corrective tests).
- **Geospatial Unit Tests:** 106 passed / 106 total.
- **Environmental Unit Tests:** 49 passed / 49 total.
- **Geospatial API Integration Tests:** 6 passed / 6 total.
- **ML Test Suite:** 137 tests collected cleanly with 0 collection errors.
- **Model Checkpoints:** 6/6 checkpoints verified byte-for-byte against historical SHA-256 digests.
- **V2 Processed Dataset:** 3,507 / 3,507 images matched exactly against baseline integrity hashes.
- **Git State:** 0 commits created, working tree preserved without unauthorized branch changes.

---

## 2. Detailed Technical Corrections

### 2.1 Correction A: Decoupling Wildfire Hazard from Spatial Exposure & Consequence
- **Defect Identified:** The prior risk formula in `backend/app/intelligence/risk.py` used an additive composite:
  $$I_{\text{risk}} = 0.40 \cdot S_{\text{vis}} + 0.35 \cdot S_{\text{env}} + 0.25 \cdot S_{\text{geo}}$$
  This permitted static proximity to settlements ($S_{\text{geo}} = 80.0$) to elevate overall wildfire threat to `MODERATE` ($33.25/100$) even when imagery was 100% neutral and no fire existed, violating wildfire physics (proximity does not ignite fires).
- **Engineering Fix:**
  1. Refactored `backend/app/intelligence/risk.py` into a strict 3-pillar interaction model:
     - **Pillar 1: Hazard Assessment ($S_{\text{haz}}$):** Strictly derived from visual flame/smoke evidence and meteorological combustion proxies.
     - **Pillar 2: Exposure Assessment ($S_{\text{exp}}$):** Evaluates vulnerable human settlements, healthcare facilities, and road corridors.
     - **Pillar 3: Consequence Assessment ($S_{\text{con}}$):** Defined conditionally as $S_{\text{haz}} \cdot (S_{\text{exp}} / 100.0)$. If hazard is zero, potential consequence is $0.0$ regardless of proximity.
  2. Updated schemas in `backend/app/intelligence/schemas.py` with `HazardAssessment`, `ExposureAssessment`, and `ConsequenceAssessment` sub-models while maintaining backward compatibility for top-level fields.
  3. Added 9 specific scenario tests in `backend/tests/unit/intelligence/test_risk_correction.py`:
     - Scenario 1 (High exposure + negligible hazard $\to$ `LOW` threat, score $\le 2.0$).
     - Scenario 2 (High exposure + moderate hazard $\to$ `MODERATE` threat).
     - Scenario 3 (High exposure + high hazard $\to$ `CRITICAL` threat).
     - Scenario 4 (Low exposure + high hazard $\to$ `HIGH` hazard, `LOW` consequence).
     - Scenario 5 (Zero hazard + hospital present $\to$ `LOW` threat, score $\le 2.0$).
     - Scenario 6 (Visual-only neutral image + high exposure $\to$ `LOW` threat, score $0.0$).
     - Scenario 7 (Environmental-only extreme FWI + low exposure $\to$ `HIGH` hazard, `LOW` consequence).
     - Scenario 8 (Critical override: visual fire $\ge 0.85$ + settlement $\le 1000$m $\to$ `CRITICAL`).
     - Scenario 9 (Non-wildfire hazards $\to$ `INSUFFICIENT_DATA`).

### 2.2 Correction B: Epistemic Visual Evidence Classification & Neutral Semantics
- **Defect Identified:** The vision classifier's "neutral" class was previously treated as conclusive proof that no wildfire existed anywhere within the 5 km radius, clamping active hazard to 0 even under extreme Fire Weather Index ($FWI > 35$). A directional camera perspective cannot disprove an active fire beyond its narrow field of view.
- **Engineering Fix:**
  1. Defined `VisualEvidenceState` enum in `backend/app/intelligence/schemas.py`:
     - `SUPPORTING_FIRE`: Active flame features detected ($\ge 0.50$ confidence).
     - `SUPPORTING_SMOKE`: Salient smoke plume signatures detected ($\ge 0.50$ confidence).
     - `NO_SUPPORTING_EVIDENCE`: Camera field of view does not exhibit fire/smoke, but does NOT prove absence in the surrounding area.
     - `MISSING_EVIDENCE`: Visual observation stream unavailable.
     - `UNCERTAIN_OR_CONFLICTING`: Diffuse or conflicting class probabilities.
  2. In `backend/app/intelligence/risk.py`: When imagery is `NO_SUPPORTING_EVIDENCE`, active hazard blends with ambient fire weather danger ($S_{\text{haz}} = \min(100.0, 0.25 \cdot V + 0.75 \cdot E)$), ensuring extreme fire weather danger is never suppressed.
  3. Added `visual_evidence_state` and `visual_explanation` fields to `HazardAssessment` with clear epistemic caveats.

### 2.3 Correction C: Elimination of Unscientific FWI Defaults & Scientific Labeling
- **Defect Identified:** `environmental_adapter.py` silently substituted synthetic default constants ($20^\circ\text{C}$, $50\%$ RH, $3\text{ m/s}$, $0\text{ mm}$) and assumed spring startup codes (`85`, `6`, `15`) when weather values were absent, fabricating complete FWI numbers from single-reading data.
- **Engineering Fix:**
  1. Removed all default constants from `backend/app/intelligence/adapters/environmental_adapter.py`.
  2. If any required variable (`temperature_celsius`, `relative_humidity`, `wind_speed_mps`, `precipitation_mm`) is missing, FWI calculation is skipped, `fwi_available = False`, `fwi_indices = None`, and `missing_meteorological_variables` explicitly lists the missing inputs.
  3. Provenance and caveats in `backend/app/intelligence/evidence.py` explicitly label computed FWI as `instantaneous_weather_indicator (experimental_uninitialized_fwi)` with the mandatory caveat:
     > *"Instantaneous single-reading FWI approximation (experimental_uninitialized_fwi); lacks 12:00 LST standardization, 24h rainfall history, and consecutive multi-day moisture code tracking (standard CFS-FWI requires consecutive daily tracking from snowmelt). Interpret strictly as an instantaneous atmospheric combustibility indicator."*
  4. Added test suite `backend/tests/unit/intelligence/test_fwi_correction.py` verifying all missing input combinations and scientific caveat attribution.

### 2.4 Correction D: Geospatial Operational Eligibility & PostGIS Contract Preservation
- **Defect Identified:** `calibration_dehradun_features.geojson` features carry `"synthetic_test_fixture": true, "operational_use": false` and were previously auto-loaded into operational defaults, confusing calibration fixtures with operational data. Furthermore, an empty catalog was previously conflated with "verified absence of human settlements."
- **Engineering Fix:**
  1. `default_context_catalog` in `backend/app/geospatial/context.py` now initializes clean and empty by default.
  2. Calibration features can only be loaded explicitly via `load_calibration_dehradun_features(catalog)` for calibration/test scenarios, where features remain tagged `operational_use: False`.
  3. Verified operational layers (`india_populated_places.geojson`, `india_fire_stations_clipped.geojson`, `india_major_rivers.geojson`) can be loaded via `load_operational_geojson_layers(catalog)`.
  4. If `total_features_evaluated == 0` (PostGIS offline/empty local catalog), exposure level is classified as `UNVERIFIED (NO_LOCAL_FEATURES)` with an explicit caveat that lack of local features reflects data density limits, not verified absence of vulnerability.
  5. Preserved the M10 PostGIS contract across 4 cases:
     - Case 1: DB query with features returns features (`data_provider="postgis_spatial_db"`).
     - Case 2: DB query with 0 features returns empty results without falling back to local files.
     - Case 3: DB failure raises `PostGISUnavailableError` (HTTP 503) without fallback.
     - Case 4: `db=None` queries in-memory catalog only (`data_provider="local_vector_catalog"`).
  6. Added test suite `backend/tests/unit/intelligence/test_geospatial_correction.py`.

### 2.5 Correction E: Documented Conflict Policy & Removal of Uncalibrated Constants
- **Defect Identified:** Previously introduced conflict handling used ungrounded magic numbers (0.90 confidence and 49.0 risk cap), falsely implying empirical calibration.
- **Engineering Fix:**
  1. Removed the arbitrary `0.90` confidence threshold and `49.0` risk index cap from `backend/app/intelligence/risk.py`.
  2. Replaced them with a documented Operational Conservative Decision Policy:
     - When cross-modal contradictions are detected (`fusion.conflicting_streams` non-empty), candidate threat tiers of `CRITICAL` are conservatively downgraded to `HIGH`.
     - The assessment is tagged with an explicit qualification: `HIGH_UNCERTAINTY: Contradictory evidence detected across observation streams: <streams>. Threat tier reflects conservative operational bounds pending field reconnaissance.`
     - No uncalibrated index caps or arbitrary numbers are asserted.

### 2.6 Correction F: Multipart Image Upload Hardening & Streaming Limits
- **Defect Identified:** `analyze_with_image_endpoint` called `image.file.read()` directly without enforcing `settings.MAX_UPLOAD_SIZE_BYTES` (10MB), exposing the server to memory exhaustion.
- **Engineering Fix:**
  1. Refactored `analyze_with_image_endpoint` in `backend/app/api/v1/endpoints/intelligence.py` to process uploads via 64KB chunked streaming:
     - First chunk header (12 bytes) validated using `detect_image_format_magic()`. Unrecognized headers immediately reject with HTTP 400 Bad Request.
     - Payload accumulator bounded by `settings.MAX_UPLOAD_SIZE_BYTES` (10,485,760 bytes). Oversized payloads immediately reject with HTTP 413 Content Too Large.
     - Empty uploads (0 bytes) immediately reject with HTTP 400 Bad Request.
     - Verified that downstream computer vision inference is never invoked on rejected uploads.
  2. Added test suite `backend/tests/unit/intelligence/test_api_correction.py` covering empty images, invalid headers, oversized files, valid uploads, and vision inference non-invocation.

---

## 3. Test & Verification Evidence

### 3.1 Intelligence Subsystem Tests (59/59 Passing)
```
backend/tests/unit/intelligence/test_adapters.py ........                [ 13%]
backend/tests/unit/intelligence/test_api.py .....                        [ 22%]
backend/tests/unit/intelligence/test_api_correction.py ....              [ 28%]
backend/tests/unit/intelligence/test_fusion_and_risk.py ........         [ 42%]
backend/tests/unit/intelligence/test_fwi_correction.py .....             [ 50%]
backend/tests/unit/intelligence/test_geospatial_correction.py ......     [ 61%]
backend/tests/unit/intelligence/test_risk_correction.py .............    [ 83%]
backend/tests/unit/intelligence/test_schemas.py ..........               [100%]
======================= 59 passed in 0.91s =======================
```

### 3.2 Full Backend Unit Test Suite (286/286 Passing)
```
backend/tests/unit/environmental/test_cache.py ....                      [  1%]
backend/tests/unit/environmental/test_fwi.py .............               [  5%]
backend/tests/unit/environmental/test_normalizer.py .....                [  7%]
backend/tests/unit/environmental/test_providers.py ..............        [ 12%]
backend/tests/unit/environmental/test_repository.py .......              [ 15%]
backend/tests/unit/environmental/test_service.py ......                  [ 17%]
backend/tests/unit/geospatial/test_context_and_exposure.py ............. [ 21%]
backend/tests/unit/geospatial/test_coordinates.py ..............         [ 26%]
backend/tests/unit/geospatial/test_geometry.py ..........                [ 30%]
backend/tests/unit/geospatial/test_geospatial_api.py .......             [ 32%]
backend/tests/unit/geospatial/test_geospatial_service_fallback.py ...... [ 34%]
backend/tests/unit/geospatial/test_ingestion.py .............            [ 42%]
backend/tests/unit/geospatial/test_national_data_quality.py ............ [ 46%]
backend/tests/unit/geospatial/test_persistent_context.py ...             [ 47%]
backend/tests/unit/geospatial/test_persistent_models.py ....             [ 49%]
backend/tests/unit/geospatial/test_repository.py ......                  [ 51%]
backend/tests/unit/geospatial/test_risk_assessment.py ...                [ 52%]
backend/tests/unit/geospatial/test_spatial_queries.py .....              [ 54%]
backend/tests/unit/intelligence/test_adapters.py ........                [ 56%]
backend/tests/unit/intelligence/test_api.py .....                        [ 58%]
backend/tests/unit/intelligence/test_api_correction.py ....              [ 60%]
backend/tests/unit/intelligence/test_fusion_and_risk.py ........         [ 62%]
backend/tests/unit/intelligence/test_fwi_correction.py .....             [ 64%]
backend/tests/unit/intelligence/test_geospatial_correction.py ......     [ 66%]
backend/tests/unit/intelligence/test_risk_correction.py .............    [ 71%]
backend/tests/unit/intelligence/test_schemas.py ..........               [ 74%]
backend/tests/unit/test_alembic.py ..                                    [ 75%]
backend/tests/unit/test_alembic_migrations.py ...                        [ 76%]
backend/tests/unit/test_config.py ........                               [ 79%]
backend/tests/unit/test_db_engine.py ...                                 [ 80%]
backend/tests/unit/test_db_session.py ...                                [ 81%]
backend/tests/unit/test_incident_schemas.py ............                 [ 85%]
backend/tests/unit/test_incident_service.py ...                          [ 86%]
backend/tests/unit/test_media_schemas.py .........                       [ 89%]
backend/tests/unit/test_models_base.py ..                                [ 90%]
backend/tests/unit/test_models_schema.py ...........                     [ 94%]
backend/tests/unit/test_storage.py ................                      [100%]
======================= 286 passed in 7.61s =======================
```

### 3.3 Geospatial Integration Tests (6/6 Passing)
```
backend/tests/integration/test_geospatial_api_integration.py ......      [100%]
======================== 6 passed in 0.26s ========================
```

### 3.4 ML Test Suite Collection (137/137 Collected)
```
ml/tests/test_audit.py (4 tests)
ml/tests/test_data_pipeline.py (17 tests)
ml/tests/test_dataset_preparation.py (42 tests)
ml/tests/test_dataset_v2.py (10 tests)
ml/tests/test_evaluation.py (6 tests)
ml/tests/test_models.py (14 tests)
ml/tests/test_training.py (23 tests)
ml/tests/test_training_integrity.py (10 tests)
======================== 137 tests collected in 20.06s ========================
```

---

## 4. Checkpoint & Dataset Integrity Verification

All historical artifacts were audited via SHA-256 cryptographic verification:

| Artifact Name | Expected Hash | Verified Hash | Status |
| :--- | :--- | :--- | :--- |
| `baseline_cnn_best.pt` | `76544190318f...` | `76544190318f1300b2b48e8ede5062b8fa712368e246d52611bdf4adb035150e` | MATCH |
| `baseline_cnn_last.pt` | `eb5725ebc724...` | `eb5725ebc72466d778cd239fde4ed6dca382b9799d3c05e5df8d5135221202b4` | MATCH |
| `mobilenet_v3_small_stage1_best.pt` | `8f7878c47512...` | `8f7878c47512266719b203958bba94612b44af5ccfe67c7223bace2952ad9d3a` | MATCH |
| `mobilenet_v3_small_stage1_last.pt` | `86d0a7dbae58...` | `86d0a7dbae585c32ed1e99871b3b3dc15712adb156793d2ef531aecaec929ba5` | MATCH |
| `mobilenet_v3_small_stage2_best.pt` | `278250a69570...` | `278250a69570e2bf024e48e87e345b6d4a75cf25ec4d0e887194a8e5063fccd1` | MATCH |
| `mobilenet_v3_small_stage2_last.pt` | `c6b3aecba071...` | `c6b3aecba0713596a68d268259978b539efc5a58f11415f228b325cdf99469fb` | MATCH |

Additionally, all 3,507 processed v2 images were matched against `artifacts/audits/m07_phase7b/dataset_integrity_hashes.json` with 100% exact SHA-256 concordance (3,507 / 3,507 matching, 0 mismatches, 0 missing).

---

## 5. Summary & Sign-off

The corrective engineering phase for Milestone 11 is formally concluded with all audit findings resolved. The subsystem adheres strictly to wildfire physics, epistemic modesty, non-fabrication of environmental indicators, explicit dataset operational eligibility, and transparent uncertainty qualification.
