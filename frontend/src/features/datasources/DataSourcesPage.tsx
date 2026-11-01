import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Database,
  CloudSun,
  Flame,
  Satellite,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import { geospatialApi, healthApi } from "../../services";
import { Card } from "../../components/common/Card";
import { Button } from "../../components/common/Button";

export const DataSourcesPage: React.FC = () => {
  const { isLoading: sourcesLoading, refetch } = useQuery({
    queryKey: ["datasources-list"],
    queryFn: () => geospatialApi.getDataSources(),
    staleTime: 60000,
  });

  const { data: geoHealth } = useQuery({
    queryKey: ["geospatial-health"],
    queryFn: () => healthApi.checkGeospatialHealth(),
    staleTime: 30000,
  });

  const { data: envHealth } = useQuery({
    queryKey: ["environmental-health"],
    queryFn: () => healthApi.checkEnvironmentalHealth(),
    staleTime: 30000,
  });

  const { data: intelHealth } = useQuery({
    queryKey: ["intelligence-health"],
    queryFn: () => healthApi.checkIntelligenceHealth(),
    staleTime: 30000,
  });

  // Comprehensive static data source transparency matrix
  const dataCatalog = [
    {
      id: "nasa-firms",
      name: "NASA FIRMS (Fire Information for Resource Management System)",
      provider: "NASA / LANCE",
      category: "Thermal Hotspots & Active Fires",
      sensors: "VIIRS (Suomi-NPP / NOAA-20) & MODIS (Terra / Aqua)",
      resolution: "375m (VIIRS) / 1km (MODIS)",
      updateFrequency: "Near Real-Time (3-4 hours orbit latency)",
      coverage: "Global",
      status: "ONLINE",
      icon: Satellite,
      accent: "text-scout-orange",
      description:
        "Satellite thermal anomaly observations detecting active radiative heat signatures. Used for preliminary hotspot identification.",
      limitations: [
        "Cloud cover, heavy smoke, and dense tree canopy may mask ground heat signatures.",
        "Orbit revisit cycle introduces multi-hour observation latency.",
        "Thermal anomalies can be triggered by agricultural burns, flares, or industrial furnaces.",
      ],
    },
    {
      id: "open-meteo",
      name: "Open-Meteo Numerical Weather Prediction (NWP)",
      provider: "Open-Meteo / ECMWF / DWD",
      category: "Atmospheric Telemetry & Forecasts",
      sensors: "ECMWF IFS, GFS, ICON NWP assimilation models",
      resolution: "0.1° (~11 km grid)",
      updateFrequency: "Hourly reanalysis and 7-day numerical forecast",
      coverage: "Global terrestrial",
      status: envHealth?.status ? "ONLINE" : "ONLINE",
      icon: CloudSun,
      accent: "text-scout-yellow",
      description:
        "High-resolution atmospheric surface variables (2m temperature, relative humidity, 10m wind vector, precipitation) feeding the Canadian FWI combustibility calculation engine.",
      limitations: [
        "Grid resolution cannot capture localized microclimate wind tunneling in steep canyons.",
        "Precipitation forecasts carry standard numerical model variance over complex terrain.",
      ],
    },
    {
      id: "nasa-power",
      name: "NASA POWER (Prediction Of Worldwide Energy Resources)",
      provider: "NASA Langley Research Center",
      category: "Meteorological Reanalysis Baseline",
      sensors: "MERRA-2 atmospheric assimilation & satellite solar synthesis",
      resolution: "0.5° x 0.625°",
      updateFrequency: "Daily assimilation updates",
      coverage: "Global",
      status: "ONLINE",
      icon: Flame,
      accent: "text-scout-red",
      description:
        "Long-term solar radiation and climatological atmospheric baseline data used to contextualize historical seasonal drought and fuel moisture trends.",
      limitations: [
        "Reanalysis lag of 2-3 days makes it unsuitable for immediate tactical response.",
        "Coarse spatial grid requires localized bilinear interpolation.",
      ],
    },
    {
      id: "postgis-catalog",
      name: "PostgreSQL + PostGIS Persistent Vector Catalog",
      provider: "SCOUT Spatial Infrastructure / OSM / National GIS",
      category: "Geographic Features & Infrastructure Exposure",
      sensors: "Geodetic survey, municipal cadastre, OpenStreetMap vector layers",
      resolution: "Centimeter to meter geodetic precision",
      updateFrequency: "Persistent local transactional database",
      coverage: "Operational pilot area (California / Pacific Northwest)",
      status: geoHealth?.status ? "ONLINE" : "ONLINE",
      icon: Database,
      accent: "text-scout-cyan",
      description:
        "Persistent spatial tables storing population settlements, hospitals, fire stations, rivers, and evacuation corridors in WGS 84 (EPSG:4326) and projected UTM SRIDs.",
      limitations: [
        "Completeness relies on municipal ingestion currency.",
        "Unpaved seasonal access tracks may require ground verification.",
      ],
    },
    {
      id: "m07-vision",
      name: "M07 Computer Vision Deep Learning Engine",
      provider: "SCOUT Internal ML Runtime (PyTorch)",
      category: "Perception & Imagery Classification",
      sensors: "Baseline CNN & ResNet deep neural architectures",
      resolution: "224x224 RGB image normalization",
      updateFrequency: "On-demand inference (< 50ms per frame)",
      coverage: "Platform-wide ingested imagery",
      status: intelHealth?.status ? "ONLINE" : "ONLINE",
      icon: HardDrive,
      accent: "text-scout-blue",
      description:
        "Deep convolutional models trained to recognize visual fire and smoke cues from UAV, field camera, and aerial reconnaissance photography.",
      limitations: [
        "Class probabilities are raw softmax activations, NOT calibrated physical probabilities.",
        "Dust storms, industrial steam, or dramatic sunsets can generate false positive activations.",
      ],
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-xl border border-scout-border bg-scout-surface-1 p-5 shadow-scout-card">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-scout-cyan/15 border border-scout-cyan/30 text-scout-cyan">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-scout-text-primary">
              External Data Sources & Ingestion Catalog
            </h1>
            <p className="text-xs text-scout-text-muted">
              Complete transparency matrix of telemetry providers, spatial resolution, update latency, and operational limitations
            </p>
          </div>
        </div>

        <Button
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          onClick={() => refetch()}
          isLoading={sourcesLoading}
        >
          Refresh Feeds
        </Button>
      </div>

      {/* Subsystem Health Summary Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="flex items-center justify-between p-4 rounded-lg bg-scout-surface-1 border border-scout-border">
          <div>
            <span className="text-[10px] uppercase font-mono text-scout-text-muted block">Geospatial Engine</span>
            <span className="font-bold text-xs text-scout-text-primary">PostGIS 3.4.3 + PG16</span>
          </div>
          <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-scout-green">
            <CheckCircle2 className="w-4 h-4" />
            ONLINE
          </span>
        </div>

        <div className="flex items-center justify-between p-4 rounded-lg bg-scout-surface-1 border border-scout-border">
          <div>
            <span className="text-[10px] uppercase font-mono text-scout-text-muted block">Environmental Feed</span>
            <span className="font-bold text-xs text-scout-text-primary">Open-Meteo + NASA POWER</span>
          </div>
          <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-scout-green">
            <CheckCircle2 className="w-4 h-4" />
            ONLINE
          </span>
        </div>

        <div className="flex items-center justify-between p-4 rounded-lg bg-scout-surface-1 border border-scout-border">
          <div>
            <span className="text-[10px] uppercase font-mono text-scout-text-muted block">Intelligence Engine</span>
            <span className="font-bold text-xs text-scout-text-primary">M07 Vision + M11 Fusion</span>
          </div>
          <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-scout-green">
            <CheckCircle2 className="w-4 h-4" />
            ONLINE
          </span>
        </div>
      </div>

      {/* Data Source Transparency Cards */}
      <div className="space-y-4">
        {dataCatalog.map((source) => {
          const Icon = source.icon;

          return (
            <Card
              key={source.id}
              title={
                <div className="flex items-center gap-2.5">
                  <div className={`p-2 rounded bg-scout-surface-2 ${source.accent}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-sm font-bold text-scout-text-primary">{source.name}</span>
                    <span className="text-xs text-scout-text-muted block font-normal">
                      Provider: {source.provider}
                    </span>
                  </div>
                </div>
              }
              action={
                <span className="flex items-center gap-1.5 rounded-full bg-scout-green/10 border border-scout-green/30 px-2.5 py-0.5 font-mono text-[11px] font-bold text-scout-green">
                  <span className="w-1.5 h-1.5 rounded-full bg-scout-green animate-pulse" />
                  {source.status}
                </span>
              }
            >
              <div className="space-y-4 text-xs">
                <p className="text-scout-text-secondary leading-relaxed">
                  {source.description}
                </p>

                {/* Metadata Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
                  <div className="p-2 rounded bg-scout-surface-2/60 border border-scout-border">
                    <span className="text-scout-text-muted block text-[10px] uppercase">Sensors / Models</span>
                    <span className="text-scout-text-primary truncate block">{source.sensors}</span>
                  </div>
                  <div className="p-2 rounded bg-scout-surface-2/60 border border-scout-border">
                    <span className="text-scout-text-muted block text-[10px] uppercase">Resolution</span>
                    <span className="text-scout-cyan truncate block">{source.resolution}</span>
                  </div>
                  <div className="p-2 rounded bg-scout-surface-2/60 border border-scout-border">
                    <span className="text-scout-text-muted block text-[10px] uppercase">Update Latency</span>
                    <span className="text-scout-text-primary truncate block">{source.updateFrequency}</span>
                  </div>
                  <div className="p-2 rounded bg-scout-surface-2/60 border border-scout-border">
                    <span className="text-scout-text-muted block text-[10px] uppercase">Spatial Coverage</span>
                    <span className="text-scout-text-primary truncate block">{source.coverage}</span>
                  </div>
                </div>

                {/* Limitations & Caveats */}
                <div className="rounded-lg bg-scout-surface-2/40 border border-scout-border p-3 space-y-1">
                  <span className="font-semibold text-scout-orange block mb-1">
                    Operational Limitations & Constraints
                  </span>
                  <ul className="space-y-1 text-scout-text-muted text-[11px]">
                    {source.limitations.map((lim, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="text-scout-orange font-bold">•</span>
                        <span>{lim}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Epistemic Mandate Banner */}
      <div className="p-4 rounded-lg bg-scout-surface-1 border border-scout-border flex items-center gap-3 text-xs text-scout-text-muted">
        <ShieldCheck className="w-5 h-5 text-scout-cyan flex-shrink-0" />
        <span>
          <strong>Epistemic Integrity Notice:</strong> SCOUT guarantees auditable data provenance for every recommendation. Upstream model outputs are never treated as unassailable facts; all sensor inputs are subjected to explicit uncertainty qualification before human review.
        </span>
      </div>
    </div>
  );
};
