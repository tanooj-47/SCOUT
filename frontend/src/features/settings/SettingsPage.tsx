import React, { useState } from "react";
import {
  Settings,
  UserCheck,
  Globe,
  Sliders,
  Check,
  RotateCcw,
  ShieldCheck,
  Server,
  Palette,
} from "lucide-react";
import { Card } from "../../components/common/Card";
import { Button } from "../../components/common/Button";
import { Logo } from "../../components/common/Logo";
import { getStoredReviewerToken, setStoredReviewerToken, API_BASE } from "../../services/api-client";

export const SettingsPage: React.FC = () => {
  const [reviewerToken, setReviewerToken] = useState(getStoredReviewerToken());
  const [defaultLat, setDefaultLat] = useState("37.7749");
  const [defaultLon, setDefaultLon] = useState("-122.4194");
  const [defaultRadius, setDefaultRadius] = useState("5000");
  const [pollingInterval, setPollingInterval] = useState("30");
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanToken = reviewerToken.trim() || "reviewer:commander-01";
    setStoredReviewerToken(cleanToken);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  const handleResetDefaults = () => {
    setReviewerToken("reviewer:commander-01");
    setStoredReviewerToken("reviewer:commander-01");
    setDefaultLat("37.7749");
    setDefaultLon("-122.4194");
    setDefaultRadius("5000");
    setPollingInterval("30");
  };

  const paletteSwatches = [
    { name: "Background", hex: "#061321", label: "bg-scout-bg" },
    { name: "Sidebar", hex: "#0B1B2C", label: "bg-scout-sidebar" },
    { name: "Surface 1", hex: "#10243A", label: "bg-scout-surface-1" },
    { name: "Surface 2", hex: "#172D45", label: "bg-scout-surface-2" },
    { name: "Border", hex: "#29445F", label: "border-scout-border" },
    { name: "Brand Cyan", hex: "#28BCEB", label: "text-scout-cyan" },
    { name: "Brand Blue", hex: "#278BC4", label: "text-scout-blue" },
    { name: "Flame Orange", hex: "#FF781F", label: "text-scout-orange" },
    { name: "Critical Red", hex: "#EF4444", label: "text-scout-red" },
    { name: "Alert Yellow", hex: "#FBBF24", label: "text-scout-yellow" },
    { name: "Safe Green", hex: "#34D399", label: "text-scout-green" },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-xl border border-scout-border bg-scout-surface-1 p-5 shadow-scout-card">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-scout-cyan/15 border border-scout-cyan/30 text-scout-cyan">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-scout-text-primary">
              System Settings & Configuration
            </h1>
            <p className="text-xs text-scout-text-muted">
              Configure Incident Commander credentials, map defaults, and inspection telemetry
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            icon={RotateCcw}
            onClick={handleResetDefaults}
          >
            Reset Defaults
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            icon={Check}
            onClick={handleSave}
          >
            {saveSuccess ? "Saved!" : "Save Changes"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Reviewer Identity & API Binding (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Reviewer Gate Identity Configuration */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-scout-cyan" />
                <span>Incident Reviewer Security Identity</span>
              </div>
            }
            subtitle="Configures the authoritative reviewer identity passed in Authorization and X-Reviewer-Token headers"
          >
            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-scout-text-secondary mb-1 font-semibold">
                  Reviewer Identifier / Bearer Token
                </label>
                <input
                  type="text"
                  value={reviewerToken}
                  onChange={(e) => setReviewerToken(e.target.value)}
                  placeholder="reviewer:commander-01"
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-cyan text-sm focus:border-scout-cyan focus:outline-none"
                />
                <p className="text-[11px] text-scout-text-muted mt-1 leading-relaxed">
                  In development and testing environments, the backend auth dependency (<code>backend/app/core/auth.py</code>) derives the authoritative reviewer identifier from this token header. (Default: <code>reviewer:commander-01</code>).
                </p>
              </div>

              <div className="rounded bg-scout-surface-2 p-3 border border-scout-border text-[11px] text-scout-text-secondary space-y-1">
                <span className="font-semibold text-scout-text-primary block">Current Header Payload:</span>
                <div className="font-mono text-scout-cyan">
                  Authorization: Bearer {reviewerToken}
                </div>
                <div className="font-mono text-scout-cyan">
                  X-Reviewer-Token: {reviewerToken}
                </div>
              </div>
            </div>
          </Card>

          {/* Map Defaults & GIS Spatial Parameters */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-scout-cyan" />
                <span>Default Geographic Centroid & Search Radius</span>
              </div>
            }
            subtitle="Default spatial parameters initialized in GIS analysis and monitoring maps"
          >
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">Default Latitude (°N)</label>
                <input
                  type="number"
                  step="0.0001"
                  value={defaultLat}
                  onChange={(e) => setDefaultLat(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">Default Longitude (°E)</label>
                <input
                  type="number"
                  step="0.0001"
                  value={defaultLon}
                  onChange={(e) => setDefaultLon(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">Default Radius (Meters)</label>
                <input
                  type="number"
                  step="500"
                  value={defaultRadius}
                  onChange={(e) => setDefaultRadius(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                />
              </div>
            </div>
          </Card>

          {/* Telemetry Polling Rate */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-scout-cyan" />
                <span>Operational Telemetry Polling Rates</span>
              </div>
            }
            subtitle="Adjust background polling intervals for live incident and workflow monitoring"
          >
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-scout-text-secondary mb-1 font-medium">Polling Cadence</label>
                <select
                  value={pollingInterval}
                  onChange={(e) => setPollingInterval(e.target.value)}
                  className="w-full sm:w-64 rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                >
                  <option value="10">Aggressive (Every 10 seconds)</option>
                  <option value="15">High Priority (Every 15 seconds)</option>
                  <option value="30">Standard Operational (Every 30 seconds)</option>
                  <option value="60">Low Bandwidth (Every 60 seconds)</option>
                </select>
              </div>
            </div>
          </Card>

          {/* Official SCOUT Brand Swatches */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Palette className="w-4 h-4 text-scout-cyan" />
                <span>Official Brand Identity Palette Swatches</span>
              </div>
            }
            subtitle="Enterprise disaster command visual language"
          >
            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3 text-xs">
              {paletteSwatches.map((swatch) => (
                <div
                  key={swatch.name}
                  className="rounded-lg bg-scout-surface-2 border border-scout-border p-2 space-y-1.5"
                >
                  <div
                    className="h-8 w-full rounded border border-scout-border/60 shadow-sm"
                    style={{ backgroundColor: swatch.hex }}
                  />
                  <div>
                    <span className="font-semibold text-scout-text-primary block text-[11px] truncate">
                      {swatch.name}
                    </span>
                    <span className="font-mono text-[10px] text-scout-text-muted">
                      {swatch.hex}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Right Column: Platform About & Backend Connection (1 col) */}
        <div className="space-y-6">
          {/* About SCOUT Platform Card */}
          <Card
            title="About SCOUT"
            subtitle="Multimodal Disaster Intelligence"
          >
            <div className="space-y-4 text-xs text-center flex flex-col items-center">
              <Logo size="xl" showTagline={true} />

              <p className="text-scout-text-secondary leading-relaxed text-[11px]">
                SCOUT is an integrated disaster intelligence and multi-agent incident management platform providing autonomous data synthesis and human-authorized decision support for emergency managers.
              </p>

              <div className="w-full text-left rounded-lg bg-scout-surface-2/60 border border-scout-border p-3 space-y-2 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-scout-text-muted">Release Milestone:</span>
                  <span className="font-mono font-bold text-scout-cyan">Block 13.1</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-scout-text-muted">Application Version:</span>
                  <span className="font-mono text-scout-text-primary">1.0.0-prod</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-scout-text-muted">GIS Engine:</span>
                  <span className="font-mono text-scout-text-primary">MapLibre GL JS 4.7</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-scout-text-muted">Agent Orchestrator:</span>
                  <span className="font-mono text-scout-text-primary">LangGraph 7-Stage</span>
                </div>
              </div>
            </div>
          </Card>

          {/* Backend Connection Info */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Server className="w-4 h-4 text-scout-cyan" />
                <span>API Connection Binding</span>
              </div>
            }
            subtitle="FastAPI server communication"
          >
            <div className="space-y-2 text-xs font-mono">
              <div className="p-2.5 rounded bg-scout-surface-2 border border-scout-border">
                <span className="text-scout-text-muted block text-[10px] uppercase">Configured Base URL</span>
                <span className="text-scout-cyan font-bold break-all">{API_BASE}</span>
              </div>
              <p className="text-[11px] text-scout-text-muted font-sans leading-relaxed">
                In production, Vite proxies <code>/api/v1</code> requests directly to <code>http://127.0.0.1:8000</code>.
              </p>
            </div>
          </Card>

          {/* Safety Notice */}
          <div className="p-4 rounded-lg bg-scout-surface-1 border border-scout-border flex items-center gap-3 text-xs text-scout-text-muted">
            <ShieldCheck className="w-5 h-5 text-scout-cyan flex-shrink-0" />
            <span>
              <strong>Advisory Operations:</strong> Zero autonomous emergency vehicle dispatch. Human incident commander approval is strictly required.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
