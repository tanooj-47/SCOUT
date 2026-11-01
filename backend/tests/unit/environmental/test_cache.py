from datetime import datetime, timezone
import time
import pytest

from app.environmental.cache import EnvironmentalCache
from app.environmental.schemas import (
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)


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
    )


class TestEnvironmentalCache:

    def test_cache_key_generation(self):
        key = EnvironmentalCache.generate_cache_key(
            provider="open-meteo",
            dataset_or_model="best_match",
            typology="model_analysis",
            lat=28.61394,
            lon=77.20897,
            time_window="current",
        )
        assert key == "scout:env_cache:open_meteo:best_match:model_analysis:28.6139_77.2090:current:all"

    def test_fresh_hit_and_miss(self, sample_item):
        cache = EnvironmentalCache()
        key = "test_key"
        
        # Miss
        data, is_stale = cache.get(key)
        assert data is None
        assert is_stale is False

        # Set
        cache.set(key, [sample_item], EnvironmentalTypology.MODEL_ANALYSIS, custom_ttl_seconds=60)
        
        # Hit
        data, is_stale = cache.get(key)
        assert data is not None
        assert len(data) == 1
        assert data[0].temperature_celsius == 30.0
        assert is_stale is False
        assert data[0].is_stale is False

    def test_stale_fallback_behavior(self, sample_item):
        cache = EnvironmentalCache()
        key = "stale_key"

        # Set with 0-second TTL (immediately expired)
        cache.set(key, [sample_item], EnvironmentalTypology.MODEL_ANALYSIS, custom_ttl_seconds=-1)

        # get without allow_stale -> None
        data, is_stale = cache.get(key, allow_stale=False)
        assert data is None
        assert is_stale is False

        # get with allow_stale -> returns data marked stale
        data, is_stale = cache.get(key, allow_stale=True)
        assert data is not None
        assert is_stale is True
        assert data[0].is_stale is True

    def test_eviction_when_capacity_exceeded(self, sample_item):
        cache = EnvironmentalCache(max_entries=2)
        cache.set("k1", [sample_item], EnvironmentalTypology.MODEL_ANALYSIS, custom_ttl_seconds=60)
        time.sleep(0.01)
        cache.set("k2", [sample_item], EnvironmentalTypology.MODEL_ANALYSIS, custom_ttl_seconds=60)
        assert cache.size() == 2

        # Adding 3rd should evict k1
        time.sleep(0.01)
        cache.set("k3", [sample_item], EnvironmentalTypology.MODEL_ANALYSIS, custom_ttl_seconds=60)
        assert cache.size() == 2

        data1, _ = cache.get("k1")
        data2, _ = cache.get("k2")
        data3, _ = cache.get("k3")
        assert data1 is None
        assert data2 is not None
        assert data3 is not None
