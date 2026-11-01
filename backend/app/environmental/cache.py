from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.environmental.schemas import EnvironmentalObservationItem, EnvironmentalTypology


@dataclass
class CacheEntry:
    data: List[EnvironmentalObservationItem]
    created_at_utc: datetime
    expires_at_utc: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at_utc


class EnvironmentalCache:
    """
    Thread-safe in-memory cache supporting distinct TTLs per observation typology
    and stale-on-error fallback when upstream external providers fail.
    """

    def __init__(self, max_entries: int = 1000):
        self._store: Dict[str, CacheEntry] = {}
        self._lock = RLock()
        self._max_entries = max_entries

    @staticmethod
    def generate_cache_key(
        provider: str,
        dataset_or_model: str,
        typology: str,
        lat: float,
        lon: float,
        time_window: str = "current",
        var_hash: str = "all",
    ) -> str:
        """
        Builds canonical compound cache key:
        scout:env_cache:{provider}:{model}:{typology}:{lat_4dp}_{lon_4dp}:{time_window}:{var_hash}
        """
        clean_provider = provider.lower().replace("-", "_").strip()
        clean_model = dataset_or_model.lower().replace("-", "_").strip()
        clean_typology = typology.lower().strip()
        location_key = f"{lat:.4f}_{lon:.4f}"
        return f"scout:env_cache:{clean_provider}:{clean_model}:{clean_typology}:{location_key}:{time_window}:{var_hash}"

    def get_ttl_for_typology(self, typology: EnvironmentalTypology) -> int:
        """Determines TTL in seconds based on configuration settings."""
        if typology == EnvironmentalTypology.MODEL_ANALYSIS:
            return settings.ENVIRONMENTAL_CURRENT_CACHE_TTL_SECONDS
        elif typology == EnvironmentalTypology.FORECAST:
            return settings.ENVIRONMENTAL_FORECAST_CACHE_TTL_SECONDS
        elif typology == EnvironmentalTypology.REANALYSIS or typology == EnvironmentalTypology.STATION_OBSERVED:
            return settings.ENVIRONMENTAL_HISTORICAL_CACHE_TTL_SECONDS
        return 1800

    def get(
        self,
        key: str,
        allow_stale: bool = False,
    ) -> Tuple[Optional[List[EnvironmentalObservationItem]], bool]:
        """
        Retrieves items from cache.
        Returns: (items, is_stale)
        If fresh: returns (items, False)
        If expired but allow_stale=True: returns (items, True)
        If missing or (expired and not allow_stale): returns (None, False)
        """
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None, False

            if not entry.is_expired:
                # Fresh entry
                return [item.model_copy(update={"is_stale": False}) for item in entry.data], False

            if allow_stale:
                # Stale fallback allowed
                return [item.model_copy(update={"is_stale": True}) for item in entry.data], True

            return None, False

    def set(
        self,
        key: str,
        data: List[EnvironmentalObservationItem],
        typology: EnvironmentalTypology,
        custom_ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Stores items in cache with appropriate TTL.
        Evicts oldest entries if capacity is reached.
        """
        ttl_seconds = custom_ttl_seconds or self.get_ttl_for_typology(typology)
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

        with self._lock:
            if len(self._store) >= self._max_entries:
                # Evict oldest entry by created_at_utc
                oldest_key = min(self._store.keys(), key=lambda k: self._store[k].created_at_utc)
                self._store.pop(oldest_key, None)

            self._store[key] = CacheEntry(
                data=data,
                created_at_utc=now,
                expires_at_utc=expires_at,
            )

    def clear(self) -> None:
        """Clears all stored entries."""
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Returns the number of cached keys."""
        with self._lock:
            return len(self._store)


# Global singleton instance for the service lifecycle
environmental_cache = EnvironmentalCache()
