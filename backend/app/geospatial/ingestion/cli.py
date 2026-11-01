"""
backend/app/geospatial/ingestion/cli.py
Administrative CLI command for batch geospatial ingestion.
Usage:
  python -m app.geospatial.ingestion.cli --file path/to/features.geojson --layer critical_facilities [options]
"""

import argparse
import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.geospatial.ingestion.schemas import (
    ConflictPolicy,
    IngestionOptions,
    SourceRegistrationCreate,
)
from app.geospatial.ingestion.pipeline import (
    GeospatialIngestionPipeline,
    GeospatialIngestionError,
)


def main():
    parser = argparse.ArgumentParser(
        description="SCOUT Persistent Geospatial Data Ingestion CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--file", "-f", required=True, type=str, help="Path to input GeoJSON file")
    parser.add_argument("--layer", "-l", required=True, type=str, help="Canonical layer name (e.g. critical_facilities, hydrology)")
    parser.add_argument("--provider", type=str, default="openstreetmap", help="External data provider identifier")
    parser.add_argument("--dataset", type=str, default="osm_features", help="Dataset name")
    parser.add_argument("--license", type=str, default="ODbL-1.0", help="Data license identifier")
    parser.add_argument("--attribution", type=str, default="Data © OpenStreetMap contributors, ODbL 1.0", help="Attribution notice")
    parser.add_argument("--aoi", type=str, default=None, help="Area of interest canonical tag (e.g. in_dehradun_basin)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate ingestion without modifying database")
    parser.add_argument(
        "--conflict-policy",
        choices=["upsert", "skip_existing", "fail_on_conflict"],
        default="upsert",
        help="Conflict policy for existing feature IDs",
    )
    parser.add_argument("--batch-size", type=int, default=250, help="Features per commit batch")

    args = parser.parse_args()

    input_file = Path(args.file)
    if not input_file.exists():
        print(f"Error: File '{args.file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print("=================================================================")
    print("  SCOUT Geospatial Ingestion Subsystem (Milestone 10)")
    print("=================================================================")
    print(f"  Input File:       {input_file.resolve()}")
    print(f"  Target Layer:     {args.layer}")
    print(f"  Provider:         {args.provider} ({args.dataset})")
    print(f"  License:          {args.license}")
    print(f"  Area of Interest: {args.aoi or 'global/unspecified'}")
    print(f"  Dry Run:          {args.dry_run}")
    print(f"  Conflict Policy:  {args.conflict_policy}")
    print("-----------------------------------------------------------------")

    db = SessionLocal()
    try:
        pipeline = GeospatialIngestionPipeline(db)

        # 1. Register or get data source
        source_in = SourceRegistrationCreate(
            provider=args.provider,
            dataset_name=args.dataset,
            license_identifier=args.license,
            attribution_text=args.attribution,
            source_crs="EPSG:4326",
        )
        source = pipeline.register_or_get_source(source_in)
        print(f"  Registered Source ID: {source.id}")

        # 2. Execute ingestion
        options = IngestionOptions(
            layer_name=args.layer,
            area_of_interest=args.aoi,
            dry_run=args.dry_run,
            conflict_policy=ConflictPolicy(args.conflict_policy),
            batch_size=args.batch_size,
        )

        summary = pipeline.ingest_geojson(
            source_id=source.id,
            geojson_source=input_file,
            options=options,
        )

        print("-----------------------------------------------------------------")
        print(f"  Ingestion Status:   {summary.status.value.upper()}")
        print(f"  Ingestion Run ID:   {summary.id}")
        print(f"  Total Features:     {summary.total_features}")
        print(f"  Inserted:           {summary.inserted_features}")
        print(f"  Updated:            {summary.updated_features}")
        print(f"  Skipped:            {summary.skipped_features}")
        print(f"  Rejected (Invalid): {summary.rejected_features}")
        if summary.error_summary:
            print("  Rejection Samples:")
            for line in summary.error_summary.split("\n")[:5]:
                print(f"    - {line}")
        print("=================================================================")
        print("Ingestion execution completed successfully.")
    except GeospatialIngestionError as exc:
        print(f"\n[Ingestion Error]: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"\n[Fatal Error]: {exc}", file=sys.stderr)
        sys.exit(3)
    finally:
        db.close()


if __name__ == "__main__":
    main()
