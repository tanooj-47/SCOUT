# SCOUT — WorldPop Semantic & Raster Validation Report

**Subsystem:** M10 Persistent Geospatial Data Integration  
**Component:** Nationwide Population Exposure Layer  
**Date:** October 31, 2026  
**Auditor:** Senior Geospatial Data Engineer & Disaster-Intelligence Systems Architect  
**Validation Status:** `MODELLED_NATIONAL_SURFACE (SEMANTICS_VERIFIED_ACCURACY_UNVERIFIED)`

---

## 1. Product Identification & Provenance

* **Product Filename:** `ind_pd_2020_1km.tif`
* **Relative Path:** `data/raw/geospatial/population/worldpop/ind_pd_2020_1km.tif`
* **File Size:** 18,081,300 bytes (17.24 MB)
* **SHA-256 Checksum:** `7854911bee96ec61cd56f8209cbc3992bcd13e2aeba7b9d852b76df390f393dc`
* **MD5 Checksum:** `c3af00c1bb6ba461da1acb7bcc9cc82a`
* **Original Provider:** WorldPop Research Group, University of Southampton (School of Geography and Environmental Science), in partnership with CIESIN (Center for International Earth Science Information Network, Columbia University).
* **Official Repository:** `https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/`
* **DOI / Citation:** WorldPop (2018). Global 1km Population Density Grids 2000–2020. University of Southampton. DOI: 10.5258/SOTON/WP00660.
* **Licensing:** Creative Commons Attribution 4.0 International (CC BY 4.0). Fully authorized for academic, commercial, and operational use with attribution.

---

## 2. Semantic Analysis: Count vs. Density

A critical question raised in the independent engineering audit was whether `ind_pd_2020_1km.tif` represents:
1. **Population Count per Pixel (`ppp`)**, or
2. **Population Density (`pd`)** in people per square kilometer.

### 2.1 Provider Naming Nomenclature
WorldPop standardizes its raster distribution filenames across two distinct product branches:
* `[iso3]_ppp_[year]_[resolution].tif`: Population per Pixel (dasymetrically disaggregated absolute head count within the pixel bounds).
* `[iso3]_pd_[year]_[resolution].tif`: **Population Density** (number of people per square kilometer).

The acquired file is named `ind_pd_2020_1km.tif`, explicitly carrying the `pd` mnemonic for **Population Density**.

### 2.2 Embedded GeoTIFF Metadata & Tags
Physical header inspection via PIL and GDAL metadata tags revealed:
```xml
<GDALMetadata>
  <Item name="STATISTICS_MAXIMUM" sample="0">235668.140625</Item>
  <Item name="STATISTICS_MEAN" sample="0">447.08389189264</Item>
  <Item name="STATISTICS_MINIMUM" sample="0">0</Item>
  <Item name="STATISTICS_STDDEV" sample="0">1370.4748812832</Item>
</GDALMetadata>
```
* **NoData Value:** `-99999.0`
* **Data Type:** 32-bit Floating Point (`Float32`)
* **Coordinate Reference System:** EPSG:4326 (WGS 84 geographic coordinates)
* **Pixel Resolution:** Exactly `0.0083333333` degrees (~30 arc-seconds / 928 meters at equator).
* **Grid Dimensions:** 3,508 columns × 3,451 rows (12,106,108 total grid cells).
* **Bounding Envelope:**
  - West: `68.182083°E`
  - East: `97.415416°E`
  - South: `6.749583°N`
  - North: `35.507917°N`

### 2.3 Verified Measurement Metric and Units
* **True Metric:** **Population Density**
* **Standard Unit:** **$\text{persons}/\text{km}^2$ (People per square kilometer)**

---

## 3. Statistical Distribution & Maximum Value Investigation

