"""
backend/app/intelligence/context.py
Aggregates and transforms raw geospatial search results into structured ContextSummary.
"""

from typing import Any, Dict, List, Optional
from app.geospatial.schemas import FeatureCategory, GeographicFeatureItem
from app.intelligence.schemas import ContextSummary


class ContextAggregator:
    """
    Transforms geographic feature search outputs into a standardized ContextSummary schema.
    Extracts category tallies, proximity milestones, and documented coverage limitations.
    """

    @staticmethod
    def aggregate(
        features: List[GeographicFeatureItem],
        missing_layers: Optional[List[str]] = None,
        data_provider: str = "local_vector_catalog",
    ) -> ContextSummary:
        """
        Synthesizes list of GeographicFeatureItems into ContextSummary.
        """
        settlements: List[GeographicFeatureItem] = []
        hospitals: List[GeographicFeatureItem] = []
        fire_stations: List[GeographicFeatureItem] = []
        roads: List[GeographicFeatureItem] = []
        water_bodies: List[GeographicFeatureItem] = []

        for feat in features:
            cat = feat.category
            if cat == FeatureCategory.SETTLEMENT:
                settlements.append(feat)
            elif cat == FeatureCategory.INFRASTRUCTURE:
                name_lower = feat.name.lower()
                meta = feat.metadata or {}
                amenity = str(meta.get("amenity", "")).lower()
                healthcare = str(meta.get("healthcare", "")).lower()

                if (
                    amenity in ("hospital", "clinic")
                    or healthcare in ("hospital", "clinic")
                    or any(w in name_lower for w in ["hospital", "clinic", "medical center", "healthcare"])
                ):
                    hospitals.append(feat)
                elif (
                    amenity == "fire_station"
                    or any(w in name_lower for w in ["fire station", "fire brigade", "fire post", "fire rescue"])
                ):
                    fire_stations.append(feat)
                else:
                    # Generic infrastructure
                    pass
            elif cat == FeatureCategory.ROAD:
                roads.append(feat)
            elif cat == FeatureCategory.WATER_BODY:
                water_bodies.append(feat)

        # Sort by distance
        settlements.sort(key=lambda f: f.distance_meters)
        hospitals.sort(key=lambda f: f.distance_meters)
        fire_stations.sort(key=lambda f: f.distance_meters)

        closest_settlement = settlements[0] if settlements else None
        closest_hospital = hospitals[0] if hospitals else None
        closest_fire_station = fire_stations[0] if fire_stations else None

        coverage_notes = []
        if len(features) == 0:
            if data_provider == "postgis_spatial_db":
                coverage_notes.append(
                    "Persistent PostGIS database holds 0 geographic features in this search perimeter. An absence of nearby features in the spatial store reflects local data density or remote coordinates, NOT verified absence of human settlements or critical infrastructure."
                )
            else:
                coverage_notes.append(
                    "Local spatial catalog holds 0 operational features in this search perimeter. An absence of nearby features reflects spatial data density limitations, NOT verified absence of human settlements or critical infrastructure."
                )

        if data_provider == "postgis_spatial_db":
            coverage_notes.append("Persistent PostGIS database queried.")
        else:
            coverage_notes.append("In-memory or local GeoJSON spatial catalog queried.")

        if fire_stations:
            coverage_notes.append(
                f"Identified {len(fire_stations)} fire station(s); national OSM coverage is known to be incomplete."
            )
        else:
            coverage_notes.append("No fire stations detected within search radius (OSM layer has partial coverage).")

        if missing_layers:
            for lyr in missing_layers:
                coverage_notes.append(f"Notice: Layer '{lyr}' is unavailable in the spatial store.")

        return ContextSummary(
            settlements_found=len(settlements),
            closest_settlement_distance_meters=closest_settlement.distance_meters if closest_settlement else None,
            closest_settlement_name=closest_settlement.name if closest_settlement else None,
            hospitals_found=len(hospitals),
            closest_hospital_distance_meters=closest_hospital.distance_meters if closest_hospital else None,
            fire_stations_found=len(fire_stations),
            closest_fire_station_distance_meters=closest_fire_station.distance_meters if closest_fire_station else None,
            road_corridors_found=len(roads),
            water_bodies_found=len(water_bodies),
            total_features_evaluated=len(features),
            spatial_coverage_notes=coverage_notes,
        )
