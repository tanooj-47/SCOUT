import React, { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Layers, Eye, EyeOff } from "lucide-react";

export interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  title: string;
  category?: string;
  severity?: string;
  status?: string;
  threatLevel?: string;
}

export interface MapLayerConfig {
  id: string;
  name: string;
  color: string;
  visible: boolean;
  count?: number;
}

interface MapLibreViewProps {
  center?: [number, number]; // [lon, lat]
  zoom?: number;
  markers?: MapMarker[];
  onMarkerClick?: (marker: MapMarker) => void;
  className?: string;
  height?: string;
  showLayerControl?: boolean;
}

export const MapLibreView: React.FC<MapLibreViewProps> = ({
  center = [-122.4194, 37.7749], // SF default
  zoom = 11,
  markers = [],
  onMarkerClick,
  className = "",
  height = "450px",
  showLayerControl = true,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerInstancesRef = useRef<maplibregl.Marker[]>([]);
  const [layersOpen, setLayersOpen] = useState(false);

  const [activeLayers, setActiveLayers] = useState<MapLayerConfig[]>([
    { id: "incidents", name: "Active Hazards & Incidents", color: "#FF781F", visible: true, count: markers.length },
    { id: "settlements", name: "Settlements & Population", color: "#28BCEB", visible: true },
    { id: "infrastructure", name: "Hospitals & Fire Stations", color: "#EF4444", visible: true },
    { id: "hydrology", name: "Rivers & Water Bodies", color: "#278BC4", visible: true },
    { id: "roads", name: "Evacuation Corridors", color: "#FBBF24", visible: true },
  ]);

  const toggleLayer = (layerId: string) => {
    setActiveLayers((prev) =>
      prev.map((l) => (l.id === layerId ? { ...l, visible: !l.visible } : l))
    );
  };

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    // Dark cartographic basemap style (Carto Dark Matter standard raster/vector)
    const mapStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        "carto-dark": {
          type: "raster",
          tiles: [
            "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            "https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
          ],
          tileSize: 256,
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        },
      },
      layers: [
        {
          id: "carto-dark-layer",
          type: "raster",
          source: "carto-dark",
          minzoom: 0,
          maxzoom: 19,
        },
      ],
    };

    try {
      const map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: mapStyle,
        center: center,
        zoom: zoom,
        attributionControl: false,
      });

      map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

      mapRef.current = map;
    } catch (err) {
      console.warn("MapLibre GL initialization error (WebGL support required):", err);
    }

    return () => {
      markerInstancesRef.current.forEach((m) => m.remove());
      markerInstancesRef.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // Update center & zoom
  useEffect(() => {
    if (mapRef.current && center) {
      mapRef.current.easeTo({ center, zoom });
    }
  }, [center[0], center[1], zoom]);

  // Update Markers
  useEffect(() => {
    const currentMap = mapRef.current;
    if (!currentMap) return;

    // Clear previous markers
    markerInstancesRef.current.forEach((m) => m.remove());
    markerInstancesRef.current = [];

    const isIncidentsVisible = activeLayers.find((l) => l.id === "incidents")?.visible ?? true;

    if (!isIncidentsVisible) return;

    markers.forEach((m) => {
      // Create custom marker DOM element
      const el = document.createElement("div");
      el.className = "scout-map-marker group relative cursor-pointer";

      const isCritical = m.severity === "critical" || m.threatLevel === "CRITICAL";
      const markerColor = isCritical ? "#EF4444" : "#FF781F";

      el.innerHTML = `
        <div class="relative flex items-center justify-center">
          <span class="absolute w-6 h-6 rounded-full animate-ping opacity-75" style="background-color: ${markerColor}"></span>
          <div class="relative w-4 h-4 rounded-full border-2 border-white shadow-lg flex items-center justify-center" style="background-color: ${markerColor}">
            <div class="w-1.5 h-1.5 bg-white rounded-full"></div>
          </div>
        </div>
      `;

      const popup = new maplibregl.Popup({ offset: 25, closeButton: false }).setHTML(`
        <div class="p-1 text-xs">
          <div class="font-bold text-scout-text-primary uppercase tracking-wider mb-1">${m.title}</div>
          <div class="text-[11px] text-scout-text-muted font-mono">
            Lat: ${m.latitude.toFixed(4)}, Lon: ${m.longitude.toFixed(4)}
          </div>
          ${m.status ? `<div class="mt-1 text-[10px] uppercase font-mono text-scout-cyan">Status: ${m.status}</div>` : ""}
          ${m.threatLevel ? `<div class="text-[10px] uppercase font-mono text-scout-orange">Threat: ${m.threatLevel}</div>` : ""}
        </div>
      `);

      el.addEventListener("click", () => {
        if (onMarkerClick) {
          onMarkerClick(m);
        }
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([m.longitude, m.latitude])
        .setPopup(popup)
        .addTo(currentMap);

      markerInstancesRef.current.push(marker);
    });
  }, [markers, activeLayers, onMarkerClick]);

  return (
    <div className={`relative w-full overflow-hidden rounded-lg border border-scout-border bg-scout-surface-1 ${className}`}>
      {/* Map Canvas */}
      <div ref={mapContainerRef} style={{ height }} className="w-full bg-[#061321]" />

      {/* Layer Control Pill */}
      {showLayerControl && (
        <div className="absolute top-3 left-3 z-10">
          <button
            onClick={() => setLayersOpen(!layersOpen)}
            className="flex items-center gap-2 rounded-md bg-scout-surface-1/90 px-3 py-2 text-xs font-semibold text-scout-text-primary shadow-lg backdrop-blur-md border border-scout-border hover:bg-scout-surface-2 transition-colors"
          >
            <Layers className="w-4 h-4 text-scout-cyan" />
            <span>Map Layers</span>
            <span className="ml-1 rounded-full bg-scout-cyan/20 px-1.5 py-0.2 text-[10px] text-scout-cyan font-mono">
              {activeLayers.filter((l) => l.visible).length}/{activeLayers.length}
            </span>
          </button>

          {/* Layer Control Dropdown Panel */}
          {layersOpen && (
            <div className="mt-2 w-64 rounded-lg bg-scout-surface-1/95 p-3 shadow-2xl backdrop-blur-md border border-scout-border animate-in fade-in duration-100">
              <div className="flex items-center justify-between border-b border-scout-border pb-2 mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-scout-text-secondary">
                  Spatial Overlays
                </span>
                <span className="text-[10px] text-scout-text-muted font-mono">WGS 84</span>
              </div>
              <div className="space-y-1.5">
                {activeLayers.map((layer) => (
                  <button
                    key={layer.id}
                    onClick={() => toggleLayer(layer.id)}
                    className="flex w-full items-center justify-between rounded px-2 py-1.5 text-xs text-left hover:bg-scout-surface-2 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: layer.color }}
                      />
                      <span
                        className={
                          layer.visible
                            ? "text-scout-text-primary font-medium"
                            : "text-scout-text-muted line-through"
                        }
                      >
                        {layer.name}
                      </span>
                    </div>
                    {layer.visible ? (
                      <Eye className="w-3.5 h-3.5 text-scout-cyan" />
                    ) : (
                      <EyeOff className="w-3.5 h-3.5 text-scout-text-muted" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Coordinate & Reference Indicator */}
      <div className="absolute bottom-2 left-3 z-10 hidden sm:flex items-center gap-2 rounded bg-scout-surface-1/80 px-2.5 py-1 text-[10px] font-mono text-scout-text-muted backdrop-blur border border-scout-border">
        <span>EPSG:4326</span>
        <span>•</span>
        <span>Center: {center[1].toFixed(4)}°N, {center[0].toFixed(4)}°E</span>
      </div>
    </div>
  );
};
