# SCOUT Milestone 07 — Phase 7B: Label Harmonization & Mapping Policy

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Milestone:** M07 — Image Classification Engineering & Generalization  
**Phase:** Phase 7B — Multi-Source Wildfire Dataset Expansion & Hardening  
**Auditor / Engineer:** Principal ML Data Engineer & QA Systems Auditor  
**Date:** October 31, 2026  
**Status:** COMPLETE & VERIFIED  

---

## 1. Objective & Scope

Machine learning computer vision models deployed for emergency disaster intelligence require robust, unambiguous class definitions. In real-world wildfire monitoring, early detection of smoke plumes must be distinguished from active flame fronts and benign environmental distractors (such as cumulus clouds, red twilight horizons, autumn foliage, or emergency vehicle lighting).

This document establishes the official semantic definitions, class boundaries, harmonization rules, and quarantine policies across all ingested data sources for the **SCOUT Wildfire Classification Engine (v2)**.

---

## 2. Target Semantic Class Definitions

The target classification space strictly consists of three mutually exclusive classes:

### 2.1 Class 0: `fire`
* **Definition:** Visible active flaming combustion, open flames, wildfire flaming fronts, flare-ups, structural fires, or active pile burns.
* **Positive Visual Criteria:**
  - Distinct incandescent flame body radiating visible yellow, orange, red, or high-temperature white light.
  - Active burning brush, trees, ground cover, or building timber.
  - UAV / aerial view over active wildfire flaming perimeter.
* **Exclusions:**
  - Smoke plumes where flaming front is completely obscured by dense smoke (classified as `smoke`).
  - Distractor red/yellow objects (red trucks, sunsets, neon signs, autumn leaves) lacking active flame (classified as `neutral`).

### 2.2 Class 1: `neutral`
* **Definition:** Non-fire, non-smoke imagery depicting natural or anthropogenic environments, baseline terrain, and false-positive distractors.
* **Positive Visual Criteria:**
  - Clear forest canopy, chaparral, mountain ridges, grass fields, roads, and waterways.
  - Pre-ignition landscapes captured from surveillance cameras.
  - Adversarial distractors: sunsets, sunrises, sun flares, red buildings, fire department vehicles, personnel in high-visibility gear, autumn foliage, chimney vapor, and fog/clouds without fire.
* **Exclusions:**
  - Any scene with confirmed visible flame or confirmed wildfire smoke.

### 2.3 Class 2: `smoke`
* **Definition:** Visible atmospheric smoke plumes, rising particulate columns, wildfire haze, or developing wildfire smoke clouds where no active flame front is visibly exposed.
* **Positive Visual Criteria:**
  - Grey, white, brown, or dark plume rising from forest, ridge, or structure.
  - Distant horizon smoke plume detected by wildfire surveillance cameras (e.g., HPWREN FIgLib).
  - Thick smoke plume filling the visual frame without distinct flame bodies.
* **Exclusions:**
  - Clear flame present alongside smoke: If an active flame body is clearly visible in the foreground/midground, the sample is evaluated under the **Flame Dominance Hierarchy Rule** (see Section 3.1).
  - Low-altitude weather clouds/fog lacking ground ignition origin (classified as `neutral`).

---

## 3. Disambiguation Hierarchy & Edge-Case Policy

### 3.1 Multi-Object Priority: The Flame Dominance Hierarchy
In wildland firefighting, active flame presents immediate life-safety hazard, whereas smoke indicates potential combustion. When an image contains both visible fire and smoke:
1. **Dominant Flame Rule:** If visible flames constitute $\ge 5\%$ of the image area or form a prominent focal hazard, the image is mapped to **`fire`**.
2. **Plume Dominance Rule:** If the scene consists overwhelmingly of a towering smoke column and any flaming embers are negligible/microscopic ($< 1\%$ pixel area), the image is mapped to **`smoke`**.
3. **Ambiguity Quarantine:** If flame and smoke are evenly balanced and a human annotator cannot decisively determine the primary operational cue without multi-label annotation, the image is routed to the **Quarantine Pool** and excluded from single-label v2 splits.

