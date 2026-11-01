# SCOUT Milestone 07 — Phase 7B: Candidate Source Discovery & License Vetting Report

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Milestone:** M07 — Image Classification Engineering & Generalization  
**Phase:** Phase 7B — Multi-Source Wildfire Dataset Expansion & Hardening  
**Auditor / Engineer:** Principal ML Data Engineer & QA Systems Auditor  
**Date:** October 31, 2026  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary & Objective

In **Milestone 07 Phase 6**, a comprehensive dataset integrity and model generalization audit exposed severe structural confounding in the baseline wildfire dataset (`data/processed/fire_smoke_v1/`):
- **100% of test neutral images** ($N=100$) were uncompressed/PackBits **TIFF** images ($800 \times 600$ px), representing every single TIFF image in the entire test dataset.
- **100% of test fire and smoke images** were small web **JPEG** images (mean dimensions $271 \times 186$ px and $269 \times 187$ px respectively).
- Deep learning backbones (such as MobileNetV3-Small) trained on this data collapsed to predicting the majority class or memorizing format/compression artifacts rather than learning invariant flame, smoke, and natural foliage features.

The core objective of **Milestone 07 Phase 7B** is to engineer a multi-source, hardened dataset (`data/processed/fire_smoke_v2/`) that:
1. Retains full bitwise integrity of the historical `v1` dataset (`data/processed/fire_smoke_v1/` remains strictly frozen and unedited).
2. Expands the dataset using reputable, open-access, research-permissive scientific datasets.
3. Formally documents data provenance, license compliance, modality, and capture context.
4. Breaks format/resolution confounding by balancing image containers (JPEG, PNG, TIFF) across all classes.
5. Implements group-aware splitting to prevent temporal, geographic, or video-frame leakage across training, validation, and test splits.

---

## 2. Source Vetting & Licensure Analysis

To prevent legal infringement and ensure academic reproducibility, strict vetting criteria were enforced:
- **Prohibited Sources:** No web-scraping of Google Images, social media (Twitter/X, Instagram, Flickr without permissive licensing), or unverified aggregations.
- **Permitted Licenses:** Public Domain (CC0 1.0), Creative Commons Attribution (CC BY 4.0), Non-Commercial Research Licenses (CC BY-NC 4.0, CC BY-NC-SA 4.0), and university academic licenses.

### Comprehensive Candidate Source Registry

| Source ID | Dataset Name | Lead Institution / Authors | License | Native Classes | Modalities | Primary Formats | Vetting Decision |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `dfire` | **D-Fire Dataset** | GAIA Solutions / UFMG (Pedro Venâncio et al.) | CC0 1.0 Universal (Public Domain) | Fire, Smoke, None | Surveillance cameras, field sensors, web cameras | JPEG | **APPROVED** |
| `bowfire` | **BoWFire Dataset** | ICMC - University of São Paulo (USP) (Chino et al.) | Academic / Research (Non-Commercial) | Fire, Non-Fire | Urban & wildland fires, adversarial distractors (sunsets, autumn leaves) | PNG, JPEG | **APPROVED** |
| `fasdd` | **FASDD Dataset** | Wuhan University (Prof. Peng Yue et al.) | CC BY 4.0 International | Flame, Smoke, Background | UAV drone aerials, ground surveillance, remote sensing | JPEG, PNG | **APPROVED** |
| `flame` | **FLAME / FLAME 2** | Clemson University / NAU (Mostafapour, Chen, Razi) | CC BY-NC 4.0 International | Fire, No-Fire | Aerial drone RGB cameras, thermal IR radiometric video | JPEG, TIFF | **APPROVED** |
| `figlib` | **HPWREN FIgLib** | UC San Diego / SDSC (Hans-Werner Braun et al.) | CC BY-NC 4.0 International | Pre-ignition background, Smoke plume, Visible flame | Mountain-top PTZ fixed optical surveillance cameras | JPEG | **APPROVED** |
| `deepquest_v1`| **DeepQuestAI Fire-Smoke** | DeepQuest AI (Moses Olafenwa) | MIT / Permissive Research | Fire, Smoke, Neutral | Web images, photography, surveillance grabs | JPEG, TIFF, PNG | **APPROVED (WITH CAVEATS)** |
| `fismo` | **FiSmo Dataset** | University of São Paulo (USP) (Avalhais et al.) | Academic Research License | Fire, Smoke, Normal | Emergency scenes, wildland fires, smoke plumes | JPEG, PNG | **APPROVED** |

---

## 3. Detailed Dataset Profiles & Ingestion Viability

