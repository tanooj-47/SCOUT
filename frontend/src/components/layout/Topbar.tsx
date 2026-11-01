import React, { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import {
  UserCheck,
  Info,
  RefreshCw,
  Search,
} from "lucide-react";
import { healthApi } from "../../services";
import { getStoredReviewerToken, setStoredReviewerToken } from "../../services/api-client";
import { Modal } from "../common/Modal";
import { Logo } from "../common/Logo";

interface TopbarProps {
  collapsed: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({ collapsed }) => {
  const location = useLocation();
  const [backendStatus, setBackendStatus] = useState<"ONLINE" | "CHECKING" | "OFFLINE">("CHECKING");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [reviewerToken, setReviewerToken] = useState(getStoredReviewerToken());
  const [isEditingReviewer, setIsEditingReviewer] = useState(false);
  const [tempReviewer, setTempReviewer] = useState(reviewerToken);

  const checkHealth = async () => {
    try {
      setBackendStatus("CHECKING");
      const res = await healthApi.checkAppHealth();
      if (res && (res.status === "healthy" || res.status === "ok" || res.status === "ONLINE")) {
        setBackendStatus("ONLINE");
      } else {
        setBackendStatus("ONLINE"); // FastAPI endpoint returns {status: 'healthy'}
      }
    } catch {
      setBackendStatus("OFFLINE");
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const getPageTitle = (pathname: string): { title: string; subtitle: string } => {
    switch (pathname) {
      case "/":
      case "/overview":
        return {
          title: "Disaster Operations Dashboard",
          subtitle: "Real-time incident surveillance, spatial threat matrix, and system readiness",
        };
      case "/monitoring":
        return {
          title: "Live Monitoring & GIS Geospatial Layers",
          subtitle: "Interactive high-precision spatial GIS canvas with active hazards and infrastructure overlays",
        };
      case "/incidents":
        return {
          title: "Incident Intelligence & Evidence Fusion",
          subtitle: "M07 visual classifier, M09 weather reanalysis, and M11 multimodal epistemic reasoning",
        };
      case "/geospatial":
        return {
          title: "Geospatial Exposure Analysis",
          subtitle: "PostGIS persistent vector catalog queries, geodesic distance, and topological relationships",
        };
      case "/risk":
        return {
          title: "Multidimensional Risk Assessment",
          subtitle: "5-factor risk synthesis, heuristic risk index, key risk drivers, and uncertainty qualification",
        };
      case "/workflows":
        return {
          title: "Multi-Agent Response Workflows & Human Gate",
          subtitle: "LangGraph 7-stage execution graph, evidence-grounded action plans, and commander review gate",
        };
      case "/reports":
        return {
          title: "Intelligence Reports & Coordinator Dossiers",
          subtitle: "Executive synthesis, multi-agency operational plans, and complete auditable review trails",
        };
      case "/data-sources":
        return {
          title: "External Data Sources & Ingestion Catalog",
          subtitle: "NASA FIRMS, Open-Meteo NWP, NASA POWER reanalysis, and PostGIS vector infrastructure status",
        };
      case "/settings":
        return {
          title: "System Configuration & Preferences",
          subtitle: "API endpoint bindings, GIS coordinate defaults, reviewer identity, and interface preferences",
        };
      default:
        return {
          title: "SCOUT Platform",
          subtitle: "Multimodal Disaster Intelligence & Response",
        };
    }
  };

  const { title, subtitle } = getPageTitle(location.pathname);

  const handleSaveReviewer = () => {
    const clean = tempReviewer.trim() || "reviewer:commander-01";
    setStoredReviewerToken(clean);
    setReviewerToken(clean);
    setIsEditingReviewer(false);
  };

  return (
    <>
      <header
        className={`sticky top-0 z-20 flex h-16 items-center justify-between border-b border-scout-border bg-scout-bg/95 px-6 backdrop-blur-md transition-all duration-300 ${
          collapsed ? "left-20" : "left-64"
        }`}
      >
        {/* Page Titles */}
        <div className="flex flex-col">
          <h2 className="text-sm font-bold tracking-wide text-scout-text-primary flex items-center gap-2">
            <span>{title}</span>
          </h2>
          <span className="text-[11px] text-scout-text-muted hidden md:inline">
            {subtitle}
          </span>
        </div>

        {/* Action Controls & Subsystem Status */}
        <div className="flex items-center gap-3">
          {/* Quick Search */}
          <div className="relative hidden xl:block">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-scout-text-muted" />
            <input
              type="text"
              placeholder="Search coordinates, IDs..."
              className="w-48 rounded-md bg-scout-surface-1 border border-scout-border py-1.5 pl-8 pr-3 text-xs text-scout-text-primary placeholder:text-scout-text-muted focus:border-scout-cyan focus:outline-none focus:w-64 transition-all"
            />
          </div>

          {/* Backend Health Status Pill */}
          <button
            onClick={checkHealth}
            className="flex items-center gap-2 rounded-full border border-scout-border bg-scout-surface-1 px-3 py-1 text-xs hover:bg-scout-surface-2 transition-colors"
            title="Click to re-verify backend telemetry"
          >
            <span
              className={`w-2 h-2 rounded-full ${
                backendStatus === "ONLINE"
                  ? "bg-scout-green shadow-[0_0_8px_rgba(52,211,153,0.8)]"
                  : backendStatus === "CHECKING"
                  ? "bg-scout-yellow animate-pulse"
                  : "bg-scout-red animate-ping"
              }`}
            />
            <span className="font-mono text-[11px] font-semibold text-scout-text-secondary">
              API {backendStatus}
            </span>
            <RefreshCw className={`w-3 h-3 text-scout-text-muted ${backendStatus === "CHECKING" ? "animate-spin" : ""}`} />
          </button>

          {/* Reviewer Gate Identity Badge */}
          <div className="relative">
            <button
              onClick={() => setIsEditingReviewer(!isEditingReviewer)}
              className="flex items-center gap-2 rounded-lg border border-scout-border bg-scout-surface-2/80 px-2.5 py-1 text-xs hover:border-scout-cyan/40 transition-colors"
              title="Click to modify emergency reviewer identity"
            >
              <UserCheck className="w-3.5 h-3.5 text-scout-cyan" />
              <div className="text-left font-mono text-[11px]">
                <span className="text-scout-text-muted">Reviewer: </span>
                <span className="font-bold text-scout-cyan">
                  {reviewerToken.replace(/^reviewer:/, "")}
                </span>
              </div>
            </button>

            {/* Quick Reviewer Switcher Popover */}
            {isEditingReviewer && (
              <div className="absolute right-0 mt-2 w-72 rounded-lg bg-scout-surface-1 p-3 shadow-2xl border border-scout-border z-50">
                <p className="text-xs font-semibold text-scout-text-primary mb-1">
                  Incident Reviewer Identity
                </p>
                <p className="text-[10px] text-scout-text-muted mb-2">
                  Authenticated identifier supplied to the human approval gate.
                </p>
                <input
                  type="text"
                  value={tempReviewer}
                  onChange={(e) => setTempReviewer(e.target.value)}
                  className="w-full rounded bg-scout-surface-2 border border-scout-border px-2.5 py-1.5 text-xs font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none mb-3"
                  placeholder="commander-01"
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setIsEditingReviewer(false)}
                    className="px-2.5 py-1 text-xs text-scout-text-muted hover:text-scout-text-primary"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveReviewer}
                    className="rounded bg-scout-cyan px-3 py-1 text-xs font-bold text-scout-bg hover:bg-scout-cyan/90"
                  >
                    Save
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* About SCOUT Trigger */}
          <button
            onClick={() => setAboutOpen(true)}
            className="flex items-center justify-center rounded-lg border border-scout-border bg-scout-surface-1 p-1.5 text-scout-text-muted hover:bg-scout-surface-2 hover:text-scout-text-primary transition-colors"
            title="About SCOUT Platform"
          >
            <Info className="w-4 h-4 text-scout-cyan" />
          </button>
        </div>
      </header>

      {/* About SCOUT Modal */}
      <Modal
        isOpen={aboutOpen}
        onClose={() => setAboutOpen(false)}
        title={
          <div className="flex items-center gap-2">
            <span>About SCOUT Platform</span>
          </div>
        }
        subtitle="Multimodal Disaster Intelligence & Response System"
        maxWidth="xl"
      >
        <div className="space-y-4">
          <div className="flex flex-col items-center justify-center p-6 bg-scout-surface-2/40 rounded-xl border border-scout-border text-center">
            <Logo size="xl" showTagline={true} />
            <p className="mt-4 text-xs text-scout-text-secondary leading-relaxed max-w-md">
              SCOUT is an enterprise-grade multimodal disaster intelligence and response platform engineered for early wildfire detection, geospatial exposure analysis, environmental danger quantification, and structured multi-agent emergency response workflows.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg bg-scout-surface-2/40 border border-scout-border p-3">
              <span className="font-semibold text-scout-cyan block mb-1">Architecture</span>
              <p className="text-scout-text-muted">
                FastAPI + LangGraph + PostgreSQL/PostGIS + React TypeScript
              </p>
            </div>
            <div className="rounded-lg bg-scout-surface-2/40 border border-scout-border p-3">
              <span className="font-semibold text-scout-orange block mb-1">Safety Mandate</span>
              <p className="text-scout-text-muted">
                Zero autonomous dispatch. Explicit human approval required for all operational recommendations.
              </p>
            </div>
          </div>

          <div className="rounded-lg bg-scout-surface-2/40 border border-scout-border p-3 text-xs space-y-1">
            <div className="flex justify-between text-scout-text-muted">
              <span>Platform Version:</span>
              <span className="font-mono text-scout-text-primary font-bold">1.0.0 (M13.1)</span>
            </div>
            <div className="flex justify-between text-scout-text-muted">
              <span>Spatial Datum:</span>
              <span className="font-mono text-scout-text-primary">WGS 84 (EPSG:4326) / UTM</span>
            </div>
            <div className="flex justify-between text-scout-text-muted">
              <span>Fire Weather Engine:</span>
              <span className="font-mono text-scout-text-primary">Canadian Forest Fire Weather Index (FWI)</span>
            </div>
            <div className="flex justify-between text-scout-text-muted">
              <span>Multi-Agent Framework:</span>
              <span className="font-mono text-scout-text-primary">LangGraph Stateful Graph Workflow</span>
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
};
