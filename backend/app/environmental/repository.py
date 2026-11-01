import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.environmental.schemas import (
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)
from app.models.environmental_observation import (
    EnvironmentalObservation,
    IncidentEnvironmentalObservation,
)


class EnvironmentalRepository:
    """
    Data access layer for environmental observations, managing persistence,
    idempotent storage, queries, and incident spatial associations.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, observation_id: UUID) -> Optional[EnvironmentalObservation]:
        """Fetch single observation by primary key UUID."""
        return self.session.get(EnvironmentalObservation, observation_id)

    def find_existing_observation(
        self,
        item: EnvironmentalObservationItem,
    ) -> Optional[EnvironmentalObservation]:
        """
        Locates an existing observation record matching the unique constraints.
        """
        query = select(EnvironmentalObservation).where(
            and_(
                EnvironmentalObservation.location_type == item.location_type.value,
                EnvironmentalObservation.location_id == item.location_id,
                EnvironmentalObservation.provider == item.provider,
                EnvironmentalObservation.dataset_or_model == item.dataset_or_model,
                EnvironmentalObservation.typology == item.typology.value,
                EnvironmentalObservation.valid_time_utc == item.valid_time_utc,
            )
        )
        if item.typology == EnvironmentalTypology.FORECAST:
            query = query.where(
                and_(
                    EnvironmentalObservation.init_time_utc == item.init_time_utc,
                    EnvironmentalObservation.lead_time_hours == item.lead_time_hours,
                )
            )
        elif item.typology == EnvironmentalTypology.DERIVED:
            query = query.where(
                and_(
                    EnvironmentalObservation.algorithm_name == item.algorithm_name,
                    EnvironmentalObservation.algorithm_version == item.algorithm_version,
                    EnvironmentalObservation.source_fingerprint == item.source_fingerprint,
                )
            )

        return self.session.execute(query).scalar_one_or_none()

    def upsert_observation(
        self,
        item: EnvironmentalObservationItem,
    ) -> EnvironmentalObservation:
        """
        Idempotently inserts or updates an environmental observation.
        If already exists, updates retrieval timestamp and variables.
        """
        existing = self.find_existing_observation(item)
        if existing:
            # Update variables and retrieval metadata
            existing.retrieved_at_utc = item.retrieved_at_utc
            existing.temperature_celsius = item.temperature_celsius
            existing.relative_humidity = item.relative_humidity
            existing.wind_speed_mps = item.wind_speed_mps
            existing.wind_direction_degrees = item.wind_direction_degrees
            existing.precipitation_mm = item.precipitation_mm
            existing.surface_pressure_hpa = item.surface_pressure_hpa
            if item.metrics_payload:
                existing.metrics_payload = {**existing.metrics_payload, **item.metrics_payload}
            self.session.flush()
            return existing

        # Create new ORM record
        obs = EnvironmentalObservation(
            id=item.id or uuid.uuid4(),
            incident_id=item.incident_id,
            location_type=item.location_type.value,
            location_id=item.location_id,
            requested_latitude=item.requested_latitude,
            requested_longitude=item.requested_longitude,
            resolved_latitude=item.resolved_latitude,
            resolved_longitude=item.resolved_longitude,
            typology=item.typology.value,
            provider=item.provider,
            dataset_or_model=item.dataset_or_model,
            valid_time_utc=item.valid_time_utc,
            recorded_at=item.valid_time_utc,
            source=item.source,
            temperature_celsius=item.temperature_celsius,
            relative_humidity=item.relative_humidity,
            wind_speed_mps=item.wind_speed_mps,
            wind_direction_degrees=item.wind_direction_degrees,
            precipitation_mm=item.precipitation_mm,
            surface_pressure_hpa=item.surface_pressure_hpa,
            init_time_utc=item.init_time_utc,
            lead_time_hours=item.lead_time_hours,
            algorithm_name=item.algorithm_name,
            algorithm_version=item.algorithm_version,
            source_fingerprint=item.source_fingerprint,
            retrieved_at_utc=item.retrieved_at_utc,
            metrics_payload=item.metrics_payload or {},
        )
        self.session.add(obs)
        self.session.flush()
        return obs

    def associate_incident(
        self,
        incident_id: UUID,
        observation_id: UUID,
        association_type: str = "spatial_proximity",
        distance_meters: Optional[float] = None,
    ) -> IncidentEnvironmentalObservation:
        """
        Creates an incident association if not already present.
        """
        existing = self.session.execute(
            select(IncidentEnvironmentalObservation).where(
                and_(
                    IncidentEnvironmentalObservation.incident_id == incident_id,
                    IncidentEnvironmentalObservation.observation_id == observation_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            return existing

        assoc = IncidentEnvironmentalObservation(
            incident_id=incident_id,
            observation_id=observation_id,
            association_type=association_type,
            distance_meters=distance_meters,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(assoc)
        self.session.flush()
        return assoc

    def save_batch(
        self,
        items: List[EnvironmentalObservationItem],
        incident_id: Optional[UUID] = None,
        association_type: str = "spatial_proximity",
    ) -> List[EnvironmentalObservation]:
        """
        Batch upserts a list of observation items and links them to an incident if provided.
        """
        persisted: List[EnvironmentalObservation] = []
        for item in items:
            obs = self.upsert_observation(item)
            if incident_id:
                self.associate_incident(
                    incident_id=incident_id,
                    observation_id=obs.id,
                    association_type=association_type,
                )
            persisted.append(obs)
        self.session.commit()
        return persisted

    def query_observations(
        self,
        location_id: Optional[str] = None,
        incident_id: Optional[UUID] = None,
        typology: Optional[str] = None,
        provider: Optional[str] = None,
        start_time_utc: Optional[datetime] = None,
        end_time_utc: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[EnvironmentalObservation]:
        """
        Queries observations with flexible filtering across spatial, incident, temporal, and model axes.
        """
        query = select(EnvironmentalObservation)

        if incident_id:
            # Join via incident association or direct incident_id
            query = query.outerjoin(
                IncidentEnvironmentalObservation,
                IncidentEnvironmentalObservation.observation_id == EnvironmentalObservation.id,
            ).where(
                (EnvironmentalObservation.incident_id == incident_id)
                | (IncidentEnvironmentalObservation.incident_id == incident_id)
            )

        if location_id:
            query = query.where(EnvironmentalObservation.location_id == location_id)
        if typology:
            query = query.where(EnvironmentalObservation.typology == typology)
        if provider:
            query = query.where(EnvironmentalObservation.provider == provider)
        if start_time_utc:
            query = query.where(EnvironmentalObservation.valid_time_utc >= start_time_utc)
        if end_time_utc:
            query = query.where(EnvironmentalObservation.valid_time_utc <= end_time_utc)

        query = query.order_by(desc(EnvironmentalObservation.valid_time_utc)).offset(offset).limit(limit)
        return list(self.session.execute(query).scalars().all())

    def get_latest_for_location(
        self,
        location_id: str,
        typology: Optional[str] = None,
    ) -> Optional[EnvironmentalObservation]:
        """Returns the most recent observation for a location."""
        query = select(EnvironmentalObservation).where(EnvironmentalObservation.location_id == location_id)
        if typology:
            query = query.where(EnvironmentalObservation.typology == typology)
        query = query.order_by(desc(EnvironmentalObservation.valid_time_utc)).limit(1)
        return self.session.execute(query).scalar_one_or_none()