### 3.2 Environmental Distractors vs. Smoke
- **Clouds / Fog vs. Smoke:** Weather clouds, marine layer fog, and overcast skies that do not emanate from a localized ground point source are strictly mapped to `neutral`.
- **Sunsets & Reflections:** Golden hour skies, crimson sunsets, and specular reflections on water or glass are strictly mapped to `neutral` to teach the model invariance against false-alarm color triggers.

### 3.3 Capture Modality & Orientation
- Images with EXIF orientation tags are transposed to natural canonical orientation prior to validation.
- All non-RGB modes (RGBA, Grayscale L, Palette P, CMYK) are normalized to 3-channel standard RGB to eliminate mode discrepancies across datasets.

---

## 4. Source-by-Source Harmonization Matrix

| Source Identifier | Source Label / Tag | Resolved Target Class | Mapping Justification & Annotation Condition |
| :--- | :--- | :--- | :--- |
| `bowfire` | `fire` | `fire` | Curated emergency and wildland still images with active flames. |
| `bowfire` | `no-fire` | `neutral` | Curated adversarial non-fire images (sunsets, red buildings, fire engines, leaves). |
| `dfire` | `Fire` | `fire` | Surveillance and field camera frames with fire bounding box annotations. |
| `dfire` | `Smoke` | `smoke` | Surveillance and field camera frames with smoke bounding boxes and zero fire boxes. |
| `dfire` | `None` / empty label | `neutral` | Surveillance and field camera frames with confirmed zero fire/smoke boxes. |
| `fasdd` | `flame` | `fire` | UAV and CV frames with localized flame annotations. |
| `fasdd` | `smoke` | `smoke` | UAV and CV frames with localized smoke annotations and no visible flame. |
| `fasdd` | `background` | `neutral` | Negative baseline terrain frames. |
| `flame` | `Fire` | `fire` | Aerial UAV frames over active prescribed burn piles. |
| `flame` | `No-Fire` | `neutral` | Aerial UAV frames over baseline unburned pine forest. |
| `figlib` | `Visible flame` | `fire` | Mountain PTZ camera captures during active flame phase. |
| `figlib` | `Early smoke` | `smoke` | Mountain PTZ camera captures during early plume emergence. |
| `figlib` | `Pre-ignition` | `neutral` | Mountain PTZ baseline mountain views prior to ignition. |
| `deepquest_v1` | `fire` | `fire` | Historical v1 fire images (preserved for continuity). |
| `deepquest_v1` | `smoke` | `smoke` | Historical v1 smoke images (preserved for continuity). |
| `deepquest_v1` | `neutral` | `neutral` | Historical v1 neutral images (rebalanced across formats). |

---

## 5. Automated Quarantine & Rejection Policy

An image is rejected from the dataset during the ingestion pass and logged to `artifacts/audits/m07_phase7b/quarantine_log.json` if any of the following conditions are met:

```
[Candidate Image]
       |
       +--> Fails Pillow 2-Pass Decode? ----------> [REJECT: CORRUPT_BYTES]
       |
       +--> Dimension < 64px or > 8192px? -------> [REJECT: INVALID_DIMENSIONS]
       |
       +--> Aspect Ratio < 0.20 or > 5.00? ------> [REJECT: EXTREME_ASPECT]
       |
       +--> Perceptual Duplicate Across Splits? -> [REJECT: LEAKAGE_PREVENTION]
       |
       +--> Ambiguous Multi-Class Co-occurrence? -> [REJECT: AMBIGUOUS_LABEL]
       |
       v
[ACCEPTED: PROCEED TO GROUPING & SPLITTING]
```

---

## 6. Audit Trail & Reproducibility Guarantee

1. Every accepted image receives a canonical SHA-256 hash and unique UUID record.
2. The split manifest (`artifacts/audits/m07_phase7b/split_manifest.csv`) records the original source ID, original filename, target class, resolution, format, and assigned split.
3. Original historical `data/processed/fire_smoke_v1/` remains entirely unaltered, ensuring 100% reproducibility of all historical benchmark experiments.