### 3.1 BoWFire (Bag-of-Words for Fire Detection)
- **Origin & Authorship:** Daniel Chino, Lucas Avalhais, José Rodrigues Jr., Agma Traina (University of São Paulo). Introduced at SIBGRAPI 2015.
- **Content:** 226 meticulously curated still images.
- **Significance for SCOUT:** BoWFire was specifically constructed to challenge false positives. It contains non-fire emergency scenes with red fire trucks, emergency uniforms, sunset skies, red and yellow leaves, and architectural lighting. Furthermore, it contains high-quality PNG and JPEG images, directly providing high-fidelity non-fire distractors in non-TIFF formats.
- **Access:** Direct HTTP archive from Bitbucket repository downloads API (`BoWFireDataset.zip`, 291 MB).
- **Ingestion Suitability:** Immediate. Fully compatible.
- **License & Redistribution Restrictions:** BoWFire is provided under an Academic Research License with mandatory citation (Chino et al., 2015). The dataset's `README.txt` contains an explicit non-redistribution clause: raw images may not be redistributed in commercial or open distributions without individual Flickr rights. Consequently, BoWFire images are retained strictly for internal research and evaluation; public distributions must fetch them via automated retrieval script.

### 3.1b DeepQuestAI v1 Historical Baseline Cohort
- **Origin & Authorship:** Moses Olafenwa, DeepQuest AI (2019).
- **Cohort Status:** Directly reused from the frozen `data/processed/fire_smoke_v1/` dataset as an internal baseline source cohort.
- **Audit Verification:** Bitwise inspection confirmed that 100% (2,931 of 2,931) images labeled `deepquest_v1` in v2 are bit-for-bit identical with the historical v1 files. They were NOT re-downloaded from an external repository for Phase 7B.
- **Licensing:** MIT License / Permissive Open Access. Commercial and academic use permitted.

### 3.2 D-Fire (Detection Fire & Smoke)
- **Origin & Authorship:** GAIA Solutions on Demand / UFMG, 2022.
- **Content:** Over 21,500 images categorized into `Only fire` (1,164), `Only smoke` (5,867), `Fire and smoke` (4,658), and `None` (9,838) with YOLO bounding boxes.
- **Significance for SCOUT:** D-Fire aggregates surveillance camera captures and public sensor feeds under CC0 1.0 Universal license. It provides clean separation of smoke plumes from flames in realistic outdoor surveillance scenarios.
- **Caveat & Mitigation:** Surveillance feeds contain temporal burst captures. Images must undergo exact SHA-256 and perceptual difference hashing (`dHash`) to eliminate consecutive duplicate frames, and remaining frames from identical sensor series must be grouped into single split partitions.

### 3.3 FASDD (Flame And Smoke Detection Dataset)
- **Origin & Authorship:** School of Remote Sensing and Information Engineering, Wuhan University (Wang et al., 2024, published in *Geo-spatial Information Science*, Taylor & Francis).
- **Content:** 105,670 images spanning CV (ground cameras), UAV (aerial drones), and RS (satellite).
- **Significance for SCOUT:** The UAV partition of FASDD represents high-altitude wildfire reconnaissance, providing high-resolution aerial perspectives matching drone-based disaster response requirements.
- **Licensing:** CC BY 4.0 Open-Access.

### 3.4 FLAME / FLAME 2 (Clemson University)
- **Origin & Authorship:** AI-SENDS Lab, Clemson University (IEEE Access 2021).
- **Content:** Aerial UAV video captures of prescribed pile burns in Northern Arizona ponderosa pine forests.
- **Significance for SCOUT:** Provides true forestry wildfire flame and smoke captures with accompanying non-fire forest canopy backgrounds.
- **Caveat & Mitigation:** Drone video sequences possess very high temporal autocorrelation. Individual video runs must be treated as atomic groups and never split across train/val/test.

### 3.5 HPWREN FIgLib (Fire Ignition images Library)
- **Origin & Authorship:** High Performance Wireless Research and Education Network (UC San Diego / SDSC).
- **Content:** Fixed mountain-top camera time-lapses capturing fire starts across Southern California wildlands.
- **Significance for SCOUT:** Captures the crucial early phase of smoke development (pre-flashover), essential for early wildfire intelligence.

---

## 4. Class Harmonization & Semantic Mapping Matrix

Each external source uses distinct annotation schemes. The SCOUT classification schema requires exactly three target classes:
- `fire`: Active flaming combustion, open flames, wildfire fronts, structural flames.
- `smoke`: Visible smoke plumes, atmospheric wildfire haze, chimney smoke, rising thermal columns without visible flaming front.
- `neutral`: Natural forest canopy, mountain terrain, clear or cloudy skies, urban landscapes, vehicles, firefighters, non-fire emergency scenes, and false-positive distractors.

