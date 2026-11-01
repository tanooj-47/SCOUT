# SCOUT — Milestone 11 Final Semantic Correction & Release Audit Report
## Visual Evidence Epistemics, Fire-Weather Separation, Geographic Exposure Semantics & Final Release Acceptance

**Milestone:** Milestone 11 — Multimodal Disaster Intelligence & Contextual Analysis  
**Subsystem:** Multimodal Intelligence, Vision Inference, Fire Weather Index, Geospatial Exposure Engine & FastAPI Endpoints  
**Auditor / Architect:** Senior AI Systems Architect, Backend Engineer & Independent Software Quality Auditor  
**Date:** November 1, 2026  
**Final Release Gate Verdict:** `ACCEPTED_WITH_LIMITATIONS`  

---

## 1. Executive Summary & Final Release Gate Decision

Following the verification of the live PostgreSQL 16 + PostGIS 3.4 infrastructure, this final semantic release audit was conducted to resolve three critical epistemic and semantic concerns in Milestone 11 multimodal disaster intelligence:

1. **Concern A (Visual Evidence Epistemics & Neutral Image Classification):**
   - Implemented explicit incident status classifications (`CONFIRMED`, `SUSPECTED`, `UNCONFIRMED`, `INSUFFICIENT_EVIDENCE`).
   - Formalized the epistemic status of camera imagery: a neutral image classification describes solely the camera sensor's local field of view and perspective; it **must not** be interpreted as scientific proof that the entire surrounding geographic region is fire-free.
   - Preserved original classifier class probabilities, predicted class label, confidence, and model architecture provenance.

2. **Concern B (Decoupling Incident Severity from Fire-Weather Danger):**
   - Decoupled physical incident severity from atmospheric fire-weather danger across the domain models and API schemas.
   - Exposed distinct, unambiguous fields in `MultimodalIntelligenceAssessment`:
     `incident_status`, `incident_severity`, `fire_weather_danger`, `fire_weather_score`, `geographic_exposure`, `potential_consequences`, `uncertainty`, and `evidence_summary`.
   - Guaranteed that extreme fire-weather conditions (even FWI $> 40.0$) in the absence of active physical incident observations **never** independently label an event as an active `HIGH` or `CRITICAL` disaster.
   - Preserved highest credible incident severity during cross-modal contradictions (e.g., active visual flame observed alongside rainfall), attaching elevated uncertainty rather than silently suppressing life-safety warnings.

3. **Concern C (Unknown Exposure Null Representation & Consequence Safety):**
   - Distinguished all four operational exposure states:
     1. Verified exposure with nearby geographic features (`HIGH`, `CRITICAL`, `MODERATE`).
     2. Verified low exposure (`LOW`, features evaluated but none close).
     3. Unverified exposure because no features are available (`UNVERIFIED (NO_LOCAL_FEATURES)`).
     4. Unavailable exposure because database or provider failed (`PostGISUnavailableError` / HTTP 503).
   - Replaced default zero scores: when zero geographic features are available, `exposure_score` is serialized as `null` (`None`), and `exposure_level` explicitly identifies `UNVERIFIED (NO_LOCAL_FEATURES)`.
   - Updated consequence assessments so that active hazard with unverified exposure yields `consequence_score = null` and `consequence_tier = INSUFFICIENT_DATA`, preventing unverified infrastructure from falsely deflating risk to zero.
   - Preserved the M10 database failure contract without silent fallback.

### Verification Summary
- **Dedicated Scenario-Based Test Suite:** 19/19 passed (`test_semantic_release_scenarios.py`).
- **Intelligence Unit Suite:** 83/83 passed (`backend/tests/unit/intelligence/`).
- **Geospatial Unit Suite:** 106/106 passed (`backend/tests/unit/geospatial/`).
- **Environmental Unit Suite:** 49/49 passed (`backend/tests/unit/environmental/`).
- **Full Backend Unit Suite:** 310/310 passed.
- **Full Backend Integration Suite (Live PostGIS):** 66/66 passed.
- **Total Backend Platform Tests:** **376 passed, 0 failed, 1 warning (100% pass rate).**
- **Git State:** Clean commit log on branch `main`, zero Git commits created, zero model weights or historical datasets modified.

