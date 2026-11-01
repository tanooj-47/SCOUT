"""
backend/app/geospatial/ingestion/pipeline.py
Bounded batch GeoJSON ingestion pipeline for persistent real-world geographic features.
Milestone 10: Persistent Geospatial Data Integration.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import uuid
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.geospatial import (
    GeographicDataSource,
    GeographicIngestionRun,
    GeographicFeature,
)
from app.geospatial.ingestion.schemas import (
    ConflictPolicy,
    IngestionOptions,
    IngestionRunSummary,
    IngestionStatus,
    NormalizedFeature,
    SourceRegistrationCreate,
)
from app.geospatial.ingestion.normalizer import (
    normalize_feature,
    FeatureNormalizationError,
)

logger = logging.getLogger(__name__)


class GeospatialIngestionError(Exception):
    """Raised when ingestion cannot be completed."""
    pass


class GeospatialIngestionPipeline:
    """
    Production-grade ingestion pipeline for external GIS layers.
    Enforces:
    1. Bounded batch commits to avoid memory spikes.
    2. Explicit audit tracking via GeographicIngestionRun.
    3. Dry-run simulation mode without state modification.
    4. Deterministic deduplication via (source_id, source_feature_id, layer_name).
    5. Checksum verification for reproducible data lineage.
    """

    def __init__(self, db: Session):
        self.db = db

    def register_or_get_source(
        self,
        source_in: SourceRegistrationCreate,
    ) -> GeographicDataSource:
        """
        Retrieves existing source by (provider, dataset_name) or registers a new source.
        """
        stmt = select(GeographicDataSource).where(
            and_(
                GeographicDataSource.provider == source_in.provider,
                GeographicDataSource.dataset_name == source_in.dataset_name,
            )
        )
        existing = self.db.scalars(stmt).first()
        if existing:
            return existing

        new_source = GeographicDataSource(
            id=uuid.uuid4(),
            provider=source_in.provider,
            dataset_name=source_in.dataset_name,
            dataset_version=source_in.dataset_version,
            source_url=source_in.source_url,
            license_identifier=source_in.license_identifier,
            attribution_text=source_in.attribution_text,
            source_crs=source_in.source_crs,
            metadata_payload=source_in.metadata_payload,
        )
        self.db.add(new_source)
        self.db.commit()
        self.db.refresh(new_source)
        return new_source

    def ingest_geojson(
        self,
        source_id: uuid.UUID,
        geojson_source: Union[str, Path, Dict[str, Any]],
        options: IngestionOptions,
    ) -> IngestionRunSummary:
        """
        Ingests a GeoJSON feature collection or file into PostGIS.
        Supports dry-run validation, conflict resolution, and batch processing.
        """
        # 1. Verify source
        source = self.db.get(GeographicDataSource, source_id)
        if not source:
            raise GeospatialIngestionError(f"GeographicDataSource with id '{source_id}' does not exist.")

        # 2. Extract payload, file name, and checksum
        file_name: Optional[str] = None
        file_checksum: Optional[str] = None

        if isinstance(geojson_source, (str, Path)) and (isinstance(geojson_source, Path) or ("\n" not in geojson_source and "{" not in geojson_source and Path(geojson_source).exists())):
            file_path = Path(geojson_source)
            if not file_path.is_file():
                raise GeospatialIngestionError(f"Source file not found: {file_path}")
            file_name = file_path.name
            with open(file_path, "rb") as f:
                content_bytes = f.read()
            file_checksum = hashlib.sha256(content_bytes).hexdigest()
            try:
                data = json.loads(content_bytes.decode("utf-8"))
            except Exception as exc:
                raise GeospatialIngestionError(f"Failed to parse JSON file {file_path}: {exc}")
        elif isinstance(geojson_source, str):
            content_bytes = geojson_source.encode("utf-8")
            file_checksum = hashlib.sha256(content_bytes).hexdigest()
            file_name = f"inline_payload_{file_checksum[:8]}.geojson"
            try:
                data = json.loads(geojson_source)
            except Exception as exc:
                raise GeospatialIngestionError(f"Failed to parse inline JSON string: {exc}")
        elif isinstance(geojson_source, dict):
            data = geojson_source
            file_name = "in_memory_dict.geojson"
            serialized = json.dumps(data, sort_keys=True).encode("utf-8")
            file_checksum = hashlib.sha256(serialized).hexdigest()
        else:
            raise GeospatialIngestionError(f"Unsupported GeoJSON source type: {type(geojson_source)}")

        # 3. Extract feature list
        if data.get("type") == "FeatureCollection":
            raw_features = data.get("features", [])
        elif data.get("type") == "Feature":
            raw_features = [data]
        elif isinstance(data, list):
            raw_features = data
        else:
            raise GeospatialIngestionError("Invalid GeoJSON: must be FeatureCollection, Feature, or list of Features")

        # 4. Initialize Ingestion Run audit record
        run_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)
        ingestion_run = GeographicIngestionRun(
            id=run_id,
            source_id=source.id,
            layer_name=options.layer_name,
            area_of_interest=options.area_of_interest,
            source_file_name=file_name,
            source_checksum=file_checksum,
            started_at=started_at,
            status=IngestionStatus.DRY_RUN.value if options.dry_run else IngestionStatus.IN_PROGRESS.value,
            total_features=len(raw_features),
            inserted_features=0,
            updated_features=0,
            skipped_features=0,
            rejected_features=0,
        )

        if not options.dry_run:
            self.db.add(ingestion_run)
            self.db.commit()

        # 5. Process features in batches
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        rejected_count = 0
        errors: List[str] = []

        batch_features_to_insert: List[GeographicFeature] = []

        try:
            for idx, raw_feat in enumerate(raw_features):
                try:
                    norm = normalize_feature(
                        raw_feat,
                        layer_name=options.layer_name,
                        source_crs=source.source_crs,
                    )
                except (FeatureNormalizationError, Exception) as exc:
                    rejected_count += 1
                    err_msg = f"Feature index {idx} invalid: {exc}"
                    logger.debug(err_msg)
                    if len(errors) < 100:  # Cap stored errors
                        errors.append(err_msg)
                    continue

                if options.dry_run:
                    # In dry-run, check existence without persisting
                    stmt = select(GeographicFeature.id).where(
                        and_(
                            GeographicFeature.source_id == source.id,
                            GeographicFeature.source_feature_id == norm.source_feature_id,
                            GeographicFeature.layer_name == norm.layer_name,
                        )
                    )
                    existing_id = self.db.scalars(stmt).first()
                    if existing_id:
                        if options.conflict_policy == ConflictPolicy.UPSERT:
                            updated_count += 1
                        elif options.conflict_policy == ConflictPolicy.SKIP_EXISTING:
                            skipped_count += 1
                        else:
                            raise GeospatialIngestionError(
                                f"Conflict on dry-run: feature {norm.source_feature_id} already exists."
                            )
                    else:
                        inserted_count += 1
                    continue

                # Live ingestion mode: check conflict policy
                stmt = select(GeographicFeature).where(
                    and_(
                        GeographicFeature.source_id == source.id,
                        GeographicFeature.source_feature_id == norm.source_feature_id,
                        GeographicFeature.layer_name == norm.layer_name,
                    )
                )
                existing_feat = self.db.scalars(stmt).first()

                if existing_feat:
                    if options.conflict_policy == ConflictPolicy.UPSERT:
                        existing_feat.name = norm.name
                        existing_feat.category = norm.category.value
                        existing_feat.properties = norm.properties
                        existing_feat.geometry = WKTElement(norm.geometry_wkt, srid=4326)
                        existing_feat.geometry_type = norm.geometry_type
                        existing_feat.hazard_relevance = norm.hazard_relevance
                        existing_feat.ingestion_run_id = run_id
                        existing_feat.updated_at = datetime.now(timezone.utc)
                        updated_count += 1
                    elif options.conflict_policy == ConflictPolicy.SKIP_EXISTING:
                        skipped_count += 1
                    elif options.conflict_policy == ConflictPolicy.FAIL_ON_CONFLICT:
                        raise GeospatialIngestionError(
                            f"Conflict: feature {norm.source_feature_id} already exists in layer {options.layer_name}."
                        )
                else:
                    new_feat = GeographicFeature(
                        id=uuid.uuid4(),
                        source_id=source.id,
                        ingestion_run_id=run_id,
                        layer_name=norm.layer_name,
                        category=norm.category.value,
                        source_feature_id=norm.source_feature_id,
                        name=norm.name,
                        properties=norm.properties,
                        geometry=WKTElement(norm.geometry_wkt, srid=4326),
                        geometry_type=norm.geometry_type,
                        source_crs="EPSG:4326",
                        hazard_relevance=norm.hazard_relevance,
                    )
                    batch_features_to_insert.append(new_feat)
                    inserted_count += 1

                # Flush batch
                if len(batch_features_to_insert) >= options.batch_size:
                    self.db.add_all(batch_features_to_insert)
                    self.db.flush()
                    batch_features_to_insert.clear()

            # Flush remaining inserts
            if not options.dry_run and batch_features_to_insert:
                self.db.add_all(batch_features_to_insert)
                self.db.flush()
                batch_features_to_insert.clear()

            completed_at = datetime.now(timezone.utc)
            final_status = IngestionStatus.DRY_RUN if options.dry_run else IngestionStatus.COMPLETED
            err_summary = "\n".join(errors) if errors else None

            if not options.dry_run:
                ingestion_run.status = final_status.value
                ingestion_run.completed_at = completed_at
                ingestion_run.inserted_features = inserted_count
                ingestion_run.updated_features = updated_count
                ingestion_run.skipped_features = skipped_count
                ingestion_run.rejected_features = rejected_count
                ingestion_run.error_summary = err_summary
                self.db.commit()

            return IngestionRunSummary(
                id=run_id,
                source_id=source.id,
                layer_name=options.layer_name,
                area_of_interest=options.area_of_interest,
                source_file_name=file_name,
                source_checksum=file_checksum,
                started_at=started_at,
                completed_at=completed_at,
                total_features=len(raw_features),
                inserted_features=inserted_count,
                updated_features=updated_count,
                skipped_features=skipped_count,
                rejected_features=rejected_count,
                status=final_status,
                error_summary=err_summary,
            )

        except Exception as exc:
            if not options.dry_run:
                self.db.rollback()
                try:
                    ingestion_run.status = IngestionStatus.FAILED.value
                    ingestion_run.completed_at = datetime.now(timezone.utc)
                    ingestion_run.error_summary = f"Fatal ingestion exception: {str(exc)}"
                    self.db.commit()
                except Exception:
                    pass
            raise GeospatialIngestionError(f"Ingestion failed: {exc}") from exc