The raster contains **4,010,402 valid landmass data cells** (33.13% of the grid envelope, precisely conforming to India's sovereign territory; remaining 66.87% are marine or extra-territorial `-99999.0` NoData cells).

### 3.1 Statistical Summary (Valid Cells Only)
* **Minimum:** $0.0000\text{ persons}/\text{km}^2$
* **Maximum:** $235,668.1406\text{ persons}/\text{km}^2$
* **Mean:** $447.0839\text{ persons}/\text{km}^2$
* **Median:** $202.0351\text{ persons}/\text{km}^2$
* **Standard Deviation:** $1,370.4750\text{ persons}/\text{km}^2$
* **75th Percentile:** $462.1502\text{ persons}/\text{km}^2$
* **90th Percentile:** $963.1211\text{ persons}/\text{km}^2$
* **95th Percentile:** $1,420.1323\text{ persons}/\text{km}^2$
* **99th Percentile:** $3,516.8164\text{ persons}/\text{km}^2$
* **99.9th Percentile:** $18,126.6445\text{ persons}/\text{km}^2$
* **Sum of Pixel Densities:** $1,792,986,112.00$

### 3.2 Geographic Audit of the Maximum Value ($235,668.14$)
The cell exhibiting the maximum value was located at:
* **Longitude:** $88.3029^\circ\text{E}$
* **Latitude:** $22.4871^\circ\text{N}$
* **Raster Coordinates:** Row 1,562, Column 2,414

Spatial verification demonstrates that this coordinate falls in the **Behala / South 24 Parganas / Kolkata municipal agglomeration** in West Bengal. 

Other top density peaks in the raster include:
1. `88.3029°E, 22.4788°N`: $209,507.31\text{ persons}/\text{km}^2$ (Kolkata South corridor)
2. `88.3029°E, 22.4954°N`: $184,082.97\text{ persons}/\text{km}^2$ (Kolkata West/South urban ward)
3. `88.2946°E, 22.4871°N`: $170,152.84\text{ persons}/\text{km}^2$ (Kolkata urban core)
4. `72.8196°E, 21.1871°N`: $124,825.42\text{ persons}/\text{km}^2$ (Surat Central Wards, Gujarat)
5. `88.4196°E, 22.6121°N`: $122,838.97\text{ persons}/\text{km}^2$ (Baranagar / Kamarhati, North 24 Parganas)
6. `72.8112°E, 21.1788°N`: $119,051.76\text{ persons}/\text{km}^2$ (Surat Old City, Gujarat)

### 3.3 Separation of Coverage, Semantics, and Estimation Accuracy

To maintain scientific integrity, three distinct spatial and demographic concepts must be strictly separated:
1. **Geographic Coverage:** The raster envelope ($3508 \times 3451$ pixels) and valid footprint (4,010,402 valid data pixels) span the entire national extent of India ($68.18^\circ\text{E}–97.42^\circ\text{E}, 6.75^\circ\text{N}–35.51^\circ\text{N}$). **National geographic coverage is verified.**
2. **Product Semantics:** Filename mnemonic (`ind_pd_...`), repository path (`/Population_Density/`), and embedded GDAL metadata confirm the metric is **modelled population density in persons per square kilometer** ($\text{persons}/\text{km}^2$), rather than raw headcount per pixel (`ppp`). **Product semantics are verified.**
3. **Estimation Accuracy & Ground-Truth Caveats:**
   - WorldPop produces this surface through a Random Forest dasymetric disaggregation model that redistributes administrative census totals across built-settlement morphological covariates.
   - The localized peak density of $235,668.14\text{ persons}/\text{km}^2$ located at $88.3029^\circ\text{E}, 22.4871^\circ\text{N}$ (Kolkata urban continuum) demonstrates how machine learning covariates concentrate population into built-up pixels. However, **attributing this peak to specific ward-level ground truth is an unverified statistical interpretation**, NOT independent empirical validation.
   - **National geographic coverage does NOT establish population-estimation accuracy.** No independent ground-truth census enumeration block cross-tabulation or local validation surveys were performed in this evaluation.
   - **Documentation Availability Limitation:** While official provider URLs (`hub.worldpop.org`) and DOIs (`10.5258/SOTON/WP00660`) are cataloged in repository manifests, no local offline copy of the official PDF methodology manual or ground-truth survey reports exists in the repository.

---

## 4. Disaster Intelligence Integration Guidelines

### 4.1 How to Compute Total Affected Population from Density
Because this layer represents **density per square kilometer** on a WGS 84 geographic grid (`EPSG:4326`), pixel area decreases with latitude as meridians converge:
$$\text{Area}_{\text{pixel}}(\phi) \approx (R \cdot \Delta\lambda \cos\phi) \times (R \cdot \Delta\phi)$$
Where:
* $R = 6,371\text{ km}$
* $\Delta\lambda = \Delta\phi = 0.0083333333^\circ = 0.000145444\text{ radians}$
* At latitude $8^\circ\text{N}$ (Southern tip): $\text{Area} \approx 0.928 \times (0.928 \cdot \cos(8^\circ)) \approx 0.853\text{ km}^2$.
* At latitude $35^\circ\text{N}$ (Northern frontier): $\text{Area} \approx 0.928 \times (0.928 \cdot \cos(35^\circ)) \approx 0.705\text{ km}^2$.

To calculate the absolute number of people exposed to a disaster perimeter (e.g., wildfire evacuation zone or flood inundation polygon):
$$\text{Exposed Population} = \sum_{i \in \text{Hazard Polygon}} \left( \text{RasterValue}_i \times \text{CellArea}_i(\phi_i) \right)$$

> [!CAUTION]
> **Do NOT directly sum cell values** to obtain affected head counts without multiplying by pixel area. Direct summation will overestimate population counts by 15% to 40% depending on latitude.

### 4.2 Integration Verdict & Conservative Classification
* **Classification Status:** **`MODELLED_NATIONAL_SURFACE (SEMANTICS_VERIFIED_ACCURACY_UNVERIFIED)`**
* **Disaster Exposure Readiness:** **READY FOR MACRO-LEVEL MODELING** with mandatory latitude-adjusted cell area weighting; local micro-level absolute accuracy must not be assumed without sub-district calibration.