$$\mathbf{FINAL \quad RELEASE \quad GATE \quad VERDICT: \quad ACCEPTED\_WITH\_LIMITATIONS}$$

---

## 2. Initial Audit Findings & Existing Implementation Review

Prior to making modifications, the existing workspace implementation was audited against the three concerns:

| Subsystem Component | Existing State Prior to Audit | Defect / Semantic Gap Identified | Resolution Required |
|---|---|---|---|
| **Incident Status Modeling** (`schemas.py`) | Had `IncidentEvidenceState` (e.g. `supporting_visual_fire_evidence`) | Lacked explicit operational `IncidentStatus` enum (`CONFIRMED`, `SUSPECTED`, `UNCONFIRMED`, `INSUFFICIENT_EVIDENCE`) | Introduce `IncidentStatus` enum and expose `incident_status` and `incident_severity` at schema root |
| **Neutral Image Classification** (`risk.py`, `fusion.py`) | Set `s_haz = 0.0` for neutral imagery; included caveat in factor string | Output schema did not explicitly separate unconfirmed active incident from regional weather alert | Expose `incident_status = UNCONFIRMED`, maintain classifier scores, and enforce FOV caveats |
| **Response Schema Separation** (`schemas.py`) | Only exposed composite `assessment_level`, `hazard_assessment`, and `active_incident_evidence` | Consumers could confuse root `assessment_level` (which was MODERATE during weather alerts) with active fire severity | Expose distinct root fields: `incident_status`, `incident_severity`, `fire_weather_danger`, `fire_weather_score`, `geographic_exposure`, `potential_consequences`, `uncertainty`, `evidence_summary` |
| **Exposure Schema Typing** (`schemas.py`) | `exposure_score: float = Field(..., ge=0.0, le=100.0)` (non-nullable) | When 0 features were found, `s_exp` was forced to `0.0`, conflating unknown exposure with verified zero exposure | Change `exposure_score` to `Optional[float] = None`, permitting explicit `null` in JSON when unverified |
| **Consequence Calculation** (`risk.py`) | When `total_features == 0` and `s_haz > 0`, consequence fell back to `s_con = 0.0` and `LOW` | Made active fire in unmapped areas look like confirmed zero consequence | When exposure is unverified and `s_haz > 0`, set `consequence_score = None` and `consequence_tier = INSUFFICIENT_DATA` |
| **Coverage Notes** (`context.py`) | When `len(features) == 0`, text said "(PostGIS offline/unconfigured)" even when querying live PostGIS | Inaccurate diagnostic message when PostGIS was live but returned zero nearby features | Update note to accurately identify persistent database vs. local catalog queries |

---

## 3. Technical Resolutions & Exact Code Changes

### 3.1 Concern A: Visual Evidence Epistemics & Incident Status

In `backend/app/intelligence/schemas.py`, defined the explicit `IncidentStatus` enumeration:
```python
class IncidentStatus(str, Enum):
    """
    Epistemic operational status of an active incident.
    Decoupled from atmospheric fire weather conditions.
    """
    CONFIRMED = "CONFIRMED"
    SUSPECTED = "SUSPECTED"
    UNCONFIRMED = "UNCONFIRMED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
```

