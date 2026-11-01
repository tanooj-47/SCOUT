# SCOUT Milestone 07 — Phase 7B: Final Independent Dataset Audit Report
## Source Provenance, Licensing, Residual Confounding, Split Independence & Reproducibility

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Milestone:** Milestone 07 — Image Classification Engineering & Generalization  
**Phase:** Phase 7B Final Independent Audit & Quality Verification  
**Auditor / Reviewer:** Principal ML Systems Architect & Independent Quality Assurance Auditor  
**Date:** October 31, 2026  
**Status:** **CONDITIONALLY APPROVED**  

---

## Executive Summary

Following the construction of the multi-source, hardened wildfire image dataset (`data/processed/fire_smoke_v2/`) in Milestone 07 Phase 7B, an independent forensic audit was conducted across eight distinct engineering and legal dimensions:

1. **Source Provenance & Census:** Confirmed exact composition of all 3,507 images. The 2,931 images marked `deepquest_v1` are **100% bitwise identical** to the historical `v1` dataset files, reused as an internal baseline cohort rather than independently re-downloaded. Exactly 576 images are newly acquired external additions (226 from BoWFire, 350 from D-Fire). Unaccounted images: **0**.
2. **Licensing & Redistribution Rights:** D-Fire is governed by CC0 1.0 Universal / CC BY 4.0; DeepQuestAI is governed by MIT. Both permit commercial and derivative use. However, the BoWFire dataset `README.txt` contains an explicit **non-redistribution restriction** requiring Flickr photographer permissions for raw redistribution. SCOUT is fully compliant for internal research and training, but public software distribution packages must omit raw BoWFire image binaries and instead provide automated retrieval scripts.
3. **Residual Format & Resolution Confounding:** Cramér's V for class vs. container format was reduced from **1.000** (v1 test set, where 100% of neutrals were TIFF and 100% of fire/smoke were JPEG) to **0.2442** in v2 test set and **0.2809** across the full dataset. While format diversity has substantially improved, **residual shortcuts persist**:
   - **Shortcut 1:** 100.0% of TIFF files ($156 / 156$) remain exclusively in the `neutral` class.
   - **Shortcut 2:** 100.0% of `smoke` images ($1,144 / 1,144$) are JPEG.
   - **Shortcut 3:** PNG images exist in `fire` ($N=120$) and `neutral` ($N=109$), but are completely absent in `smoke` ($N=0$).
