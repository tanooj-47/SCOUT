# SCOUT — Healthcare Geographic Coverage & Quality Analysis

**Subsystem:** M10 Persistent Geospatial Data Integration  
**Component:** Critical Emergency Infrastructure Layer  
**Date:** October 31, 2026  
**Auditor:** Senior Geospatial Data Engineer & Disaster-Intelligence Systems Architect  
**Validation Status:** `VERIFIED_NATIONAL` (with documented regional mapping bias)

---

## 1. Executive Summary

This report delivers a comprehensive spatial coverage and data-quality analysis of India's national healthcare facility layer (`india_hospitals_healthcare.geojson`). 

The layer was extracted from the Humanitarian OpenStreetMap Team (HOT) export hosted on the Humanitarian Data Exchange (HDX). While containing an authentic repository of **121,613 healthcare features**, spatial join analysis against administrative boundaries proves that community mapping density is heavily concentrated in peninsular and urbanized states (Maharashtra, Tamil Nadu, Telangana, Gujarat), with significant sparsity across remote Himalayan, northeastern frontier, and island territories.

---

## 2. Dataset Properties & Data Quality Audit

* **Total Evaluated Features:** 121,613 Point geometries.
* **Coordinate Reference System:** EPSG:4326 (WGS 84).
* **Attribute Completeness:**
  - Feature Names: 121,613 / 121,613 (100% complete; zero unnamed nodes).
  - Categorization: 121,613 / 121,613 (100% mapped into valid infrastructure subcategories).
  - Invalid Geometries: 0.
  - Coordinate Precision: 6 decimal places (~0.1m precision).
* **Facility Typology Breakdown:**
  - `hospital`: 48,770 (40.10%)
  - `centre` (Primary Health Centres / Community Health Centres): 37,425 (30.77%)
  - `clinic`: 21,003 (17.27%)
  - `pharmacy`: 7,341 (6.04%)
  - `doctors`: 3,613 (2.97%)
  - `health_post`: 3,461 (2.85%)
* **Spatial Uniqueness & Compound Co-location:**
  - Unique spatial coordinates: 118,415.
  - Co-located coordinates: 3,198 (2.63%).
  - *Engineering Evaluation:* These co-located points represent distinct legitimate facilities located within single hospital compounds (e.g. an outpatient department, pharmacy, and diagnostic blood bank sharing a hospital building or campus). These have been strictly preserved.
* **Territorial Containment:**
  - Inside Sovereign States/UTs: **121,546 features (99.94%)**.
  - Unmatched / Coastal Tide-line Slivers: **67 features (0.06%)**.

---

## 3. State & Union Territory Distribution (36 Jurisdictions)

The complete state-by-state aggregation is published in:  
`data/processed/geospatial/healthcare/india_healthcare_state_summary.csv`

### 3.1 Top 10 States by Healthcare Density
| Rank | State / Union Territory | Total Facilities | Hospitals | Primary Health Centres | Clinics | Pharmacies & Doctors |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | **Maharashtra** | 14,036 | 7,072 | 4,388 | 1,829 | 747 |
| 2 | **Tamil Nadu** | 11,107 | 5,681 | 1,560 | 2,814 | 1,052 |
| 3 | **Uttar Pradesh** | 9,275 | 3,635 | 4,554 | 763 | 323 |
| 4 | **Telangana** | 9,101 | 2,643 | 633 | 1,590 | 4,235 |
| 5 | **Gujarat** | 8,353 | 4,955 | 1,742 | 1,381 | 275 |
| 6 | **Karnataka** | 8,139 | 3,196 | 999 | 2,396 | 1,548 |
| 7 | **Rajasthan** | 7,826 | 2,718 | 3,616 | 1,105 | 387 |
| 8 | **Bihar** | 6,403 | 742 | 4,978 | 474 | 209 |
| 9 | **Madhya Pradesh** | 6,401 | 2,135 | 2,427 | 942 | 897 |
| 10 | **Punjab** | 6,271 | 2,929 | 1,872 | 1,121 | 349 |

### 3.2 Bottom 5 Jurisdictions
| State / Union Territory | Total Facilities | Hospitals | PHCs / Centres | Clinics & Other |
| :--- | :---: | :---: | :---: | :---: |
| **Dadra & Nagar Haveli** | 62 | 22 | 40 | 0 |
| **Chandigarh** | 61 | 23 | 5 | 33 |
| **Andaman & Nicobar Islands** | 23 | 13 | 3 | 7 |
| **Daman & Diu** | 23 | 11 | 9 | 3 |
| **Lakshadweep** | 0 | 0 | 0 | 0 |

---

## 4. District-Level Analysis (641 Census Districts)

The full district schedule is published in:  
`data/processed/geospatial/healthcare/india_healthcare_district_summary.csv`

### 4.1 Districts with Zero Mapped Facilities (3 Districts)
1. **Diu District** (Daman & Diu, Census Code: `494.0`): 0 mapped points.
2. **Nicobar District** (Andaman & Nicobar Islands, Census Code: `638.0`): 0 mapped points.
3. **Lakshadweep District** (UT of Lakshadweep, Census Code: `587.0`): 0 mapped points.

> [!IMPORTANT]
> **Interpretation Warning:** Zero mapped features in OpenStreetMap does **NOT** indicate that healthcare infrastructure is absent in these districts. Diu, Nicobar, and Lakshadweep possess operational government district hospitals and community health centres operated by the Ministry of Health & Family Welfare. The zero count reflects a volunteer mapping gap in OpenStreetMap contributors.

### 4.2 Districts with Sparsely Mapped Infrastructure (1–9 Facilities)
A total of **24 districts** possess between 1 and 9 mapped facilities. These are primarily located in:
* **Himalayan / High-Altitude Corridors:** Kargil (9), Doda (8), Kishtwar (7), Leh (5), Lahul & Spiti (4), Kinnaur (5).
* **Northeastern Frontier States:** Upper Siang (9), Longleng (8), Peren (8), Tawang (8), Anjaw (7), Lower Dibang Valley (7), Kurung Kumey (6), Dibang Valley (4).

---

## 5. Operational Guidelines for Disaster Response

1. **Urban & Peninsular India Triage:** In major metropolitan centers and states like Maharashtra, Tamil Nadu, and Karnataka, the dataset provides fine-grained facility locations suitable for routing injured populations, estimating bed capacity, and staging mobile ambulances.
2. **Rural & Frontier Hazard Response:** When evaluating flood or landslide impacts in Arunachal Pradesh, Ladakh, or island groups, SCOUT services must note that OpenStreetMap facility density is incomplete and should supplement this layer with official state disaster management authority (SDMA) health directory records.