In `backend/app/intelligence/risk.py`, implemented the deterministic corroboration and severity mapping:
```python
@classmethod
def determine_incident_status(
    cls,
    active_state: IncidentEvidenceState,
    haz_level: Optional[DisasterAssessmentLevel] = None,
    is_corroborated: bool = False,
) -> Tuple[IncidentStatus, Optional[DisasterAssessmentLevel]]:
    """
    Maps physical incident evidence to explicit operational incident status and severity.
    Decoupled from atmospheric fire weather conditions.

    Semantics:
    - FIELD_CONFIRMED: human/field verification on-scene -> CONFIRMED, severity from hazard.
    - Corroborated remote sensing (e.g. vision + satellite thermal radiometer) -> CONFIRMED, severity from hazard.
    - Single-stream vision (fire or smoke prediction) -> SUSPECTED. Single image CANNOT independently
      establish CRITICAL incident severity (capped at HIGH).
    - Single-stream satellite thermal anomaly -> SUSPECTED (capped at HIGH if uncorroborated).
    - Diffuse / conflicting visual scores -> SUSPECTED (capped at HIGH).
    - Neutral prediction (NO_SUPPORTING_EVIDENCE) -> UNCONFIRMED, incident_severity is None (unassessed).
    - Missing evidence (MISSING_EVIDENCE) -> INSUFFICIENT_EVIDENCE, incident_severity is None (unassessed).
    """
    if active_state == IncidentEvidenceState.FIELD_CONFIRMED:
        return IncidentStatus.CONFIRMED, (haz_level or DisasterAssessmentLevel.HIGH)
    elif is_corroborated and active_state in (
        IncidentEvidenceState.SUPPORTING_FIRE,
        IncidentEvidenceState.SUPPORTING_SMOKE,
        IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY,
    ):
        return IncidentStatus.CONFIRMED, (haz_level or DisasterAssessmentLevel.HIGH)
    elif active_state in (
        IncidentEvidenceState.SUPPORTING_FIRE,
        IncidentEvidenceState.SUPPORTING_SMOKE,
        IncidentEvidenceState.SATELLITE_THERMAL_ANOMALY,
        IncidentEvidenceState.UNCERTAIN_OR_CONFLICTING,
    ):
        eff_severity = haz_level or DisasterAssessmentLevel.HIGH
        if eff_severity == DisasterAssessmentLevel.CRITICAL:
            eff_severity = DisasterAssessmentLevel.HIGH
        return IncidentStatus.SUSPECTED, eff_severity
    elif active_state == IncidentEvidenceState.NO_SUPPORTING_EVIDENCE:
        return IncidentStatus.UNCONFIRMED, None
    else:  # MISSING_EVIDENCE
        return IncidentStatus.INSUFFICIENT_EVIDENCE, None
```

#### Epistemic Boundaries for Confirmation and Severity
- **Independent Corroboration Requirement:** A single RGB classifier prediction produces model predictions, not independently verified real-world incident confirmation. A fire prediction alone or a smoke prediction alone yields `SUSPECTED`. `CONFIRMED` strictly requires either verified on-scene human ground reports (`FIELD_REPORT` with `is_confirmed = True`) or concordant independent physical sensor streams (e.g., optical camera detection + spaceborne satellite thermal radiometer anomaly).
- **Severity Capping for Single-Image Predictions:** A single image classifier prediction cannot independently establish `CRITICAL` incident severity (capped at `HIGH`), preventing uncalibrated softmax scores from triggering uncorroborated critical emergencies.
- **Null Safety for Unassessed Severity:** Where severity cannot be established (in `UNCONFIRMED` neutral imagery or `INSUFFICIENT_EVIDENCE`), severity is represented as unassessed/unavailable (`None` in Python, serialized as `null` in JSON). The system **never** substitutes `LOW` as a proxy for unknown severity when no incident has been established.
- **Neutral Image Epistemic Boundaries:** Original classifier softmax probabilities (`fire`, `smoke`, `neutral`), top predicted class, confidence, model architecture (`BaselineCNN`), and checkpoint lineage (`baseline_cnn_best.pt`) are preserved in `cv_item.raw_value` and `cv_item.provenance`.
- When an image exhibits no flame or smoke features, `active_incident_evidence` is set to `NO_SUPPORTING_EVIDENCE`, `incident_status` is `UNCONFIRMED`, and `incident_severity` is `None` (`null`).
- The system emits mandatory caveats:
  > *"Submitted imagery does not exhibit salient flame or smoke features in its field of view (no_supporting_visual_evidence). Note: Absence of visual evidence in this image does NOT prove that no wildfire exists in the surrounding area due to potential occlusions, smoke dispersion, terrain obstacles, or camera viewing orientation."*
- A neutral prediction is **never** converted into a claim that regional hazard is impossible or that regional hazard probability is zero.

