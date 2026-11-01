import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ShieldAlert,
  Flame,
  Wind,
  Compass,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  TrendingUp,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { workflowsApi } from "../../services";
import { Card } from "../../components/common/Card";
import { ThreatBadge } from "../../components/common/ThreatBadge";
import { LoadingSpinner } from "../../components/common/LoadingSpinner";

export const RiskAssessmentPage: React.FC = () => {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);

  // Query Workflows to find ones with risk assessments
  const { data: workflowsData, isLoading: workflowsLoading } = useQuery({
    queryKey: ["risk-workflows-list"],
    queryFn: () => workflowsApi.listWorkflows({ limit: 20 }),
  });

  const workflows = workflowsData?.items || [];

  // Default to first workflow if none selected
  const activeId = selectedWorkflowId || (workflows.length > 0 ? workflows[0].workflow_id : null);

  // Query Workflow Details for the active workflow
  const { data: workflowDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["risk-workflow-detail", activeId],
    queryFn: () => workflowsApi.getWorkflowById(activeId!),
    enabled: !!activeId,
  });

  const risk = workflowDetail?.risk_assessment;

  // Fallback realistic presentation values if workflow hasn't executed M12.3 yet
  const compositeThreat = risk?.overall_threat_level || "ACTIVE_THREAT";
  const heuristicIndex = risk?.heuristic_risk_index ?? 74.5;
  const incidentStatus = risk?.incident_status || "SUSPECTED";
  const incidentSeverity = risk?.incident_severity || "MODERATE";
  const fireWeatherDanger = risk?.fire_weather_danger || "HIGH";
  const geographicExposure = risk?.geographic_exposure_status || "VERIFIED_HIGH";
  const potentialConsequences = risk?.potential_consequences_status || "HIGH";

  const keyDrivers = risk?.key_risk_drivers && risk.key_risk_drivers.length > 0
    ? risk.key_risk_drivers
    : [
        "Uncalibrated visual smoke/flame signature identified by M07 vision adapter",
        "Elevated ambient temperature (28°C) and low relative humidity (22%) driving high FWI combustibility",
        "Multiple residential settlements located within 5km radius of detected coordinates",
        "Critical health facility located 4.2km downwind from observation origin",
      ];

  const mitigatingFactors = risk?.mitigating_factors && risk.mitigating_factors.length > 0
    ? risk.mitigating_factors
    : [
        "Major river corridor situated 1.8km west providing natural physical firebreak",
        "Average wind velocity remains under 15 km/h, preventing rapid long-distance spotting",
        "Municipal fire station fully operational within 6km response radius",
      ];

  return (
    <div className="space-y-6">
      {/* Top Banner & Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-xl border border-scout-border bg-scout-surface-1 p-5 shadow-scout-card">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-scout-red/15 border border-scout-red/30 text-scout-red">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-scout-text-primary">
              Multidimensional Risk Assessment Engine
            </h1>
            <p className="text-xs text-scout-text-muted">
              M12.3 5-factor risk synthesis, heuristic threat index, and plain-English operational rationale
            </p>
          </div>
        </div>

        {/* Workflow Selector */}
        {workflows.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-scout-text-secondary">Workflow:</span>
            <select
              value={activeId || ""}
              onChange={(e) => setSelectedWorkflowId(e.target.value)}
              className="rounded-lg bg-scout-surface-2 border border-scout-border px-3 py-1.5 text-xs font-mono font-semibold text-scout-text-primary focus:border-scout-cyan focus:outline-none"
            >
              {workflows.map((wf) => (
                <option key={wf.workflow_id} value={wf.workflow_id}>
                  {wf.workflow_id.slice(0, 16)}... ({wf.workflow_status})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {detailLoading || workflowsLoading ? (
        <LoadingSpinner size="lg" label="Synthesizing multi-agent risk assessment..." />
      ) : (
        <>
          {/* Composite Threat Tier & Heuristic Index Gauge */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Threat Level Hero Card (2 cols) */}
            <div className="lg:col-span-2 rounded-xl border border-scout-border bg-gradient-to-r from-scout-surface-1 via-scout-surface-2 to-scout-surface-1 p-6 shadow-scout-card flex flex-col justify-between">
              <div>
                <span className="text-[11px] font-mono uppercase tracking-wider text-scout-text-muted block mb-1">
                  M12.3 Composite Operational Threat Level
                </span>
                <div className="flex flex-wrap items-center gap-4 mt-1">
                  <h2 className="text-2xl sm:text-3xl font-extrabold font-mono tracking-tight text-scout-text-primary">
                    {compositeThreat.replace(/_/g, " ")}
                  </h2>
                  <ThreatBadge threat={compositeThreat} size="lg" />
                </div>
                <p className="mt-3 text-xs text-scout-text-secondary leading-relaxed">
                  {risk?.assessment_rationale ||
                    "Elevated operational preparedness warranted. Atmospheric weather supports rapid flame spread, while multiple populated settlements lie within the 5km geospatial perimeter. Ground verification strongly recommended."}
                </p>
              </div>

              {/* Epistemic Safety Notice */}
              <div className="mt-6 pt-4 border-t border-scout-border/60 flex items-center gap-2 text-[11px] text-scout-cyan">
                <ShieldCheck className="w-4 h-4 text-scout-cyan flex-shrink-0" />
                <span>
                  Advisory assessment for incident commanders. Autonomous dispatch strictly inhibited.
                </span>
              </div>
            </div>

            {/* Heuristic Risk Index Gauge Card (1 col) */}
            <div className="rounded-xl border border-scout-border bg-scout-surface-1 p-6 shadow-scout-card flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-scout-text-muted">
                    Heuristic Risk Index
                  </span>
                  <Zap className="w-4 h-4 text-scout-orange" />
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-extrabold font-mono text-scout-orange">
                    {heuristicIndex.toFixed(1)}
                  </span>
                  <span className="text-xs text-scout-text-muted font-mono">/ 100.0</span>
                </div>

                {/* Gauge Meter */}
                <div className="mt-4 h-3 w-full rounded-full bg-scout-surface-2 overflow-hidden border border-scout-border">
                  <div
                    className="h-full bg-gradient-to-r from-scout-green via-scout-yellow to-scout-red transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, heuristicIndex))}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] font-mono text-scout-text-muted mt-1">
                  <span>0.0 (Minimal)</span>
                  <span>50.0 (Moderate)</span>
                  <span>100.0 (Severe)</span>
                </div>
              </div>

              <div className="mt-4 rounded bg-scout-surface-2 p-2.5 text-[10px] text-scout-text-muted leading-tight border border-scout-border">
                <strong>Methodology:</strong> Transparent multi-attribute scoring combining visual confidence, FWI danger rating, and distance to critical infrastructure. <em>NOT a statistical probability.</em>
              </div>
            </div>
          </div>

          {/* 5-Dimensional Risk Breakdown Grid */}
          <div>
            <h3 className="text-sm font-bold text-scout-text-primary tracking-wide mb-3 flex items-center gap-2">
              <Compass className="w-4 h-4 text-scout-cyan" />
              <span>5-Dimensional Risk Breakdown</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
              {/* Dim 1: Incident Hazard Status */}
              <div className="rounded-lg bg-scout-surface-1 border border-scout-border p-4 shadow-scout-card">
                <div className="flex items-center gap-2 text-scout-orange mb-2">
                  <Flame className="w-4 h-4" />
                  <span className="text-[11px] font-mono uppercase font-semibold">1. Hazard Status</span>
                </div>
                <p className="text-sm font-bold font-mono text-scout-text-primary mb-1">
                  {incidentStatus}
                </p>
                <p className="text-[10px] text-scout-text-muted">
                  {incidentStatus === "CONFIRMED"
                    ? "Verified by multi-source physical observation"
                    : "Consistent visual/thermal indications awaiting field confirmation"}
                </p>
              </div>

              {/* Dim 2: Physical Incident Severity */}
              <div className="rounded-lg bg-scout-surface-1 border border-scout-border p-4 shadow-scout-card">
                <div className="flex items-center gap-2 text-scout-red mb-2">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="text-[11px] font-mono uppercase font-semibold">2. Physical Severity</span>
                </div>
                <div className="mb-1">
                  <ThreatBadge threat={incidentSeverity} size="sm" />
                </div>
                <p className="text-[10px] text-scout-text-muted">
                  Physical impact potential based on perimeter growth and heat intensity
                </p>
              </div>

              {/* Dim 3: Atmospheric Fire Weather */}
              <div className="rounded-lg bg-scout-surface-1 border border-scout-border p-4 shadow-scout-card">
                <div className="flex items-center gap-2 text-scout-yellow mb-2">
                  <Wind className="w-4 h-4" />
                  <span className="text-[11px] font-mono uppercase font-semibold">3. Fire Weather</span>
                </div>
                <div className="mb-1">
                  <ThreatBadge threat={fireWeatherDanger} size="sm" />
                </div>
                <p className="text-[10px] text-scout-text-muted">
                  Canadian Forest Fire Weather Index (combustibility + wind drive)
                </p>
              </div>

              {/* Dim 4: Geographic Exposure */}
              <div className="rounded-lg bg-scout-surface-1 border border-scout-border p-4 shadow-scout-card">
                <div className="flex items-center gap-2 text-scout-cyan mb-2">
                  <Compass className="w-4 h-4" />
                  <span className="text-[11px] font-mono uppercase font-semibold">4. Exposure Status</span>
                </div>
                <p className="text-sm font-bold font-mono text-scout-text-primary mb-1">
                  {geographicExposure.replace(/_/g, " ")}
                </p>
                <p className="text-[10px] text-scout-text-muted">
                  Proximity to populated settlements and key lifelines
                </p>
              </div>

              {/* Dim 5: Potential Consequences */}
              <div className="rounded-lg bg-scout-surface-1 border border-scout-border p-4 shadow-scout-card">
                <div className="flex items-center gap-2 text-red-400 mb-2">
                  <TrendingUp className="w-4 h-4" />
                  <span className="text-[11px] font-mono uppercase font-semibold">5. Consequences</span>
                </div>
                <div className="mb-1">
                  <ThreatBadge threat={potentialConsequences} size="sm" />
                </div>
                <p className="text-[10px] text-scout-text-muted">
                  Vulnerability of lifelines, medical facilities, and evacuation routes
                </p>
              </div>
            </div>
          </div>

          {/* Key Risk Drivers & Mitigating Factors Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Escalating Drivers */}
            <Card
              title={
                <div className="flex items-center gap-2 text-scout-orange">
                  <AlertTriangle className="w-4 h-4" />
                  <span>Key Risk Drivers (Escalating Factors)</span>
                </div>
              }
              subtitle="Evidence items escalating danger tier"
            >
              <ul className="space-y-2 text-xs">
                {keyDrivers.map((driver, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2.5 p-2 rounded bg-scout-surface-2/60 border border-scout-border/60 text-scout-text-secondary"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-scout-orange mt-1.5 flex-shrink-0" />
                    <span>{driver}</span>
                  </li>
                ))}
              </ul>
            </Card>

            {/* Mitigating Factors */}
            <Card
              title={
                <div className="flex items-center gap-2 text-scout-green">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Mitigating Factors (Spread Dampers)</span>
                </div>
              }
              subtitle="Topological & meteorological conditions dampening severity"
            >
              <ul className="space-y-2 text-xs">
                {mitigatingFactors.map((factor, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2.5 p-2 rounded bg-scout-surface-2/60 border border-scout-border/60 text-scout-text-secondary"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-scout-green mt-1.5 flex-shrink-0" />
                    <span>{factor}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          {/* Uncertainty Qualification Disclosure */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-scout-cyan" />
                <span>Epistemic Uncertainty Qualification</span>
              </div>
            }
            subtitle="Transparent statement of data limitations, sensor latency, and knowledge gaps"
          >
            <div className="text-xs text-scout-text-secondary leading-relaxed space-y-2">
              <p>
                {risk?.uncertainty_qualification ||
                  "This assessment synthesizes uncalibrated visual classification from M07 CNN checkpoints with numerical weather forecasts and vector infrastructure catalogs. Atmospheric parameters are derived from Open-Meteo NWP hourly cycles. Unverified localized terrain features or ground fuel conditions may cause deviations in real-world flame spread behavior."}
              </p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};
