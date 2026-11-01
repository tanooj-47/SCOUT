"""
backend/app/environmental/providers/__init__.py
External environmental data provider clients.
"""

from app.environmental.providers.base import BaseWeatherProvider
from app.environmental.providers.open_meteo import OpenMeteoProvider
from app.environmental.providers.nasa_power import NasaPowerProvider

__all__ = [
    "BaseWeatherProvider",
    "OpenMeteoProvider",
    "NasaPowerProvider",
]