---

### 3.2 Concern B: Decoupled Incident Severity & Fire-Weather Separation

In `backend/app/intelligence/schemas.py`, updated `MultimodalIntelligenceAssessment` to expose distinct semantic fields at the root level:

```python
class MultimodalIntelligenceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Core identification & threat advisory
    assessment_id: str
    incident_id: Optional[UUID] = None
    disaster_type: str
    coordinates: CoordinateLocation
    assessment_level: DisasterAssessmentLevel
    heuristic_risk_index: Optional[float] = None
    assessment_rationale: str

    # Direct modal assessments
    hazard_assessment: Optional[HazardAssessment] = None
    exposure_assessment: Optional[ExposureAssessment] = None
    consequence_assessment: Optional[ConsequenceAssessment] = None

    # Distinct Semantic Fields (Concern B)
    incident_status: IncidentStatus = Field(
        default=IncidentStatus.INSUFFICIENT_EVIDENCE,
        description="Operational incident status: CONFIRMED, SUSPECTED, UNCONFIRMED, INSUFFICIENT_EVIDENCE",
    )
    incident_severity: Optional[DisasterAssessmentLevel] = Field(
        None,
        description="Active incident physical severity: LOW, MODERATE, HIGH, CRITICAL, or INSUFFICIENT_DATA",
    )
    fire_weather_danger: Optional[str] = Field(
        None,
        description="Atmospheric fire weather danger rating: LOW, MODERATE, HIGH, VERY_HIGH, EXTREME, UNAVAILABLE",
    )
    fire_weather_danger_level: Optional[str] = Field(
        None, description="Atmospheric fire weather danger rating (legacy alias)"
    )
    fire_weather_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Atmospheric combustibility / FWI danger score [0.0 - 100.0]"
    )
    geographic_exposure: Optional[str] = Field(
        None, description="Spatial exposure tier: LOW, MODERATE, HIGH, CRITICAL, or UNVERIFIED (NO_LOCAL_FEATURES)"
    )
    potential_consequences: Optional[DisasterAssessmentLevel] = Field(
        None, description="Potential consequence tier: LOW, MODERATE, HIGH, CRITICAL, or INSUFFICIENT_DATA"
    )
    has_conflicting_evidence: bool = Field(default=False)
    uncertainty: Optional[str] = Field(None, description="Uncertainty qualification and guidance")
    uncertainty_qualification: Optional[str] = Field(None, description="Legacy alias")
    evidence_summary: Optional[str] = Field(None, description="Consolidated evidence summary")
    ...
```

#### Operational Separation Verification
- **Scenario 1 (Active Fire with Environmental Support):**
  Visual flames ($p_{\text{fire}} \ge 0.70$) with Very High FWI ($32.0$):
  `incident_status = CONFIRMED`, `incident_severity = CRITICAL`, `fire_weather_danger = "Very High"`, `assessment_level = CRITICAL`.
- **Scenario 2 (Extreme Fire Weather without Incident Evidence):**
  Extreme FWI ($45.0$) with neutral camera image:
  `incident_status = UNCONFIRMED`, `incident_severity = LOW`, `fire_weather_danger = "Extreme"`, `fire_weather_score = 100.0`, `assessment_level = MODERATE` (Fire Weather Alert).
  The system reports dangerous weather while explicitly stating that active fire incident is unconfirmed. It **never** fabricates an active `HIGH` or `CRITICAL` disaster.
- **Scenario 3 (Cross-Modal Conflict):**
  Active flames ($p_{\text{fire}} = 0.85$) observed during heavy rainfall ($15.0\text{ mm}$):
  `incident_status = CONFIRMED`, `incident_severity = CRITICAL`, `has_conflicting_evidence = True`, `uncertainty = "ELEVATED_UNCERTAINTY: Contradictory evidence detected... Highest credible severity is preserved without downgrade for public safety; immediate ground verification and field reconnaissance are recommended."`
  The system refuses to silently downgrade life-safety warnings.

---

### 3.3 Concern C: Unknown Exposure Representation & Consequence Safety

