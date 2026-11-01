import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Compass,
  Flame,
  Filter,
  Layers,
  Hospital,
  Shield,
  Waves,
  Navigation,
  Eye,
  EyeOff,
  Crosshair,
} from "lucide-react";
import { incidentsApi, geospatialApi } from "../../services";
import { MapLibreView, MapMarker } from "../../components/map/MapLibreView";
import { StatusBadge } from "../../components/common/StatusBadge";
import { ThreatBadge } from "../../components/common/ThreatBadge";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";

export const LiveMonitoringPage: React.FC = () => {
  const [mapCenter, setMapCenter] = useState<[number, number]>([-122.4194, 37.7749]);
  const [mapZoom, setMapZoom] = useState<number>(11);
  const [inputLat, setInputLat] = useState("37.7749");
  const [inputLon, setInputLon] = useState("-122.4194");
  const [selectedIncident, setSelectedIncident] = useState<any | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");

  // Geospatial layer toggles
  const [layersState, setLayersState] = useState({
    thermal: true,
    settlements: true,
    hospitals: true,
    fireStations: true,
    waterBodies: true,
    evacuationRoutes: true,
  });

  const { data: incidentsData } = useQuery({
    queryKey: ["monitoring-incidents"],
    queryFn: () => incidentsApi.listIncidents({ limit: 50 }),
    refetchInterval: 20000,
  });

  const { data: nearbyFeatures = [] } = useQuery({
    queryKey: ["monitoring-nearby", mapCenter[1], mapCenter[0]],
    queryFn: () =>
      geospatialApi.getNearbyFeatures({
        latitude: mapCenter[1],
        longitude: mapCenter[0],
        radius_meters: 10000,
      }),
    staleTime: 60000,
  });

  const incidents = incidentsData?.items || [];

  const filteredIncidents = incidents.filter((inc) => {
    if (filterSeverity !== "all" && inc.severity !== filterSeverity) return false;
    return true;
  });

  const markers: MapMarker[] = filteredIncidents.map((inc) => ({
    id: inc.id,
    latitude: inc.location.latitude,
    longitude: inc.location.longitude,
    title: inc.title,
    severity: inc.severity,
    status: inc.status,
    category: inc.disaster_type,
  }));

  const handleCoordinateJump = (e: React.FormEvent) => {
    e.preventDefault();
    const lat = parseFloat(inputLat);
    const lon = parseFloat(inputLon);
    if (!isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      setMapCenter([lon, lat]);
      setMapZoom(13);
    }
  };

  const handleMarkerClick = (marker: MapMarker) => {
    const found = incidents.find((i) => i.id === marker.id);
    if (found) {
      setSelectedIncident(found);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Controller Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 rounded-xl border border-scout-border bg-scout-surface-1 p-4 shadow-scout-card">
        {/* Coordinate Jump Form */}
        <form onSubmit={handleCoordinateJump} className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-scout-text-secondary mr-2">
            <Crosshair className="w-4 h-4 text-scout-cyan" />
            <span>Target Coordinates:</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-mono text-scout-text-muted">LAT:</span>
            <input
              type="number"
              step="0.0001"
              value={inputLat}
              onChange={(e) => setInputLat(e.target.value)}
              className="w-24 rounded bg-scout-surface-2 border border-scout-border px-2 py-1 text-xs font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-mono text-scout-text-muted">LON:</span>
            <input
              type="number"
              step="0.0001"
              value={inputLon}
              onChange={(e) => setInputLon(e.target.value)}
              className="w-24 rounded bg-scout-surface-2 border border-scout-border px-2 py-1 text-xs font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
            />
          </div>
          <Button type="submit" variant="primary" size="sm" icon={Navigation}>
            Jump
          </Button>
        </form>

        {/* Severity Filter & Status Summary */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-scout-text-muted" />
            <span className="text-xs text-scout-text-secondary">Severity:</span>
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="rounded bg-scout-surface-2 border border-scout-border px-2 py-1 text-xs text-scout-text-primary focus:border-scout-cyan focus:outline-none"
            >
              <option value="all">All Tiers ({incidents.length})</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="moderate">Moderate</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="h-4 w-px bg-scout-border hidden sm:block" />

          <div className="flex items-center gap-1.5 text-xs font-mono text-scout-text-muted">
            <Compass className="w-3.5 h-3.5 text-scout-cyan" />
            <span>Datum: EPSG:4326</span>
          </div>
        </div>
      </div>

      {/* Main Monitoring Canvas Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Map View Canvas (3 cols) */}
        <div className="xl:col-span-3 space-y-4">
          <div className="relative rounded-xl border border-scout-border overflow-hidden bg-scout-surface-1 shadow-scout-card">
            <MapLibreView
              center={mapCenter}
              zoom={mapZoom}
              markers={markers}
              onMarkerClick={handleMarkerClick}
              height="650px"
              showLayerControl={true}
            />

            {/* Float Overlay Indicator: Active Observation Count */}
            <div className="absolute top-3 right-12 z-10 hidden sm:flex items-center gap-2 rounded-lg bg-scout-surface-1/90 px-3 py-1.5 text-xs font-mono backdrop-blur-md border border-scout-border shadow-lg">
              <span className="w-2 h-2 rounded-full bg-scout-orange animate-pulse" />
              <span className="text-scout-text-primary font-bold">{filteredIncidents.length}</span>
              <span className="text-scout-text-muted">Hazards in Scope</span>
            </div>
          </div>
        </div>

        {/* Right Sidebar: Layer Controls & Selected Incident Inspector (1 col) */}
        <div className="space-y-4">
          {/* Layer Visibility Matrix */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-scout-cyan" />
                <span>GIS Layer Architecture</span>
              </div>
            }
            subtitle="Persistent PostGIS vector & satellite overlays"
          >
            <div className="space-y-2 text-xs">
              <button
                onClick={() => setLayersState((s) => ({ ...s, thermal: !s.thermal }))}
                className="flex w-full items-center justify-between p-2 rounded bg-scout-surface-2/60 border border-scout-border hover:bg-scout-surface-2 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Flame className="w-4 h-4 text-scout-orange" />
                  <span className={layersState.thermal ? "text-scout-text-primary font-medium" : "text-scout-text-muted line-through"}>
                    Active Hazards (FIRMS/Vision)
                  </span>
                </div>
                {layersState.thermal ? <Eye className="w-3.5 h-3.5 text-scout-cyan" /> : <EyeOff className="w-3.5 h-3.5 text-scout-text-muted" />}
              </button>

              <button
                onClick={() => setLayersState((s) => ({ ...s, hospitals: !s.hospitals }))}
                className="flex w-full items-center justify-between p-2 rounded bg-scout-surface-2/60 border border-scout-border hover:bg-scout-surface-2 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Hospital className="w-4 h-4 text-scout-red" />
                  <span className={layersState.hospitals ? "text-scout-text-primary font-medium" : "text-scout-text-muted line-through"}>
                    Hospitals & Medical Care
                  </span>
                </div>
                {layersState.hospitals ? <Eye className="w-3.5 h-3.5 text-scout-cyan" /> : <EyeOff className="w-3.5 h-3.5 text-scout-text-muted" />}
              </button>

              <button
                onClick={() => setLayersState((s) => ({ ...s, fireStations: !s.fireStations }))}
                className="flex w-full items-center justify-between p-2 rounded bg-scout-surface-2/60 border border-scout-border hover:bg-scout-surface-2 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-scout-yellow" />
                  <span className={layersState.fireStations ? "text-scout-text-primary font-medium" : "text-scout-text-muted line-through"}>
                    Fire Stations & Hydrants
                  </span>
                </div>
                {layersState.fireStations ? <Eye className="w-3.5 h-3.5 text-scout-cyan" /> : <EyeOff className="w-3.5 h-3.5 text-scout-text-muted" />}
              </button>

              <button
                onClick={() => setLayersState((s) => ({ ...s, waterBodies: !s.waterBodies }))}
                className="flex w-full items-center justify-between p-2 rounded bg-scout-surface-2/60 border border-scout-border hover:bg-scout-surface-2 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Waves className="w-4 h-4 text-scout-blue" />
                  <span className={layersState.waterBodies ? "text-scout-text-primary font-medium" : "text-scout-text-muted line-through"}>
                    Hydrology & Natural Barriers
                  </span>
                </div>
                {layersState.waterBodies ? <Eye className="w-3.5 h-3.5 text-scout-cyan" /> : <EyeOff className="w-3.5 h-3.5 text-scout-text-muted" />}
              </button>
            </div>
          </Card>

          {/* Selected Incident Telemetry Inspector */}
          {selectedIncident ? (
            <Card
              title="Incident Inspector"
              subtitle={`ID: ${selectedIncident.id.slice(0, 8)}...`}
              action={
                <button
                  onClick={() => setSelectedIncident(null)}
                  className="text-xs text-scout-text-muted hover:text-scout-text-primary"
                >
                  Clear
                </button>
              }
            >
              <div className="space-y-3 text-xs">
                <div>
                  <h4 className="font-semibold text-scout-text-primary text-sm mb-1">
                    {selectedIncident.title}
                  </h4>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={selectedIncident.status} size="sm" />
                    <ThreatBadge threat={selectedIncident.severity} size="sm" />
                  </div>
                </div>

                <div className="rounded bg-scout-surface-2 p-2.5 font-mono text-[11px] text-scout-text-secondary space-y-1">
                  <div>Lat: {selectedIncident.location.latitude.toFixed(6)}°N</div>
                  <div>Lon: {selectedIncident.location.longitude.toFixed(6)}°E</div>
                  <div>Reported: {new Date(selectedIncident.reported_at).toLocaleTimeString()}</div>
                </div>

                <Button
                  variant="primary"
                  size="sm"
                  className="w-full"
                  onClick={() => (window.location.href = `/incidents?id=${selectedIncident.id}`)}
                >
                  Inspect Multimodal Evidence
                </Button>
              </div>
            </Card>
          ) : (
            /* Nearby Spatial Feature Catalog preview */
            <Card
              title="Spatial Adjacency Catalog"
              subtitle={`Within 10km radius (${nearbyFeatures.length} found)`}
            >
              {nearbyFeatures.length === 0 ? (
                <div className="text-center py-6 text-xs text-scout-text-muted">
                  No registered infrastructure within search radius.
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto">
                  {nearbyFeatures.slice(0, 6).map((feat) => (
                    <div
                      key={feat.id}
                      className="p-2 rounded bg-scout-surface-2/60 border border-scout-border text-xs flex justify-between items-center"
                    >
                      <div>
                        <span className="font-medium text-scout-text-primary block">
                          {feat.name}
                        </span>
                        <span className="text-[10px] uppercase font-mono text-scout-text-muted">
                          {feat.category} • {feat.relationship}
                        </span>
                      </div>
                      <span className="font-mono text-[11px] font-bold text-scout-cyan">
                        {(feat.distance_meters / 1000).toFixed(1)} km
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
