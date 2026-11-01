"""
backend/app/geospatial/acquisition/cli.py
National Geographic Data Acquisition Administrative CLI.
Provides discovery, preflight storage validation, dry-run simulation,
manifest generation, and resumable downloading across all approved India datasets.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Dict, List, Optional

from app.geospatial.acquisition.manifest import (
    AcquisitionState,
    DatasetManifest,
    ProcessingStatus,
    ValidationStatus,
)
from app.geospatial.acquisition.downloader import (
    DownloadResult,
    InsufficientDiskSpaceError,
    ResumableDownloader,
    check_available_disk_space,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("scout.acquisition")

# Canonical India Bounding Box: [min_lon, min_lat, max_lon, max_lat]
INDIA_BBOX = [68.1, 6.5, 97.4, 35.5]

DATASET_DEFINITIONS: Dict[str, dict] = {
    "osm": {
        "dataset_id": "osm_india_pbf_latest",
        "dataset_name": "OpenStreetMap India Complete Regional Extract",
        "provider": "openstreetmap",
        "official_source_url": "https://download.geofabrik.de/asia/india.html",
        "download_url": "https://download.geofabrik.de/asia/india-latest.osm.pbf",
        "checksum_url": "https://download.geofabrik.de/asia/india-latest.osm.pbf.md5",
        "product_name": "osm_india_pbf",
        "product_version": "latest",
        "geographic_coverage": "India-wide (national coverage across all States and UTs)",
        "license": "ODbL-1.0",
        "attribution": "Data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
        "original_filename": "india-latest.osm.pbf",
        "file_format": "osm.pbf",
        "estimated_size_bytes": 1717986918,  # ~1.6 GB
        "target_relative_path": "data/raw/geospatial/osm/india/india-latest.osm.pbf",
        "crs": "EPSG:4326",
        "spatial_resolution": "vector",
        "coordinate_bounds": INDIA_BBOX,
        "credentials_required": False,
        "operational_use_restrictions": (
            "Governed by Open Database License (ODbL 1.0). Derivative databases must share-alike. "
            "Volunteered geographic information; density is high in urban centers and variable in rural forest tracts."
        ),
        "quality_notes": [
            "Primary source for national roads, railways, hospitals, fire stations, waterways, and settlements.",
            "Must be downloaded once and split into thematic layers to prevent redundant transfers.",
        ],
    },
    "soi": {
        "dataset_id": "soi_abdb_national",
        "dataset_name": "Survey of India Administrative Boundary Data Base (ABDB)",
        "provider": "survey_of_india",
        "official_source_url": "https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-",
        "download_url": "https://onlinemaps.surveyofindia.gov.in/",
        "product_name": "abdb_national",
        "product_version": "2024",
        "geographic_coverage": "India-wide (State, District, Subdistrict, Village)",
        "license": "National Geospatial Policy / Survey of India Terms",
        "attribution": "Survey of India, Department of Science and Technology, Government of India",
        "original_filename": "soi_abdb_boundaries.zip",
        "file_format": "shapefile",
        "estimated_size_bytes": 367001600,  # ~350 MB
        "target_relative_path": "data/raw/geospatial/boundaries/survey_of_india/soi_abdb_boundaries.zip",
        "crs": "EPSG:4326",
        "spatial_resolution": "vector_1:50000",
        "coordinate_bounds": INDIA_BBOX,
        "credentials_required": True,
        "operational_use_restrictions": (
            "Requires user registration on onlinemaps.surveyofindia.gov.in with mobile OTP and identity verification. "
            "Export or transfer of sensitive boundary geometries outside India is restricted under national security policies."
        ),
        "quality_notes": [
            "Official sovereign boundaries of the Government of India.",
            "Automated public downloading is gated by government authentication. User must obtain files via official portal.",
        ],
    },
    "worldcover": {
        "dataset_id": "esa_worldcover_2021_india",
        "dataset_name": "ESA WorldCover 10m 2021 v200 Land Cover Grid",
        "provider": "esa_worldcover",
        "official_source_url": "https://esa-worldcover.org/en/data-access",
        "download_url": "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/",
        "product_name": "worldcover_10m_v200",
        "product_version": "2021_v200",
        "geographic_coverage": "India-wide (National Grid: 52 3x3 degree tiles)",
        "license": "CC-BY-4.0",
        "attribution": "© ESA WorldCover project 2021 / contains modified Copernicus Sentinel data",
        "original_filename": "ESA_WorldCover_10m_2021_v200_India_Grid.zip",
        "file_format": "geotiff",
        "estimated_size_bytes": 10737418240,  # ~10 GB complete grid; representative tiles ~250 MB each
        "target_relative_path": "data/raw/geospatial/land_cover/esa_worldcover",
        "crs": "EPSG:4326",
        "spatial_resolution": "10m",
        "coordinate_bounds": INDIA_BBOX,
        "nodata_value": 0,
        "credentials_required": False,
        "operational_use_restrictions": "Open commercial and non-commercial use with credit to ESA WorldCover.",
        "quality_notes": [
            "11 discrete land-cover classes (tree cover, shrubland, grassland, built-up, water bodies, mangroves).",
            "To respect storage budgets (<10 GB), national tile index is cataloged with prioritized hazard tile fetching.",
        ],
    },
    "ghsl": {
        "dataset_id": "ghsl_pop_r2023a_india",
        "dataset_name": "GHSL Global Human Settlement Population Grid (GHS-POP R2023A)",
        "provider": "ghsl",
        "official_source_url": "https://human-settlement.emergency.copernicus.eu/",
        "download_url": "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/GHS_POP_E2025_GLOBE_R2023A_54009_1000/V1-0/GHS_POP_E2025_GLOBE_R2023A_54009_1000_V1_0.zip",
        "product_name": "ghs_pop_r2023a",
        "product_version": "R2023A_epoch2025",
        "geographic_coverage": "India-wide (national coverage)",
        "license": "CC-BY-4.0",
        "attribution": "European Commission, Joint Research Centre (JRC) Global Human Settlement Layer",
        "original_filename": "GHS_POP_E2025_GLOBE_R2023A_54009_1000_V1_0.zip",
        "file_format": "geotiff",
        "estimated_size_bytes": 838860800,  # ~800 MB (1km national extract)
        "target_relative_path": "data/raw/geospatial/population/ghsl/GHS_POP_E2025_India_1km.zip",
        "crs": "EPSG:54009 / EPSG:4326",
        "spatial_resolution": "1000m (100m regional sub-tiles)",
        "coordinate_bounds": INDIA_BBOX,
        "nodata_value": -200,
        "credentials_required": False,
        "operational_use_restrictions": "Open commercial and academic use with CC BY 4.0 credit.",
        "quality_notes": [
            "Estimates residential resident population density per grid cell for disaster exposure assessment.",
            "Not an instantaneous headcount of individuals present during a disaster event.",
        ],
    },
    "copernicus_dem": {
        "dataset_id": "copernicus_dem_glo30_india",
        "dataset_name": "Copernicus DEM 30m Global Digital Surface Model (GLO-30)",
        "provider": "copernicus_dem",
        "official_source_url": "https://dataspace.copernicus.eu/",
        "download_url": "https://copernicus-dem-30m.s3.amazonaws.com/",
        "product_name": "copernicus_glo_30",
        "product_version": "GLO-30",
        "geographic_coverage": "India-wide (1x1 degree COG tile grid)",
        "license": "Open Access (Copernicus Data Policy)",
        "attribution": "© DLR e.V. and © Airbus Defence and Space GmbH (Copernicus DEM)",
        "original_filename": "Copernicus_DSM_COG_10_India_Grid.zip",
        "file_format": "geotiff",
        "estimated_size_bytes": 12884901888,  # ~12 GB complete grid; 25-50 MB per tile
        "target_relative_path": "data/raw/geospatial/elevation/copernicus_dem",
        "crs": "EPSG:4326 (EGM96 vertical datum)",
        "spatial_resolution": "30m",
        "coordinate_bounds": INDIA_BBOX,
        "nodata_value": -99999.0,
        "credentials_required": False,
        "operational_use_restrictions": "Open use under Copernicus Data Policy.",
        "quality_notes": [
            "Represents a Digital Surface Model (DSM) including canopy and structural elevations, not bare-earth DTM.",
            "Derived slopes and hydrological drainage models must document surface model characteristics.",
        ],
    },
    "bhuvan": {
        "dataset_id": "isro_bhuvan_flood_hazard_wms",
        "dataset_name": "ISRO Bhuvan Disaster Services — Flood Hazard & Inundation Layers",
        "provider": "isro_bhuvan",
        "official_source_url": "https://bhuvan.nrsc.gov.in/",
        "download_url": "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms",
        "product_name": "bhuvan_hazard_wms",
        "product_version": "operational_wms_1.1.1",
        "geographic_coverage": "India-wide (Major river basins: Brahmaputra, Ganga, Mahanadi, Godavari, Kosi)",
        "license": "Government of India / NRSC ISRO Terms of Service",
        "attribution": "ISRO / National Remote Sensing Centre (NRSC), Government of India",
        "original_filename": "bhuvan_flood_hazard_capabilities.xml",
        "file_format": "wms_ogc_service",
        "estimated_size_bytes": 1048576,  # Service metadata
        "target_relative_path": "data/raw/geospatial/flood/bhuvan/bhuvan_flood_wms_capabilities.xml",
        "crs": "EPSG:4326",
        "spatial_resolution": "1:50000 thematic / raster WMS stream",
        "coordinate_bounds": INDIA_BBOX,
        "credentials_required": False,
        "operational_use_restrictions": (
            "Service provides OGC WMS map imagery streams for situational awareness. "
            "Raw spatial geometry download is restricted to authorized government agencies."
        ),
        "quality_notes": [
            "Historical flood inundation zones derived from multi-temporal satellite sensors (RISAT, Sentinel-1, IRS).",
            "Subject to optical cloud cover gaps during active monsoonal storm events.",
        ],
    },
    "weather": {
        "dataset_id": "open_meteo_era5_india",
        "dataset_name": "Open-Meteo ERA5 / ERA5-Land Historical Climate Reanalysis",
        "provider": "open_meteo",
        "official_source_url": "https://open-meteo.com/en/docs/historical-weather-api",
        "download_url": "https://archive-api.open-meteo.com/v1/era5",
        "product_name": "ecmwf_era5_reanalysis",
        "product_version": "era5_land",
        "geographic_coverage": "India-wide (Climatic Reference Grids across 6 Agro-ecological Zones)",
        "license": "CC-BY-4.0",
        "attribution": "Meteorological data from Open-Meteo under CC BY 4.0; ECMWF Copernicus Climate Change Service",
        "original_filename": "open_meteo_india_climatic_grid.json",
        "file_format": "json",
        "estimated_size_bytes": 52428800,  # ~50 MB
        "target_relative_path": "data/raw/geospatial/weather/open_meteo_india_climatic_grid.json",
        "crs": "EPSG:4326",
        "spatial_resolution": "0.1 degree (~11km)",
        "temporal_resolution": "hourly / daily",
        "coordinate_bounds": INDIA_BBOX,
        "credentials_required": False,
        "operational_use_restrictions": "CC BY 4.0 license; free tier subject to 10,000 daily API calls.",
        "quality_notes": [
            "Provides temperature, humidity, precipitation, and 10m wind vectors for Canadian FWI calculation.",
            "Historical model reanalysis (ERA5), not direct physical weather station telemetry.",
        ],
    },
    "firms": {
        "dataset_id": "nasa_firms_nrt_india",
        "dataset_name": "NASA FIRMS Satellite Active Fire Observations (MODIS / VIIRS)",
        "provider": "nasa_firms",
        "official_source_url": "https://firms.modaps.eosdis.nasa.gov/",
        "download_url": "https://firms.modaps.eosdis.nasa.gov/api/area/csv/",
        "product_name": "firms_modis_viirs_nrt",
        "product_version": "NRT_v2",
        "geographic_coverage": "India-wide (national coverage)",
        "license": "NASA Earth Science Data Policy (Open Access / Public Domain)",
        "attribution": "NASA FIRMS, Earth Science Data and Information System (ESDIS) / LANCE",
        "original_filename": "firms_active_fire_india.csv",
        "file_format": "csv",
        "estimated_size_bytes": 15728640,  # ~15 MB
        "target_relative_path": "data/raw/geospatial/observations/nasa_firms/firms_active_fire_india.csv",
        "crs": "EPSG:4326",
        "spatial_resolution": "375m (VIIRS) / 1km (MODIS)",
        "temporal_resolution": "sub-daily satellite passes",
        "coordinate_bounds": INDIA_BBOX,
        "credentials_required": True,
        "operational_use_restrictions": "Requires NASA_FIRMS_MAP_KEY configured in environment or .env.",
        "quality_notes": [
            "Thermal radiation anomalies and Fire Radiative Power (FRP in MW).",
            "Satellite active fire observations; not ground-truth incident records.",
        ],
    },
}


def print_banner():
    print("=================================================================")
    print("  SCOUT National Geographic Data Acquisition Engine")
    print("  Subsystem: India-Wide Real-World Dataset Integration")
    print("=================================================================")


def execute_dry_run(sources: List[str], project_root: Path):
    print_banner()
    print("  MODE: DRY-RUN SIMULATION (NO FILES WILL BE DOWNLOADED)")
    print("-----------------------------------------------------------------")

    total_usage = shutil.disk_usage(str(project_root))
    free_gb = total_usage.free / (1024**3)
    total_gb = total_usage.total / (1024**3)

    print(f"  Drive Capacity:     {total_gb:.2f} GB")
    print(f"  Available Space:    {free_gb:.2f} GB")
    print(f"  Target Sources:     {len(sources)} requested")
    print("=================================================================\n")

    total_est_bytes = 0

    for key in sources:
        defn = DATASET_DEFINITIONS[key]
        est_sz = defn["estimated_size_bytes"]
        total_est_bytes += est_sz
        target_path = project_root / defn["target_relative_path"]

        is_ok, free_b, safe_b = check_available_disk_space(target_path, est_sz)

        print(f"[{key.upper()}] {defn['dataset_name']}")
        print(f"  Dataset ID:           {defn['dataset_id']}")
        print(f"  Provider:             {defn['provider']}")
        print(f"  Official Source URL:  {defn['official_source_url']}")
        print(f"  Download URL:         {defn['download_url']}")
        print(f"  Format:               {defn['file_format'].upper()} (CRS: {defn['crs']})")
        print(f"  Expected File Size:   {est_sz / (1024**2):.2f} MB ({est_sz / (1024**3):.2f} GB)")
        print(f"  Target Path:          {target_path}")
        print(f"  License Status:       {defn['license']}")
        print(f"  Attribution:          {defn['attribution'][:65]}...")
        print(f"  Credentials Needed:   {'YES (Action Required)' if defn['credentials_required'] else 'NO (Open Access)'}")
        print(f"  Disk Space Preflight: {'PASSED' if is_ok else 'FAILED (Insufficient Free Space)'}")
        print(f"  Geographic Bounds:    {defn['coordinate_bounds']}")
        print(f"  Operational Notes:    {defn['operational_use_restrictions'][:80]}...")
        print("-----------------------------------------------------------------")

    print(f"\nTotal Estimated Raw Storage: {total_est_bytes / (1024**3):.2f} GB")
    print(f"Available Free Disk Space:   {free_gb:.2f} GB")
    if free_gb < (total_est_bytes / (1024**3)) * 2.0:
        print("WARNING: Complete concurrent download of all full national datasets would stress disk budget.")
        print("RECOMMENDATION: Use prioritized incremental acquisition (OSM PBF + Representative Tiles).")
    else:
        print("STATUS: Disk budget sufficient for incremental phased acquisition.")
    print("=================================================================")


def generate_all_manifests(project_root: Path):
    manifests_dir = project_root / "data" / "manifests" / "geospatial"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for key, defn in DATASET_DEFINITIONS.items():
        state = AcquisitionState.SOURCE_DISCOVERED
        proc_status = ProcessingStatus.RESTRICTED if defn["credentials_required"] else ProcessingStatus.RAW

        target_file = project_root / defn["target_relative_path"]
        actual_size = None
        sha256_val = None

        if target_file.is_file() and target_file.exists():
            state = AcquisitionState.DOWNLOAD_COMPLETED
            actual_size = target_file.stat().st_size

        manifest = DatasetManifest(
            dataset_id=defn["dataset_id"],
            dataset_name=defn["dataset_name"],
            provider=defn["provider"],
            official_source_url=defn["official_source_url"],
            download_url=defn["download_url"],
            product_name=defn["product_name"],
            product_version=defn["product_version"],
            acquisition_state=state,
            acquisition_timestamp_utc=datetime.now(timezone.utc).isoformat(),
            geographic_coverage=defn["geographic_coverage"],
            license=defn["license"],
            attribution=defn["attribution"],
            original_filename=defn["original_filename"],
            file_format=defn["file_format"],
            file_size_bytes=actual_size or defn["estimated_size_bytes"],
            sha256=sha256_val,
            crs=defn["crs"],
            spatial_resolution=defn.get("spatial_resolution"),
            temporal_resolution=defn.get("temporal_resolution"),
            coordinate_bounds=defn["coordinate_bounds"],
            nodata_value=defn.get("nodata_value"),
            processing_status=proc_status,
            validation_status=ValidationStatus.UNVALIDATED,
            quality_notes=defn.get("quality_notes", []),
            operational_use_restrictions=defn.get("operational_use_restrictions"),
            metadata_payload={"credentials_required": defn["credentials_required"]},
        )
        saved_path = manifest.save_to_directory(manifests_dir)
        generated.append(saved_path)

    print(f"Generated {len(generated)} official dataset manifests in {manifests_dir}.")
    return generated


def main():
    parser = argparse.ArgumentParser(description="SCOUT National Geographic Data Acquisition CLI")
    parser.add_argument(
        "--source",
        choices=["all", "osm", "soi", "worldcover", "ghsl", "copernicus_dem", "bhuvan", "weather", "firms"],
        default="all",
        help="Target geographic dataset to inspect or download",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate acquisition without downloading files")
    parser.add_argument("--generate-manifests", action="store_true", help="Generate machine-readable JSON manifests")
    parser.add_argument("--timeout", type=float, default=120.0, help="Download timeout in seconds")
    parser.add_argument("--retries", type=int, default=5, help="Maximum download retry attempts")

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    # Ensure project_root is the workspace root C:\Users\TANOOJ\OneDrive\Desktop\SCOUT
    if not (project_root / "backend").exists():
        project_root = Path(os.getcwd())

    sources = list(DATASET_DEFINITIONS.keys()) if args.source == "all" else [args.source]

    if args.dry_run:
        execute_dry_run(sources, project_root)

    if args.generate_manifests or args.dry_run:
        generate_all_manifests(project_root)


if __name__ == "__main__":
    main()