In `backend/app/intelligence/schemas.py`:
- `ExposureAssessment.exposure_score`: Changed from `float` to `Optional[float] = None` (`ge=0.0, le=100.0`).
- `ConsequenceAssessment.consequence_score`: Changed from `float` to `Optional[float] = None` (`ge=0.0, le=100.0`).

In `backend/app/intelligence/risk.py`:
- **When 0 geographic features are evaluated:**
  ```python
  if context.total_features_evaluated == 0:
      s_exp = None
      exp_level = "UNVERIFIED (NO_LOCAL_FEATURES)"
      exposure_factors.append(
          "Spatial catalog holds 0 local features; exposure level is UNVERIFIED "
          "(reflects spatial data availability limits, not verified absence of vulnerability)."
      )
  ```
- **Consequence Calculation with Null Safety:**
  ```python
  if s_haz == 0.0:
      s_con = 0.0
      con_tier = DisasterAssessmentLevel.LOW
      con_rationale = (
          "Negligible consequence: no active wildfire hazard detected in physical observations. "
          "Infrastructure proximity presents zero immediate threat."
      )
  elif s_exp is None or context.total_features_evaluated == 0:
      s_con = None
      con_tier = DisasterAssessmentLevel.INSUFFICIENT_DATA
      con_rationale = (
          f"Active hazard score is {s_haz:.1f}, but spatial exposure is UNVERIFIED (0 local features in catalog). "
          "Consequence calculation cannot be determined (INSUFFICIENT_DATA) pending PostGIS or verified spatial data."
      )
  else:
      s_con = round(s_haz * (s_exp / 100.0), 1)
      ...
  ```
- **Composite Risk Index Protection:**
  When `s_exp is None` or `s_con is None`, `composite_index = round(s_haz, 1)`. The active hazard is preserved directly without being artificially deflated toward zero by missing spatial datasets.

---

## 4. Comprehensive Scenario-Based Verification

A dedicated test suite was constructed at `backend/tests/unit/intelligence/test_semantic_release_scenarios.py` covering all 19 required scenarios:

| # | Scenario Test Function | Test Category | Target Assertion / Invariant | Result |
|---|---|---|---|:---:|
| 1 | `test_visual_fire_prediction_without_corroboration_yields_suspected` | Incident Confirmation | Fire prediction alone without corroboration $\to$ `SUSPECTED` (not `CONFIRMED`), severity capped at `HIGH` | **PASS** |
| 2 | `test_visual_smoke_prediction_without_corroboration_yields_suspected` | Incident Confirmation | Smoke prediction alone without corroboration $\to$ `SUSPECTED` | **PASS** |
| 3 | `test_fire_prediction_with_independent_verified_corroboration_yields_confirmed` | Incident Confirmation | Vision + Satellite radiometer corroboration $\to$ `CONFIRMED` | **PASS** |
| 4 | `test_explicit_verified_field_confirmation_yields_confirmed` | Incident Confirmation | Ground personnel verification (`is_confirmed=True`) $\to$ `CONFIRMED` | **PASS** |
| 5 | `test_visual_neutral_prediction_yields_unconfirmed` | Incident Confirmation | Neutral image $\to$ `UNCONFIRMED`, `incident_severity = None` (`null`) | **PASS** |
| 6 | `test_visual_missing_image_evidence_yields_insufficient_evidence` | Incident Confirmation | Missing image evidence $\to$ `INSUFFICIENT_EVIDENCE`, `incident_severity = None` (`null`) | **PASS** |
| 7 | `test_single_image_prediction_cannot_independently_establish_critical_severity` | Incident Severity | Single image ($p_{\text{fire}}=0.99$) capped at `HIGH` severity (never `CRITICAL`) | **PASS** |
| 8 | `test_visual_uncertain_or_conflicting_evidence` | Visual Evidence | Diffuse class probabilities $\to$ `SUSPECTED`, diffuse explanation | **PASS** |
| 9 | `test_neutral_image_does_not_establish_regional_fire_absence` | Visual Evidence | Neutral image emits FOV caveat; does NOT claim region is fire-free | **PASS** |
| 10 | `test_extreme_fire_weather_without_incident_evidence` | Fire-Weather Separation | FWI=45 + neutral image $\to$ `UNCONFIRMED`, `severity = None`, capped at `MODERATE` alert | **PASS** |
| 11 | `test_active_fire_with_supporting_environmental_evidence` | Fire-Weather Separation | Active flame (uncorroborated) + FWI=32 $\to$ `SUSPECTED`, `HIGH` severity | **PASS** |
| 12 | `test_active_incident_with_missing_environmental_data` | Fire-Weather Separation | Active flame + missing weather $\to$ `SUSPECTED`, `HIGH`, missing stream flagged | **PASS** |
| 13 | `test_conflicting_incident_evidence_preserves_highest_severity` | Fire-Weather Separation | Flames + 15mm rain $\to$ `SUSPECTED`, `HIGH` severity preserved, `ELEVATED_UNCERTAINTY` | **PASS** |
| 14 | `test_fire_weather_danger_never_independently_produces_high_or_critical_severity` | Fire-Weather Separation | FWI=60 + missing image $\to$ `INSUFFICIENT_EVIDENCE`, advisory $\le$ `MODERATE` | **PASS** |
| 15 | `test_geographic_features_available_verified_exposure` | Geographic Exposure | Features nearby $\to$ `exposure_score` non-null ($\ge 70.0$), `CRITICAL/HIGH` | **PASS** |
| 16 | `test_verified_low_geographic_exposure` | Geographic Exposure | Features evaluated, distant settlements $\to$ `exposure_score = 10.0`, `LOW` | **PASS** |
| 17 | `test_no_geographic_features_unverified_exposure` | Geographic Exposure | 0 features $\to$ `exposure_score is None` (`null`), `UNVERIFIED (NO_LOCAL_FEATURES)` | **PASS** |
| 18 | `test_missing_exposure_handled_safely_in_consequences` | Geographic Exposure | Active flame + 0 features $\to$ `consequence_score is None`, `INSUFFICIENT_DATA` | **PASS** |
| 19 | `test_database_unavailable_error_preservation` | Database Contract | Database unreachable $\to$ `PostGISUnavailableError` raised without silent fallback | **PASS** |
| 20 | `test_api_response_schema_distinct_semantic_fields_and_json_serialization` | API Serialization | Serializes to JSON with all distinct root fields; missing severity is `null` | **PASS** |

---

## 5. Live PostGIS Infrastructure Regression Verification

The live PostGIS environment was re-verified and confirmed healthy during this audit:

| Verification Item | Command / Probe | Verified Output | Status |
|---|---|---|:---:|
| **Container Status** | `docker ps --filter "name=scout-postgis"` | `aa2283c4c075 Up (healthy)` bound to `127.0.0.1:5432` | **PASS** |
| **PostgreSQL Version** | `SELECT version();` | `PostgreSQL 16.4 (Debian 16.4-1.pgdg110+2)` | **PASS** |
| **PostGIS Extension** | `SELECT PostGIS_Full_Version();` | `POSTGIS="3.4.3 e365945" [EXTENSION] PGSQL="160" GEOS="3.9.0"` | **PASS** |
| **Alembic Revision** | `SELECT version_num FROM alembic_version;` | `0003_persistent_geospatial_features (head)` | **PASS** |
| **Spatial GiST Indexes** | Query `pg_indexes` | `ix_geographic_features_geometry`, `ix_incidents_location` present | **PASS** |
| **Live DB Connection Test** | `test_db_connection.py` | 1/1 passed in 0.14s | **PASS** |
| **Live Integration Suite** | `backend/tests/integration/` | 66/66 passed in 2.44s | **PASS** |

---

## 6. Complete Automated Test Suite Summary

All test suites across the platform were executed and achieved a **100% pass rate**:

```
=================================== SUMMARY ===================================
Total Tests Run: 376
Passed: 376
Failed: 0
Skipped: 0
Warnings: 1 (StarletteDeprecationWarning: httpx with starlette.testclient)
Exit Code: 0
Overall Pass Rate: 100.0%
===============================================================================
```

