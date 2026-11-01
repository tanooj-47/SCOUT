from datetime import datetime, timezone
from unittest.mock import MagicMock, call
import uuid
import pytest

from app.environmental.repository import EnvironmentalRepository
from app.environmental.schemas import (
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)
from app.models.environmental_observation import (
    EnvironmentalObservation,
    IncidentEnvironmentalObservation,
)


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def sample_item():
    return EnvironmentalObservationItem(
        location_type=LocationType.GRID,
        location_id="grid:open_meteo:best_match:28.6250_77.2500",
        requested_latitude=28.6139,
        requested_longitude=77.2090,
        resolved_latitude=28.6250,
        resolved_longitude=77.2500,
        typology=EnvironmentalTypology.MODEL_ANALYSIS,
        valid_time_utc=datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc),
        recorded_at=datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc),
        source="open-meteo",
        provider="open-meteo",
        dataset_or_model="best_match",
        temperature_celsius=30.0,
        relative_humidity=50.0,
        wind_speed_mps=4.0,
        precipitation_mm=0.0,
        surface_pressure_hpa=1010.0,
    )


class TestEnvironmentalRepository:

    def test_get_by_id(self, mock_session):
        repo = EnvironmentalRepository(mock_session)
        obs_id = uuid.uuid4()
        fake_obs = EnvironmentalObservation(id=obs_id)
        mock_session.get.return_value = fake_obs

        result = repo.get_by_id(obs_id)
        assert result == fake_obs
        mock_session.get.assert_called_once_with(EnvironmentalObservation, obs_id)

    def test_upsert_observation_creates_new_when_not_existing(self, mock_session, sample_item):
        repo = EnvironmentalRepository(mock_session)
        # Mock scalar_one_or_none to return None (no existing record)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        obs = repo.upsert_observation(sample_item)

        assert mock_session.add.called
        assert mock_session.flush.called
        assert obs.location_id == sample_item.location_id
        assert obs.temperature_celsius == sample_item.temperature_celsius
        assert obs.typology == sample_item.typology.value

    def test_upsert_observation_updates_existing_when_found(self, mock_session, sample_item):
        repo = EnvironmentalRepository(mock_session)
        existing_obs = EnvironmentalObservation(
            id=uuid.uuid4(),
            location_type="grid",
            location_id=sample_item.location_id,
            provider="open-meteo",
            dataset_or_model="best_match",
            typology="model_analysis",
            valid_time_utc=sample_item.valid_time_utc,
            recorded_at=sample_item.valid_time_utc,
            source="open-meteo",
            temperature_celsius=25.0,
            metrics_payload={"previous": "data"},
        )
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing_obs

        obs = repo.upsert_observation(sample_item)

        # Should update existing record and not call add()
        assert not mock_session.add.called
        assert mock_session.flush.called
        assert obs == existing_obs
        assert obs.temperature_celsius == 30.0  # Updated from sample_item

    def test_associate_incident_creates_association_when_absent(self, mock_session):
        repo = EnvironmentalRepository(mock_session)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        inc_id = uuid.uuid4()
        obs_id = uuid.uuid4()
        assoc = repo.associate_incident(incident_id=inc_id, observation_id=obs_id, distance_meters=150.0)

        assert mock_session.add.called
        assert mock_session.flush.called
        assert assoc.incident_id == inc_id
        assert assoc.observation_id == obs_id
        assert assoc.distance_meters == 150.0

    def test_save_batch_persists_and_commits(self, mock_session, sample_item):
        repo = EnvironmentalRepository(mock_session)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        inc_id = uuid.uuid4()
        results = repo.save_batch([sample_item], incident_id=inc_id)

        assert len(results) == 1
        assert mock_session.commit.called

    def test_query_observations(self, mock_session):
        repo = EnvironmentalRepository(mock_session)
        mock_obs = [EnvironmentalObservation(id=uuid.uuid4()), EnvironmentalObservation(id=uuid.uuid4())]
        mock_session.execute.return_value.scalars.return_value.all.return_value = mock_obs

        res = repo.query_observations(location_id="test_loc", typology="model_analysis", limit=10)
        assert len(res) == 2
        assert mock_session.execute.called

    def test_get_latest_for_location(self, mock_session):
        repo = EnvironmentalRepository(mock_session)
        latest = EnvironmentalObservation(id=uuid.uuid4())
        mock_session.execute.return_value.scalar_one_or_none.return_value = latest

        res = repo.get_latest_for_location("grid:loc")
        assert res == latest
