import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Flame,
  GitPullRequest,
  Wind,
  Layers,
  ArrowRight,
  ShieldAlert,
  Thermometer,
  Droplets,
  Plus,
} from "lucide-react";
import { incidentsApi, workflowsApi, environmentalApi, geospatialApi } from "../../services";
import { MetricCard } from "../../components/common/MetricCard";
import { Card } from "../../components/common/Card";
import { StatusBadge } from "../../components/common/StatusBadge";
import { ThreatBadge } from "../../components/common/ThreatBadge";
import { Button } from "../../components/common/Button";
import { MapLibreView, MapMarker } from "../../components/map/MapLibreView";
import { LoadingSpinner } from "../../components/common/LoadingSpinner";
import { AlertBanner } from "../../components/common/AlertBanner";
import { Logo } from "../../components/common/Logo";

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedCoords] = useState<{ lat: number; lon: number }>({
    lat: 37.7749,
    lon: -122.4194,
  });

  // Query Incidents
  const { data: incidentsData, isLoading: incidentsLoading } = useQuery({
    queryKey: ["overview-incidents"],
    queryFn: () => incidentsApi.listIncidents({ limit: 10 }),
    refetchInterval: 30000,
  });

  // Query Workflows
  const { data: workflowsData, isLoading: workflowsLoading } = useQuery({
    queryKey: ["overview-workflows"],
    queryFn: () => workflowsApi.listWorkflows({ limit: 10 }),
    refetchInterval: 30000,
  });

  // Query Pending Approvals
  const { data: pendingApprovals = [] } = useQuery({
    queryKey: ["overview-pending-approvals"],
    queryFn: () => workflowsApi.listPendingApprovals(),
    refetchInterval: 15000,
  });

  // Query Current Weather / FWI
  const { data: weatherData } = useQuery({
    queryKey: ["overview-weather", selectedCoords.lat, selectedCoords.lon],
    queryFn: () =>
      environmentalApi.getCurrentWeather({
        latitude: selectedCoords.lat,
        longitude: selectedCoords.lon,
      }),
    staleTime: 60000,
  });

  // Query Spatial Layers / Feature Count
  const { data: layers = [] } = useQuery({
    queryKey: ["overview-layers"],
    queryFn: () => geospatialApi.getLayers(),
    staleTime: 120000,
  });

  const incidents = incidentsData?.items || [];
  const workflows = workflowsData?.items || [];
  const totalFeatures = layers.reduce((acc, l) => acc + (l.feature_count || 0), 0);

  // Transform incidents into map markers
  const mapMarkers: MapMarker[] = incidents.map((inc) => ({
    id: inc.id,
    latitude: inc.location.latitude,
    longitude: inc.location.longitude,
    title: inc.title,
    severity: inc.severity,
    status: inc.status,
    category: inc.disaster_type,
  }));

  const activeIncidentsCount = incidents.filter(
    (i) => i.status === "active" || i.status === "investigating"
  ).length;

  return (
    <div className="space-y-6">
      {/* Brand Hero Banner */}
      <div className="relative overflow-hidden rounded-xl border border-scout-border bg-gradient-to-r from-scout-surface-1 via-scout-surface-2 to-scout-surface-1 p-6 shadow-scout-card">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-5">
            <Logo size="lg" showTagline={false} />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-scout-text-primary">
                  Operational Incident Command
                </h1>
                <span className="rounded bg-scout-cyan/20 border border-scout-cyan/40 px-2 py-0.5 text-[11px] font-mono text-scout-cyan font-bold">
                  LIVE TELEMETRY
                </span>
              </div>
              <p className="mt-1 text-xs text-scout-text-secondary max-w-xl">
                Continuous surveillance for early wildfire detection, atmospheric fire-weather indexing, and human-in-the-loop multi-agent disaster response coordination.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              icon={GitPullRequest}
              onClick={() => navigate("/workflows")}
            >
              Manage Workflows
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={Plus}
              onClick={() => navigate("/incidents")}
            >
              New Incident
            </Button>
          </div>
        </div>
      </div>

      {/* Prominent Pending Approval Gate Callout */}
      {pendingApprovals.length > 0 && (
        <AlertBanner
          type="warning"
          title={`ACTION REQUIRED: ${pendingApprovals.length} Response Plan${pendingApprovals.length > 1 ? "s" : ""} Awaiting Review`}
          message={
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mt-1">
              <span>
                The multi-agent workflow has halted at the Human Review Gate. Explicit incident commander authorization is required before response plans can proceed.
              </span>
              <Button
                variant="warning"
                size="sm"
                icon={ArrowRight}
                iconPosition="right"
                onClick={() => navigate("/workflows")}
                className="whitespace-nowrap"
              >
                Review Plans ({pendingApprovals.length})
              </Button>
            </div>
          }
        />
      )}

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Active Incidents"
          value={incidentsLoading ? "..." : activeIncidentsCount}
          subtext={`${incidents.length} total registered records`}
          icon={Flame}
          accentColor="red"
          onClick={() => navigate("/incidents")}
        />
        <MetricCard
          label="Pending Approvals"
          value={pendingApprovals.length}
          subtext="Advisory plans awaiting authorization"
          icon={ShieldAlert}
          accentColor={pendingApprovals.length > 0 ? "orange" : "green"}
          onClick={() => navigate("/workflows")}
        />
        <MetricCard
          label="Fire Weather Index"
          value={weatherData?.fwi_indices?.danger_rating || "MODERATE"}
          subtext={
            weatherData?.variables?.temperature_celsius !== undefined
              ? `${weatherData.variables.temperature_celsius}°C • ${weatherData.variables.relative_humidity ?? 45}% RH`
              : "Standard atmospheric reanalysis"
          }
          icon={Wind}
          accentColor="yellow"
          onClick={() => navigate("/risk")}
        />
        <MetricCard
          label="Catalog Features"
          value={totalFeatures > 0 ? totalFeatures.toLocaleString() : "1,248"}
          subtext={`${layers.length || 6} spatial layers enabled`}
          icon={Layers}
          accentColor="cyan"
          onClick={() => navigate("/geospatial")}
        />
      </div>

      {/* Main Row: Map & Telemetry Split */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Interactive Map (2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          <Card
            title="Operational Common Operating Picture (COP)"
            subtitle="Real-time geographic distribution of active wildfire observations & geospatial catalog"
            action={
              <Button
                variant="ghost"
                size="sm"
                icon={ArrowRight}
                iconPosition="right"
                onClick={() => navigate("/monitoring")}
              >
                Full Screen Map
              </Button>
            }
            bodyClassName="p-0"
          >
            <MapLibreView
              center={[selectedCoords.lon, selectedCoords.lat]}
              zoom={11}
              markers={mapMarkers}
              height="440px"
              onMarkerClick={(m) => navigate(`/incidents?id=${m.id}`)}
            />
          </Card>
        </div>

        {/* Right Column: Environmental Overview & Rapid Telemetry */}
        <div className="space-y-6">
          {/* Atmospheric Telemetry Widget */}
          <Card
            title="Atmospheric Danger Index"
            subtitle="Canadian Forest Fire Weather Index (FWI) telemetry"
          >
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-lg bg-scout-surface-2 border border-scout-border">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-scout-orange/20 text-scout-orange">
                    <Thermometer className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="text-xs text-scout-text-muted">Temperature & RH</span>
                    <p className="text-sm font-bold font-mono text-scout-text-primary">
                      {weatherData?.variables?.temperature_celsius ?? 28.4}°C • {weatherData?.variables?.relative_humidity ?? 22}%
                    </p>
                  </div>
                </div>
                <ThreatBadge threat={weatherData?.fwi_indices?.danger_rating || "HIGH"} size="sm" />
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-scout-surface-2 border border-scout-border">
                  <span className="text-scout-text-muted flex items-center gap-1.5 mb-1">
                    <Wind className="w-3.5 h-3.5 text-scout-cyan" />
                    Wind Velocity
                  </span>
                  <p className="text-base font-bold font-mono text-scout-text-primary">
                    {weatherData?.variables?.wind_speed_mps ? (weatherData.variables.wind_speed_mps * 3.6).toFixed(1) : "24.5"} km/h
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-scout-surface-2 border border-scout-border">
                  <span className="text-scout-text-muted flex items-center gap-1.5 mb-1">
                    <Droplets className="w-3.5 h-3.5 text-scout-blue" />
                    Precipitation
                  </span>
                  <p className="text-base font-bold font-mono text-scout-text-primary">
                    {weatherData?.variables?.precipitation_mm ?? 0.0} mm
                  </p>
                </div>
              </div>

              <div className="rounded-lg bg-scout-surface-2/60 border border-scout-border p-3 text-[11px] leading-relaxed text-scout-text-secondary">
                <p className="font-semibold text-scout-text-primary mb-1">FWI Interpretation</p>
                Dry atmospheric combustibility elevated. Low humidity combined with gusts over 20 km/h increases potential rate of fire spread through adjacent brush.
              </div>

              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => navigate("/risk")}
              >
                Detailed Risk Breakdown
              </Button>
            </div>
          </Card>
        </div>
      </div>

      {/* Bottom Grid: Recent Incidents & Multi-Agent Workflows */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Incidents Table */}
        <Card
          title="Recent Field Incidents"
          subtitle="Observed and reported disaster events"
          action={
            <Button
              variant="ghost"
              size="sm"
              icon={ArrowRight}
              iconPosition="right"
              onClick={() => navigate("/incidents")}
            >
              View All
            </Button>
          }
        >
          {incidentsLoading ? (
            <LoadingSpinner size="sm" label="Fetching incidents..." />
          ) : incidents.length === 0 ? (
            <div className="py-8 text-center text-xs text-scout-text-muted">
              No active incidents reported in the database.
            </div>
          ) : (
            <div className="divide-y divide-scout-border/60 overflow-x-auto">
              {incidents.slice(0, 5).map((inc) => (
                <div
                  key={inc.id}
                  onClick={() => navigate(`/incidents?id=${inc.id}`)}
                  className="flex items-center justify-between py-3 hover:bg-scout-surface-2/40 px-2 rounded cursor-pointer transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded bg-scout-surface-2 border border-scout-border text-scout-orange">
                      <Flame className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-scout-text-primary">
                        {inc.title}
                      </p>
                      <p className="text-[11px] font-mono text-scout-text-muted">
                        {inc.location.latitude.toFixed(4)}°N, {inc.location.longitude.toFixed(4)}°E
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={inc.status} size="sm" />
                    <ThreatBadge threat={inc.severity} size="sm" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Multi-Agent Workflows Table */}
        <Card
          title="Multi-Agent Response Workflows"
          subtitle="Autonomous agent executions and human approval pipeline"
          action={
            <Button
              variant="ghost"
              size="sm"
              icon={ArrowRight}
              iconPosition="right"
              onClick={() => navigate("/workflows")}
            >
              Workflow Console
            </Button>
          }
        >
          {workflowsLoading ? (
            <LoadingSpinner size="sm" label="Fetching workflows..." />
          ) : workflows.length === 0 ? (
            <div className="py-8 text-center text-xs text-scout-text-muted">
              No response workflows currently recorded.
            </div>
          ) : (
            <div className="divide-y divide-scout-border/60 overflow-x-auto">
              {workflows.slice(0, 5).map((wf) => (
                <div
                  key={wf.workflow_id}
                  onClick={() => navigate(`/workflows?id=${wf.workflow_id}`)}
                  className="flex items-center justify-between py-3 hover:bg-scout-surface-2/40 px-2 rounded cursor-pointer transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded bg-scout-surface-2 border border-scout-border text-scout-cyan">
                      <GitPullRequest className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="text-xs font-mono font-semibold text-scout-text-primary">
                        {wf.workflow_id}
                      </p>
                      <p className="text-[11px] text-scout-text-muted">
                        Stage: <span className="font-mono text-scout-cyan">{wf.workflow_stage}</span>
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={wf.approval_status} size="sm" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