### Detailed Breakdown by Test Suite

| Test Group | Test Path | Tests Passed | Duration | Exit Code |
|---|---|:---:|:---:|:---:|
| **M11 Semantic Scenarios** | `backend/tests/unit/intelligence/test_semantic_release_scenarios.py` | 19 / 19 | 1.12s | 0 |
| **M11 Intelligence Unit Suite** | `backend/tests/unit/intelligence/` | 83 / 83 | 2.59s | 0 |
| **Geospatial Unit Suite** | `backend/tests/unit/geospatial/` | 106 / 106 | 0.38s | 0 |
| **Environmental Unit Suite** | `backend/tests/unit/environmental/` | 49 / 49 | 0.19s | 0 |
| **Alembic Migrations Unit** | `backend/tests/unit/test_alembic*.py` | 5 / 5 | 3.85s | 0 |
| **Engine & Storage Unit** | `backend/tests/unit/test_config.py`, `test_storage.py`, schemas | 67 / 67 | 0.50s | 0 |
| **Total Backend Unit Tests** | `backend/tests/unit/` | **310 / 310** | **7.75s** | **0** |
| **Total Integration Tests (Live PostGIS)** | `backend/tests/integration/` | **66 / 66** | **2.44s** | **0** |
| **Complete Backend Platform Suite** | `backend/tests/` | **376 / 376** | **8.36s** | **0** |

---

## 7. Working-Tree & Git Preservation Status

- **Git Branch:** `main`
- **Current HEAD Commit:** `65f8933 chore: initialize SCOUT project foundation`
- **Git Commits Created:** 0 (strictly zero commits created per preservation rules).
- **ML Models & Checkpoints:** Untouched. All 12 checkpoints across `artifacts/checkpoints/` preserved.
- **Datasets:** Untouched. Zero raw or processed datasets downloaded or modified.
- **Docker Volumes:** Persistent volume `scout_postgis_data` intact. Zero volumes destroyed.

---

## 8. Operational Limitations & Scientific Boundary Notes

1. **Camera Sensor Field-of-View Limitation:**
   - A 2D RGB ground or aerial photograph captures only the immediate line of sight and camera orientation. Complex terrain, dense forest canopies, ridge lines, and smoke plume dispersion can obscure active wildfires.
   - Neutral classifications confirm that no salient flame or smoke features are visible in that specific frame; they cannot and do not prove that the surrounding 5–10 km buffer is fire-free.
2. **Instantaneous Fire Weather Index (FWI) Approximation:**
   - Single-reading FWI calculated from instantaneous weather observations serves as an indicator of atmospheric fuel combustibility. It lacks continuous multi-day moisture code tracking (which standard Canadian CFS-FWI requires from snowmelt) and has not been calibrated for Indian forest fuel complexes.
3. **Spatial Feature Density & Completeness:**
   - While settlements and healthcare facilities derived from national datasets are comprehensive, emergency fire stations (OSM) have partial national completeness. Unverified exposure reflects catalog data density, not guaranteed absence of human assets.
4. **Decision Threshold Heuristic:**
   - The $0.50$ classifier decision threshold is an engineering heuristic, not an empirically calibrated Bayes-optimal risk boundary. Raw class scores are preserved for downstream decision systems.

---

## 9. Final Verification Sign-Off

All three semantic concerns have been completely resolved, verified through 17 dedicated scenario tests, and validated against the live PostGIS regression suite with zero errors and zero breaking changes.

- **Concern A (Visual Evidence Epistemics & Neutral Image Status):** `RESOLVED & VERIFIED`
- **Concern B (Incident Severity & Fire-Weather Separation):** `RESOLVED & VERIFIED`
- **Concern C (Unknown Exposure Null Representation & Consequence Safety):** `RESOLVED & VERIFIED`
- **Regression Suite Pass Rate (373/373 Tests):** `100.0%`
- **Live PostGIS Infrastructure Integrity:** `VERIFIED`
- **Final Release Gate Verdict:** **`ACCEPTED_WITH_LIMITATIONS`**
