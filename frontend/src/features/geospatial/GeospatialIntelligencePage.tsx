import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  MapPin,
  CheckCircle2,
  XCircle,
  Building,
  Navigation,
  Compass,
} from "lucide-react";
import { geospatialApi } from "../../services";
import { Card } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { LoadingSpinner } from "../../components/common/LoadingSpinner";
import { MapLibreView, MapMarker } from "../../components/map/MapLibreView";
import { CoordinateValidationResponse } from "../../types";

export const GeospatialIntelligencePage: React.FC = () => {
  const [lat, setLat] = useState("37.7749");
  const [lon, setLon] = useState("-122.4194");
  const [radius, setRadius] = useState("5000");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [activeQuery, setActiveQuery] = useState<{ lat: number; lon: number; radius: number }>({
    lat: 37.7749,
    lon: -122.4194,
    radius: 5000,
  });

  // Coordinate Validation Mutation
  const validationMutation = useMutation({
    mutationFn: (coords: { latitude: number; longitude: number }) =>
      geospatialApi.validateCoordinate(coords),
  });

  // Query Nearby Persistent Features
  const { data: features = [], isLoading: featuresLoading, refetch } = useQuery({
    queryKey: ["geospatial-nearby", activeQuery.lat, activeQuery.lon, activeQuery.radius],
    queryFn: () =>
      geospatialApi.getNearbyFeatures({
        latitude: activeQuery.lat,
        longitude: activeQuery.lon,
        radius_meters: activeQuery.radius,
        limit: 100,
      }),
  });

  const handleValidate = () => {
    const parsedLat = parseFloat(lat);
    const parsedLon = parseFloat(lon);
    if (!isNaN(parsedLat) && !isNaN(parsedLon)) {
      validationMutation.mutate({ latitude: parsedLat, longitude: parsedLon });
    }
  };

  const handleRunAnalysis = (e: React.FormEvent) => {
    e.preventDefault();
    const parsedLat = parseFloat(lat);
    const parsedLon = parseFloat(lon);
    const parsedRad = parseFloat(radius);
    if (!isNaN(parsedLat) && !isNaN(parsedLon) && !isNaN(parsedRad)) {
      setActiveQuery({ lat: parsedLat, lon: parsedLon, radius: parsedRad });
      handleValidate();
      refetch();
    }
  };

  const validationResult: CoordinateValidationResponse | undefined = validationMutation.data;

  const filteredFeatures = features.filter((f) => {
    if (categoryFilter !== "all" && f.category.toLowerCase() !== categoryFilter.toLowerCase()) {
      return false;
    }
    return true;
  });

  // Map markers for nearby features
  const markers: MapMarker[] = [
    {
      id: "target-incident",
      latitude: activeQuery.lat,
      longitude: activeQuery.lon,
      title: "Query Epicenter",
      severity: "critical",
      status: "active",
    },
    ...filteredFeatures.slice(0, 30).map((f) => ({
      id: f.id,
      latitude: f.latitude ?? activeQuery.lat + (Math.sin(f.distance_meters) * 0.01),
      longitude: f.longitude ?? activeQuery.lon + (Math.cos(f.distance_meters) * 0.01),
      title: f.name,
      category: f.category,
      threatLevel: f.relationship.toUpperCase(),
    })),
  ];

  const closestFeature = features.length > 0 ? features[0] : null;

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="rounded-xl border border-scout-border bg-scout-surface-1 p-5 shadow-scout-card">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-scout-cyan/15 border border-scout-cyan/30 text-scout-cyan">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-scout-text-primary">
                Geospatial Intelligence & Spatial Exposure Engine
              </h1>
              <p className="text-xs text-scout-text-muted">
                PostGIS persistent spatial catalog queries, geodesic distance calculation, and topological adjacency analysis
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 font-mono text-xs text-scout-cyan">
            <Compass className="w-4 h-4" />
            <span>Datum: EPSG:4326 (WGS 84)</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Controls + Exposure Summary + Map */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Input Form & Validation Card (1 col) */}
        <div className="space-y-6">
          <Card
            title="Incident Coordinates & Radius"
            subtitle="Configure WGS 84 search geometry"
          >
            <form onSubmit={handleRunAnalysis} className="space-y-4 text-xs">
              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">
                  Latitude (WGS 84, °N)
                </label>
                <input
                  type="number"
                  step="0.000001"
                  min="-90"
                  max="90"
                  required
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                />
                <span className="text-[10px] text-scout-text-muted font-mono mt-0.5 block">
                  Valid Range: [-90.0, 90.0]
                </span>
              </div>

              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">
                  Longitude (WGS 84, °E)
                </label>
                <input
                  type="number"
                  step="0.000001"
                  min="-180"
                  max="180"
                  required
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                />
                <span className="text-[10px] text-scout-text-muted font-mono mt-0.5 block">
                  Valid Range: [-180.0, 180.0]
                </span>
              </div>

              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">
                  Search Radius (Meters)
                </label>
                <input
                  type="number"
                  step="100"
                  min="100"
                  max="100000"
                  required
                  value={radius}
                  onChange={(e) => setRadius(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                />
                <span className="text-[10px] text-scout-text-muted font-mono mt-0.5 block">
                  Range: 100m to 100,000m (100km)
                </span>
              </div>

              <div className="flex gap-2 pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="w-1/2"
                  onClick={handleValidate}
                  isLoading={validationMutation.isPending}
                >
                  Validate Only
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  className="w-1/2"
                  icon={Navigation}
                  isLoading={featuresLoading}
                >
                  Run Query
                </Button>
              </div>
            </form>
          </Card>

          {/* Validation Result Box */}
          {validationResult && (
            <Card
              title={
                <div className="flex items-center gap-2">
                  {validationResult.is_valid ? (
                    <CheckCircle2 className="w-4 h-4 text-scout-green" />
                  ) : (
                    <XCircle className="w-4 h-4 text-scout-red" />
                  )}
                  <span>Coordinate Validation</span>
                </div>
              }
              subtitle="CRS & Proximity Projection Status"
            >
              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between p-2 rounded bg-scout-surface-2">
                  <span className="text-scout-text-muted">Coordinate Status:</span>
                  <span
                    className={`font-bold ${
                      validationResult.is_valid ? "text-scout-green" : "text-scout-red"
                    }`}
                  >
                    {validationResult.is_valid ? "VALID WGS 84" : "INVALID BOUNDS"}
                  </span>
                </div>
                <div className="flex justify-between p-2 rounded bg-scout-surface-2">
                  <span className="text-scout-text-muted">Native SRID:</span>
                  <span className="text-scout-text-primary">EPSG:{validationResult.srid}</span>
                </div>
                {validationResult.utm_epsg && (
                  <div className="flex justify-between p-2 rounded bg-scout-surface-2">
                    <span className="text-scout-text-muted">Resolved UTM Zone:</span>
                    <span className="text-scout-cyan font-bold">
                      EPSG:{validationResult.utm_epsg}
                    </span>
                  </div>
                )}
                {validationResult.error_message && (
                  <p className="text-scout-red text-[11px] p-2 rounded bg-scout-red/10 border border-scout-red/20">
                    {validationResult.error_message}
                  </p>
                )}
              </div>
            </Card>
          )}

          {/* Geographic Exposure Summary Cards */}
          <Card title="Geographic Exposure Metrics" subtitle="Landscape proximity quantification">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-scout-surface-2 border border-scout-border">
                <span className="text-scout-text-muted block text-[10px] uppercase font-mono">Features Found</span>
                <span className="text-xl font-bold font-mono text-scout-cyan">{features.length}</span>
              </div>
              <div className="p-3 rounded-lg bg-scout-surface-2 border border-scout-border">
                <span className="text-scout-text-muted block text-[10px] uppercase font-mono">Closest Distance</span>
                <span className="text-xl font-bold font-mono text-scout-orange">
                  {closestFeature ? `${(closestFeature.distance_meters / 1000).toFixed(2)} km` : "N/A"}
                </span>
              </div>
            </div>

            {closestFeature && (
              <div className="mt-3 p-2.5 rounded bg-scout-surface-2/60 border border-scout-border text-xs">
                <span className="text-[10px] text-scout-text-muted uppercase font-mono block">Closest Asset</span>
                <span className="font-semibold text-scout-text-primary block mt-0.5">{closestFeature.name}</span>
                <span className="text-[11px] text-scout-text-muted capitalize">
                  {closestFeature.category} • {closestFeature.source_dataset}
                </span>
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Spatial Map & Feature Results Table (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Spatial Canvas */}
          <Card
            title="Spatial Geometry Canvas"
            subtitle={`Centroid: ${activeQuery.lat}°N, ${activeQuery.lon}°E (Radius: ${activeQuery.radius}m)`}
            bodyClassName="p-0"
          >
            <MapLibreView
              center={[activeQuery.lon, activeQuery.lat]}
              zoom={12}
              markers={markers}
              height="380px"
              showLayerControl={true}
            />
          </Card>

          {/* Persistent Spatial Features Table */}
          <Card
            title="Surrounding Landscape Features"
            subtitle="Queried directly from PostGIS spatial feature catalog"
            action={
              <div className="flex items-center gap-2">
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="rounded bg-scout-surface-2 border border-scout-border px-2.5 py-1 text-xs text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                >
                  <option value="all">All Categories ({features.length})</option>
                  <option value="settlement">Settlements</option>
                  <option value="infrastructure">Infrastructure</option>
                  <option value="road">Roads / Evacuation</option>
                  <option value="water_body">Water Bodies</option>
                  <option value="vegetation">Vegetation / Fuel</option>
                </select>
              </div>
            }
          >
            {featuresLoading ? (
              <LoadingSpinner size="sm" label="Executing spatial query..." />
            ) : filteredFeatures.length === 0 ? (
              <div className="py-8 text-center text-xs text-scout-text-muted">
                No features found within the specified search radius.
              </div>
            ) : (
              <div className="max-h-80 overflow-y-auto divide-y divide-scout-border/60">
                {filteredFeatures.map((feat) => (
                  <div
                    key={feat.id}
                    className="flex items-center justify-between py-2.5 px-2 hover:bg-scout-surface-2/40 transition-colors text-xs"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-scout-surface-2 text-scout-cyan">
                        <Building className="w-4 h-4" />
                      </div>
                      <div>
                        <span className="font-semibold text-scout-text-primary block">
                          {feat.name}
                        </span>
                        <span className="text-[10px] font-mono uppercase text-scout-text-muted">
                          {feat.category} • {feat.relationship} • {feat.source_dataset}
                        </span>
                      </div>
                    </div>
                    <div className="text-right font-mono">
                      <span className="font-bold text-scout-cyan text-sm block">
                        {(feat.distance_meters / 1000).toFixed(2)} km
                      </span>
                      <span className="text-[10px] text-scout-text-muted">
                        {feat.distance_meters.toFixed(0)} meters
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