| Source ID | Original Class / Tag | Target SCOUT Class | Inclusion Criteria & Rules |
| :--- | :--- | :--- | :--- |
| `bowfire` | `fire` | `fire` | Image contains active visible flame. |
| `bowfire` | `no-fire` | `neutral` | Negative distractor without fire or smoke (sunsets, red buildings, natural terrain). |
| `dfire` | `Fire` (or `fire` label in YOLO) | `fire` | Frame annotated with fire bounding box. If both fire and smoke exist, label assigned based on dominant visual feature or secondary smoke annotation recorded. |
| `dfire` | `Smoke` (only smoke) | `smoke` | Frame annotated exclusively with smoke plume bounding box; zero flame boxes. |
| `dfire` | `None` (empty txt or class 0) | `neutral` | Frame verified to have no fire and no smoke bounding boxes. |
| `fasdd` | `flame` | `fire` | Aerial or ground image with flame bounding box / polygon. |
| `fasdd` | `smoke` | `smoke` | Aerial or ground image with smoke bounding box / polygon and no active flame. |
| `fasdd` | `background` | `neutral` | Verified negative non-fire terrain capture. |
| `flame` | `Fire` | `fire` | UAV aerial capture over active burn pile / forest fire. |
| `flame` | `No-Fire` | `neutral` | UAV aerial capture over forest canopy with no burn. |
| `deepquest_v1`| `fire` | `fire` | Verified historical v1 fire image. |
| `deepquest_v1`| `smoke` | `smoke` | Verified historical v1 smoke image. |
| `deepquest_v1`| `neutral` | `neutral` | Verified historical v1 neutral image. |

### Quarantine Criteria
Images are immediately rejected and routed to quarantine if:
1. File fails binary decode or header verification in Pillow (corrupt image bytes).
2. Image contains both dominant fire and heavy smoke in ambiguous proportions where no single label is defensible without multi-label support.
3. Aspect ratio is extreme ($\text{aspect} < 0.25$ or $\text{aspect} > 4.0$) or spatial resolution $< 128 \times 128$ px.
4. Perceptual hash matches an image in another split (leakage violation).

---

## 5. Architectural Strategy for `fire_smoke_v2` Construction

```
+-----------------------------------------------------------------------------------+
|                           SCOUT Multi-Source Pipeline                             |
+-----------------------------------------------------------------------------------+
                                        |
       +--------------------------------+--------------------------------+
       |                                |                                |
+--------------+               +------------------+             +------------------+
| v1 Baseline  |               | BoWFire (USP)    |             | External Open    |
| (DeepQuest)  |               | Hard Distractors |             | Vetted Sources   |
| 2,931 images |               | 226 images       |             | (D-Fire, etc.)   |
+--------------+               +------------------+             +------------------+
       |                                |                                |
       +--------------------------------+--------------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | 1. Pillow 2-Pass Image Validation     |
                    |    (Verify headers, decode full array)|
                    +---------------------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | 2. Feature & Metadata Extraction      |
                    |    (SHA-256, dHash, W, H, Format)     |
                    +---------------------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | 3. Exact & Perceptual Deduplication   |
                    |    (Filter exact SHA-256 & dHash <= 3)|
                    +---------------------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | 4. Scene & Capture-Session Grouping   |
                    |    (Temporal burst / camera clustering)|
                    +---------------------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | 5. Group-Aware Stratified Splitting   |
                    |    (Train: ~70%, Val: ~15%, Test: 15%)|
                    |    * CRITICAL: Format Balance Enforced|
                    +---------------------------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | 6. Target Directory Materialization   |
                    |    data/processed/fire_smoke_v2/      |
                    |      ├── train/                       |
                    |      ├── validation/                  |
                    |      └── test/                        |
                    +---------------------------------------+
```

---

## 6. Verification and Status

- Source discovery registry written to: [`ml/data/source_registry.json`](../../ml/data/source_registry.json).
- Licensure compliance verified: All selected sources possess CC0, CC BY, CC BY-NC, or academic research rights. Note BoWFire raw redistribution restriction for external distribution.
- Historical `data/processed/fire_smoke_v1/` remains 100% frozen and byte-preserved.
- **Split Independence vs. Group Independence:** The test partition is group-independent (0 leaked scene groups across split boundaries, verified via dHash $\le 8$ clustering), but NOT source-independent (DeepQuest, D-Fire, and BoWFire appear across train, validation, and test). A source-held-out test split is currently infeasible because BoWFire contains 0 smoke images, D-Fire contains only 150 smoke images, and DeepQuestAI comprises 83.6% of the corpus.
- **Residual Format Confounding:** While format diversity is substantially improved (Cramér's V reduced from 1.00 to 0.244 in test), three residual shortcuts persist:
  1. 100% of smoke images remain JPEG ($1,144 / 1,144$).
  2. 100% of TIFF images remain exclusive to neutral ($156 / 156$).
  3. PNG images appear in fire and neutral but are absent in smoke ($0$ smoke PNGs).
  Future expansion in Phase 7C/v3 should prioritize non-JPEG smoke captures from open-access sources like FASDD.