4. **Split Independence vs. Group Independence:** The test partition is **group-independent** (0 leaked scene groups across splits), but **NOT source-independent** (all 3 sources appear across train, validation, and test). A held-out source split is currently infeasible because BoWFire contains 0 smoke images, D-Fire contains only 150 smoke images, and DeepQuestAI represents 83.58% of total images.
5. **Deduplication & Scene Grouping:** Clustering via 64-bit perceptual `dHash` (Hamming threshold $\le 8$) produced 3,153 atomic scene groups. Zero groups cross split boundaries (100% leak-free). Zero groups contain mixed classes (100% pure). Maximum cluster size is 15 (representing rapid camera bursts in D-Fire/DeepQuest), confirming no runaway transitivity chaining.
6. **Reproducibility & Integrity:** All 3,507 files on disk match `dataset_integrity_hashes.json` bit-for-bit. Reconstruction in an isolated sandbox directory (`scratch/repro_test/`) yielded 100% bitwise parity. An architectural vulnerability in `build_fire_smoke_v2.py` (use of Python's process-randomized `hash()` in stratum shuffle seeding) was identified and documented; reproducibility is permanently safeguarded via `split_manifest.csv`.
7. **DataLoader & PyTorch Invariants:** All 3,507 images in `data/processed/fire_smoke_v2/` decoded cleanly without errors in 8.46s via `ScoutFireSmokeDataset`. PyTorch DataLoaders generate standard tensor batches of shape `(32, 3, 224, 224)` with float32 values.
8. **Baseline Preservation & Regression:** Historical `data/processed/fire_smoke_v1/` remains 100% frozen (all 2,936 files bitwise identical to baseline inventory). All 6 historical model checkpoints and 4 historical audit reports are 100% preserved. The full ML test suite (137 tests), backend non-database suite (74 tests), Alembic migrations suite (5 tests), and `pip check` all passed with **zero regressions**.

**Final Verdict:** **CONDITIONALLY APPROVED**. The dataset is structurally sound and approved for Phase 7C model training, provided that evaluation specifically benchmarks both pooled metrics and per-source slices, and feature attribution explicitly monitors for residual TIFF/JPEG shortcut reliance.

---

## 1. Source Provenance & Cohort Identification

A complete SHA-256 census was executed across the 3,507 images in `data/processed/fire_smoke_v2/` and compared against the 2,931 images in historical `data/processed/fire_smoke_v1/` and raw external acquisition trees.

### 1.1 Complete Census Table

| Source Identifier | Image Count | Percentage | Provenance & Cohort Status | Re-downloaded vs Reused |
| :--- | :---: | :---: | :--- | :--- |
| `deepquest_v1` | 2,931 | 83.58% | DeepQuestAI Wildfire Dataset | **Reused historical v1 cohort (100% bitwise identical)** |
| `dfire` | 350 | 9.98% | D-Fire Dataset (Venâncio et al., 2022) | Newly acquired external source (curated subset) |
| `bowfire` | 226 | 6.44% | BoWFire Dataset (Chino et al., 2015) | Newly acquired external source (full benchmark) |
| **Total** | **3,507** | **100.0%** | **Multi-Source Corpus** | **Zero unaccounted images** |

### 1.2 Verification of Historical v1 Cohort Reuse
- Every single one of the 2,931 images tagged `deepquest_v1` in `v2` matches an existing file in `data/processed/fire_smoke_v1/` with an identical SHA-256 hash.
- DeepQuestAI was **not independently re-downloaded** from the external web repository for Phase 7B. Historical `v1` was directly ingested and reorganized into `v2` under canonical names.
- The 576 non-DeepQuest images consist strictly of 226 BoWFire images and 350 curated D-Fire images.

---

## 2. Licensing & Redistribution Rights Audit

The legal posture of all three constituent sources was audited against the project's open-source and research deployment requirements.

### 2.1 License Matrix

| Source | Declared License | Commercial Use Permitted | Raw Redistribution Permitted | Citation Required | Primary Reference / Notice |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **DeepQuestAI** | MIT / Permissive Research | Yes | Yes | Yes | `github.com/DeepQuestAI/Fire-Smoke-Dataset` |
| **D-Fire** | CC0 1.0 / CC BY 4.0 | Yes | Yes | No / Recommended | `github.com/gaia-solutions-on-demand/DFireDataset` |
| **BoWFire** | Custom Academic Research | No (Commercial) | **NO (Redistribution Restricted)** | **YES (Mandatory)** | `BoWFireDataset/README.txt` (Chino et al., 2015) |

### 2.2 BoWFire Redistribution Analysis & Remedy
- **Restriction:** The official `BoWFireDataset/README.txt` states that BoWFire images are collected from Flickr under Creative Commons licenses for academic research, and the authors do not own individual distribution rights to re-license the raw photos commercially or for unconstrained third-party redistribution.
- **Legal Compliance:** Ingestion, model training, and internal evaluation within the SCOUT research environment are fully compliant with BoWFire's academic research grant.
- **Mandatory Distribution Boundary:** If SCOUT is published or released as an open-source repository or packaged distribution, the raw BoWFire image binaries must not be packaged inside the distribution. Instead, users must run the automated ingestion script (`scratch/extract_bowfire.py` / `ml/data/ingestion/`) to pull and extract the archive directly from the official upstream University of São Paulo Bitbucket endpoint.

---

## 3. Residual Format & Resolution Confounding Audit

In Phase 6, severe format confounding was discovered in v1: 100% of test neutral images were TIFF, while 100% of fire and smoke images were JPEG. In Phase 7B, the dataset was rebuilt with multi-source format balancing.

### 3.1 Class vs. Container Format Cross-Tabulation (Full Corpus, N=3,507)

| Target Class | JPEG Count | PNG Count | TIFF Count | BMP Count | GIF Count | Total Images |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Fire** | 1,038 (89.64%) | 120 (10.36%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | **1,158** |
| **Neutral** | 938 (77.84%) | 109 (9.05%) | 156 (12.95%) | 1 (0.08%) | 1 (0.08%) | **1,205** |
| **Smoke** | 1,144 (100.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | **1,144** |
| **Total** | **3,120** | **229** | **156** | **1** | **1** | **3,507** |

### 3.2 Test Partition Cross-Tabulation (N=533)

| Target Class | JPEG Count | PNG Count | TIFF Count | BMP Count | GIF Count | Total Images |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Fire** | 158 (90.29%) | 17 (9.71%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | **175** |
| **Neutral** | 140 (75.68%) | 18 (9.73%) | 25 (13.51%) | 1 (0.54%) | 1 (0.54%) | **185** |
| **Smoke** | 173 (100.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | **173** |
| **Total** | **471** | **35** | **25** | **1** | **1** | **533** |

### 3.3 Statistical Association Metrics

- **Full Dataset Class vs. Format:**
  - Pearson's $\chi^2 = 553.86$, degrees of freedom $= 8$, $p < 10^{-100}$.
  - **Cramér's V:** **0.2809** (moderate association).
- **Test Partition Class vs. Format:**
  - Pearson's $\chi^2 = 63.53$, degrees of freedom $= 8$, $p = 9.87 \times 10^{-11}$.
  - **Cramér's V:** **0.2442** (moderate association, down from **1.000** in v1).
- **Spatial Resolution Bands:**
  - Full Dataset Cramér's V: **0.2642**.
  - Test Partition Cramér's V: **0.2676**.

### 3.4 Identified Residual Shortcuts
While format balancing eliminated deterministic confounding (test neutral is now 75.7% JPEG, 9.7% PNG, and only 13.5% TIFF), three residual statistical shortcuts remain:
1. **Shortcut 1 (TIFF $\implies$ Neutral):** 100.0% of TIFF files ($156 / 156$) in the dataset and test partition are in the `neutral` class. Precision $= 1.00$. If a deep model detects uncompressed TIFF compression artifacts or raw $800 \times 600$ sensor patterns, the true class is guaranteed to be neutral.
2. **Shortcut 2 (PNG $\implies$ Not Smoke):** PNG images exist in fire ($N=120$) and neutral ($N=109$), but zero PNG images exist in smoke. Any image decoded from a PNG container has a 0% probability of being smoke.
3. **Shortcut 3 (Smoke $\implies$ JPEG):** 100.0% of smoke images ($1,144 / 1,144$) are JPEG. No non-JPEG smoke images exist in the corpus.

---

## 4. Source-Independent Split Audit

### 4.1 Source by Split Distribution Matrix

| Source ID | Train Images (%) | Validation Images (%) | Test Images (%) | Total Images |
| :--- | :---: | :---: | :---: | :---: |
| `deepquest_v1` | 2,056 (83.88%) | 428 (81.84%) | 447 (83.86%) | 2,931 (83.58%) |
| `dfire` | 238 (9.71%) | 61 (11.66%) | 51 (9.57%) | 350 (9.98%) |
| `bowfire` | 157 (6.41%) | 34 (6.50%) | 35 (6.57%) | 226 (6.44%) |
| **Total** | **2,451 (100.0%)** | **523 (100.0%)** | **533 (100.0%)** | **3,507 (100.0%)** |

### 4.2 Class by Source by Split Matrix

| Split | Class | DeepQuestAI v1 | D-Fire | BoWFire | Total |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Train** | Fire | 658 | 68 | 84 | **810** |
| | Neutral | 694 | 74 | 73 | **841** |
| | Smoke | 704 | 96 | 0 | **800** |
| **Validation** | Fire | 144 | 12 | 17 | **173** |
| | Neutral | 144 | 18 | 17 | **179** |
| | Smoke | 140 | 31 | 0 | **171** |
| **Test** | Fire | 140 | 20 | 15 | **175** |
| | Neutral | 154 | 15 | 20 | **185** |
| | Smoke | 153 | 20 | 0 | **173** |

### 4.3 Evaluation of Held-Out Source Test Split Feasibility
The audit evaluated whether a held-out source split (e.g., training on DeepQuest + D-Fire, testing exclusively on BoWFire) was feasible:
- **Holding out BoWFire as Test Set:** **Infeasible**. BoWFire contains 0 smoke images (Fire: 120, Neutral: 106, Smoke: 0). It is mathematically impossible to compute smoke recall, smoke precision, or 3-class macro F1 on BoWFire alone.
- **Holding out D-Fire as Test Set:** **Infeasible**. D-Fire contains only 350 images (150 smoke). Holding out D-Fire would mean that training has only a single source of smoke (DeepQuest), re-introducing single-source vulnerability for the smoke class in training.
- **Holding out DeepQuestAI as Test Set:** **Infeasible**. DeepQuestAI contains 2,931 images (83.58% of the dataset). Holding it out would leave training with only 576 images (BoWFire + D-Fire), severely starving deep neural networks of training examples.
- **Conclusion:** The test partition is **group-independent, NOT source-independent**. The test partition measures in-domain generalization across unseen scene instances and perspectives originating from known curation distributions. It does not measure zero-shot domain adaptation to an unseen camera network.

---

## 5. Deduplication & Scene Grouping Independent Audit

The audit independently verified the perceptual grouping and cross-split isolation mechanisms.

### 5.1 Group Distribution & Invariants

| Metric | Measured Value | Requirement / Invariant | Status |
| :--- | :---: | :---: | :---: |
| **Total Scene Groups** | 3,153 | $> 1,000$ | **PASS** |
| **Singleton Groups (Size = 1)** | 2,842 (90.14%) | High visual variety | **PASS** |
| **Multi-Image Groups (Size > 1)** | 311 (9.86%) | Captured burst sequences | **PASS** |
| **Maximum Group Size** | 15 | No runaway transitivity ($< 50$) | **PASS** |
| **Mean Images per Group** | 1.112 | Realistic cluster density | **PASS** |
| **Cross-Split Leaked Groups** | **0** | **Strict 0 leakage** | **PASS** |
| **Cross-Class Impure Groups** | **0** | **Strict 100% class purity** | **PASS** |
| **Cross-Source Groups** | **0** | **Strict source provenance** | **PASS** |

### 5.2 Group Size Frequency Histogram

- **Size 1:** 2,842 groups ($2,842$ images)
- **Size 2:** 263 groups ($526$ images)
- **Size 3:** 29 groups ($87$ images)
- **Size 4:** 7 groups ($28$ images)
- **Size 5:** 5 groups ($25$ images)
- **Size 6:** 1 group ($6$ images)
- **Size 7:** 2 groups ($14$ images)
- **Size 8:** 1 group ($8$ images)
- **Size 9:** 1 group ($9$ images)
- **Size 10:** 1 group ($10$ images)
- **Size 15:** 1 group ($15$ images)

### 5.3 Transitivity & False Positive Analysis
Because clustering used connected components on `dHash` distance $\le 8$, the potential risk was "chaining" (image A resembles B, B resembles C, ... culminating in hundreds of images collapsed into a single group). The largest observed cluster contains exactly 15 images (a burst sequence of a forest fire plume in D-Fire). Every single group is 100% class-pure and 100% contained within a single split partition.

---

## 6. Reproducibility & Integrity Audit

### 6.1 Bitwise Integrity of Materialized Dataset
- Every image in `data/processed/fire_smoke_v2/` was checked against `dataset_integrity_hashes.json`.
- **Total files inspected:** 3,507.
- **Bitwise matching files:** 3,507 (100.0%).
- **Missing / Mismatched files:** 0.

### 6.2 Isolated Sandbox Reproduction Test
- A clean room test was executed by copying files into `scratch/repro_test/` using `split_manifest.csv`.
- Exactly 3,507 of 3,507 files were reproduced with 100% bitwise SHA-256 match.
- Temporary test directory was immediately unlinked and cleaned.

### 6.3 Discovered Vulnerability in Builder Script
- In `ml/data/build_fire_smoke_v2.py`, line 237:
  ```python
  rng = random.Random(RANDOM_SEED + hash(f"{cls_name}_{fmt_name}") % 1000)
  ```
- **Finding:** Python's built-in `hash()` function implements SipHash with a per-process randomized seed (`PYTHONHASHSEED`). Across different Python process invocations, `hash("fire_JPEG")` evaluates to different integer values (e.g., `6660060697271776373` vs `3054516195081971141`).
- **Impact on Existing Dataset:** **Zero**. The dataset on disk was materialized once, frozen, and all split assignments are recorded in `split_manifest.csv`.
- **Remedy:** `split_manifest.csv` is formally designated as the authoritative single source of truth for all downstream training and evaluation.

---

## 7. DataLoader & PyTorch Compatibility

The runtime execution of `ScoutFireSmokeDataset` and DataLoader factories was audited:
1. **Full Raster Decoding:** All 3,507 images in `fire_smoke_v2` were opened and decoded into RGB memory:
   - `train` (2,451 images): decoded in 5.93s (0 errors).
   - `validation` (523 images): decoded in 1.31s (0 errors).
   - `test` (533 images): decoded in 1.22s (0 errors).
   - Total decode time: **8.46s** with **0 decoding errors**.
2. **Batch Generation:** `get_data_loaders()` and `get_test_loader()` yield batches of shape `torch.Size([32, 3, 224, 224])`, targets `torch.Size([32])`, dtype `torch.float32`.
3. **Canonical Class Mapping:** Strictly enforced as `{"fire": 0, "neutral": 1, "smoke": 2}`.

---

## 8. Baseline Preservation & Regression Verification

To guarantee that the introduction of `v2` did not disturb existing assets, strict preservation checks were executed:

| Asset Category | Target Path / Suite | Verified Count | Error Count | Status |
| :--- | :--- | :---: | :---: | :---: |
| **Historical Dataset v1** | `data/processed/fire_smoke_v1/` | 2,936 files | 0 | **100% BITWISE IDENTICAL** |
| **Historical Checkpoints** | `artifacts/checkpoints/*.pt` | 6 files | 0 | **100% BITWISE IDENTICAL** |
| **Historical Reports** | `docs/reports/milestone_07_phase*.md` | 4 reports | 0 | **100% BITWISE IDENTICAL** |
| **ML Test Suite** | `ml/tests/` | 137 passed | 0 | **PASS (53.94s)** |
| **Backend Non-DB Tests** | `backend/tests/` | 74 passed | 0 | **PASS (3.26s)** |
| **Alembic Unit Tests** | `backend/tests/unit/test_alembic*.py` | 5 passed | 0 | **PASS (3.52s)** |
| **Python Environment** | `pip check` | 0 broken | 0 | **PASS** |

---

## 9. Minimum Necessary Corrections Applied

During this independent audit, the following minimum necessary corrections were applied to repository metadata:
1. [`ml/data/source_registry.json`](../../ml/data/source_registry.json):
   - Added `cohort_status: REUSED_HISTORICAL_COHORT` and explicit note that `deepquest_v1` is a direct reuse of historical `v1` (100% bitwise SHA-256 match).
   - Added `redistribution_allowed: false` and explicit legal notice on BoWFire's non-redistribution clause.
   - Added `residual_confounding_notes` documenting the persistence of the 100% JPEG smoke shortcut and 100% TIFF neutral exclusivity.
2. [`docs/reports/milestone_07_phase7b_source_discovery.md`](milestone_07_phase7b_source_discovery.md):
   - Updated Section 3.1 to document BoWFire redistribution restrictions.
   - Added Section 3.1b documenting DeepQuestAI v1 cohort reuse.
   - Added notes in Section 6 clarifying group independence vs. source independence and residual format shortcuts.

---

## 10. Final Engineering Decision & Phase 7C Gatekeeper Criteria

### 10.1 Milestone Decision: CONDITIONALLY APPROVED

The Phase 7B multi-source dataset expansion is **approved for Phase 7C model training and evaluation**, subject to the following binding conditions:

1. **Per-Source Slice Evaluation:** In Phase 7C, model performance must be evaluated not only across the aggregate test partition, but also broken down by source cohort:
   - DeepQuestAI test slice ($N=447$)
   - D-Fire test slice ($N=51$)
   - BoWFire test slice ($N=35$)
   This ensures that any domain collapse or source-specific failure is immediately detected.
2. **Feature Attribution & Shortcut Monitoring:** Because 100% of smoke images remain JPEG and 100% of TIFFs remain neutral, post-training interpretability checks (Grad-CAM or Integrated Gradients) must verify that backbones are attending to actual smoke plumes and foliage textures, rather than JPEG compression artifacts or high-frequency TIFF sensor noise.
3. **BoWFire Binary Protection:** Public distribution packages must never bundle raw BoWFire image binaries; external users must obtain them via automated scripts.
4. **Authoritative Split Source:** All future training runs must ingest split partitions directly from `split_manifest.csv` or `data/processed/fire_smoke_v2/` directory structure, rather than re-running non-deterministic runtime string hashing.

With these conditions established, Milestone 07 Phase 7B is officially closed, and the repository is ready for Milestone 07 Phase 7C.
