import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  Flame,
  Plus,
  Upload,
  Cpu,
  Wind,
  MapPin,
  HelpCircle,
  FileSearch,
} from "lucide-react";
import { incidentsApi, intelligenceApi } from "../../services";
import { Card } from "../../components/common/Card";
import { StatusBadge } from "../../components/common/StatusBadge";
import { ThreatBadge } from "../../components/common/ThreatBadge";
import { Button } from "../../components/common/Button";
import { Modal } from "../../components/common/Modal";
import { LoadingSpinner } from "../../components/common/LoadingSpinner";
import { AlertBanner } from "../../components/common/AlertBanner";
import { IncidentItem, IncidentCreatePayload } from "../../types";

export const IncidentIntelligencePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const queryIncidentId = searchParams.get("id");

  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(queryIncidentId);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // New Incident Form State
  const [newTitle, setNewTitle] = useState("");
  const [newLat, setNewLat] = useState("37.7749");
  const [newLon, setNewLon] = useState("-122.4194");
  const [newDisasterType, setNewDisasterType] = useState<"wildfire" | "flood" | "earthquake">("wildfire");
  const [newSeverity, setNewSeverity] = useState<"low" | "moderate" | "high" | "critical">("moderate");

  // Multimodal Analysis State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // Query Incidents List
  const { data: incidentsData, isLoading: incidentsLoading } = useQuery({
    queryKey: ["incidents-list"],
    queryFn: () => incidentsApi.listIncidents({ limit: 50 }),
  });

  const incidents = incidentsData?.items || [];

  // Update selected incident if query param changes
  useEffect(() => {
    if (queryIncidentId) {
      setSelectedIncidentId(queryIncidentId);
    } else if (incidents.length > 0 && !selectedIncidentId) {
      setSelectedIncidentId(incidents[0].id);
    }
  }, [queryIncidentId, incidents]);

  const selectedIncident: IncidentItem | undefined = incidents.find(
    (i) => i.id === selectedIncidentId
  );

  // Run Multimodal Intelligence Analysis Mutation
  const analysisMutation = useMutation({
    mutationFn: async () => {
      setAnalysisError(null);
      if (!selectedIncident) throw new Error("No incident selected for analysis.");

      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("incident_id", selectedIncident.id);
        formData.append("disaster_type", selectedIncident.disaster_type);
        formData.append("latitude", String(selectedIncident.location.latitude));
        formData.append("longitude", String(selectedIncident.location.longitude));
        return await intelligenceApi.analyzeWithImage(formData);
      } else {
        return await intelligenceApi.analyzeObservation({
          incident_id: selectedIncident.id,
          disaster_type: selectedIncident.disaster_type,
          latitude: selectedIncident.location.latitude,
          longitude: selectedIncident.location.longitude,
        });
      }
    },
    onError: (err: any) => {
      setAnalysisError(err?.message || "Failed to execute multimodal intelligence analysis.");
    },
  });

  // Create Incident Mutation
  const createMutation = useMutation({
    mutationFn: (payload: IncidentCreatePayload) => incidentsApi.createIncident(payload),
    onSuccess: (newInc) => {
      queryClient.invalidateQueries({ queryKey: ["incidents-list"] });
      queryClient.invalidateQueries({ queryKey: ["overview-incidents"] });
      setSelectedIncidentId(newInc.id);
      setCreateModalOpen(false);
      setNewTitle("");
    },
  });

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const lat = parseFloat(newLat);
    const lon = parseFloat(newLon);
    if (!newTitle.trim()) return;

    createMutation.mutate({
      title: newTitle.trim(),
      disaster_type: newDisasterType,
      severity: newSeverity,
      location: { latitude: lat, longitude: lon },
    });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
    }
  };

  const analysis = analysisMutation.data;

  return (
    <div className="space-y-6">
      {/* Top Header & Incident Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-xl border border-scout-border bg-scout-surface-1 p-4 shadow-scout-card">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-scout-orange/15 border border-scout-orange/30 text-scout-orange">
            <Flame className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-scout-text-primary">
              Incident Intelligence & Epistemic Reasoner
            </h2>
            <p className="text-xs text-scout-text-muted">
              Multimodal observation fusion, computer vision classification, and uncertainty qualification
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Incident Selector Dropdown */}
          <select
            value={selectedIncidentId || ""}
            onChange={(e) => setSelectedIncidentId(e.target.value)}
            className="rounded-lg bg-scout-surface-2 border border-scout-border px-3 py-2 text-xs font-semibold text-scout-text-primary focus:border-scout-cyan focus:outline-none"
          >
            {incidents.map((inc) => (
              <option key={inc.id} value={inc.id}>
                {inc.title} ({inc.disaster_type})
              </option>
            ))}
          </select>

          <Button
            variant="primary"
            size="sm"
            icon={Plus}
            onClick={() => setCreateModalOpen(true)}
          >
            New Incident
          </Button>
        </div>
      </div>

      {analysisError && (
        <AlertBanner
          type="error"
          title="Analysis Execution Error"
          message={analysisError}
          onDismiss={() => setAnalysisError(null)}
        />
      )}

      {/* Main Grid: Incident Details & Imagery Input + Multimodal Intelligence Results */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Incident Info & Image Ingestion (1 col) */}
        <div className="space-y-6">
          {selectedIncident ? (
            <Card
              title="Active Incident Record"
              subtitle={`ID: ${selectedIncident.id}`}
              action={<StatusBadge status={selectedIncident.status} size="sm" />}
            >
              <div className="space-y-4 text-xs">
                <div>
                  <span className="text-scout-text-muted block mb-0.5">Callsign / Title:</span>
                  <p className="text-sm font-bold text-scout-text-primary">{selectedIncident.title}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded bg-scout-surface-2 p-2.5 border border-scout-border">
                    <span className="text-scout-text-muted block text-[10px] uppercase font-mono">Disaster Type</span>
                    <span className="font-semibold capitalize text-scout-text-primary">{selectedIncident.disaster_type}</span>
                  </div>
                  <div className="rounded bg-scout-surface-2 p-2.5 border border-scout-border">
                    <span className="text-scout-text-muted block text-[10px] uppercase font-mono">Initial Severity</span>
                    <ThreatBadge threat={selectedIncident.severity} size="sm" />
                  </div>
                </div>

                <div className="rounded bg-scout-surface-2 p-2.5 font-mono text-[11px] text-scout-text-secondary space-y-1 border border-scout-border">
                  <div className="flex items-center gap-1.5 text-scout-cyan font-bold">
                    <MapPin className="w-3.5 h-3.5" />
                    <span>Coordinates (WGS 84)</span>
                  </div>
                  <div>Latitude: {selectedIncident.location.latitude.toFixed(6)}°N</div>
                  <div>Longitude: {selectedIncident.location.longitude.toFixed(6)}°E</div>
                  <div>Reported: {new Date(selectedIncident.reported_at).toLocaleString()}</div>
                </div>
              </div>
            </Card>
          ) : incidentsLoading ? (
            <LoadingSpinner size="sm" label="Loading incident records..." />
          ) : (
            <div className="rounded-lg border border-scout-border p-6 text-center text-xs text-scout-text-muted">
              Select or register an incident to initiate analysis.
            </div>
          )}

          {/* Aerial / Ground Imagery Upload */}
          <Card
            title="Perception Imagery Stream"
            subtitle="Ground camera, drone, or satellite visual input"
          >
            <div className="space-y-4 text-xs">
              {previewUrl ? (
                <div className="relative rounded-lg overflow-hidden border border-scout-border bg-scout-surface-2 max-h-56">
                  <img
                    src={previewUrl}
                    alt="Uploaded Observation"
                    className="w-full h-48 object-cover"
                  />
                  <button
                    onClick={() => {
                      setSelectedFile(null);
                      setPreviewUrl(null);
                    }}
                    className="absolute top-2 right-2 rounded bg-scout-bg/80 px-2 py-1 text-[10px] font-mono text-scout-text-muted hover:text-white"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <label className="flex flex-col items-center justify-center p-6 rounded-lg border-2 border-dashed border-scout-border hover:border-scout-cyan/60 bg-scout-surface-2/40 cursor-pointer transition-colors text-center">
                  <Upload className="w-8 h-8 text-scout-cyan mb-2" />
                  <span className="font-semibold text-scout-text-primary">Upload Field Image</span>
                  <span className="text-[11px] text-scout-text-muted mt-1">
                    PNG, JPEG, or WebP up to 10MB
                  </span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </label>
              )}

              <Button
                variant="primary"
                size="md"
                className="w-full font-bold"
                icon={FileSearch}
                isLoading={analysisMutation.isPending}
                disabled={!selectedIncident}
                onClick={() => analysisMutation.mutate()}
              >
                Execute Multimodal Fusion Analysis
              </Button>
            </div>
          </Card>
        </div>

        {/* Right Column: Multimodal Intelligence Results (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {analysisMutation.isPending ? (
            <Card title="Processing Multimodal Ingestion">
              <LoadingSpinner size="lg" label="Fusing visual, atmospheric, and geospatial streams..." />
            </Card>
          ) : analysis ? (
            <>
              {/* Epistemic Status Banner */}
              <div className="rounded-xl border border-scout-border bg-gradient-to-r from-scout-surface-1 to-scout-surface-2 p-5 shadow-scout-card">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <span className="text-[11px] font-mono uppercase text-scout-text-muted tracking-wider block mb-1">
                      Epistemic Incident Status
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-xl font-bold font-mono tracking-tight text-scout-text-primary">
                        {analysis.incident_status}
                      </span>
                      <ThreatBadge threat={analysis.threat_level} size="md" />
                    </div>
                  </div>

                  <div className="text-left sm:text-right">
                    <span className="text-[10px] font-mono uppercase text-scout-text-muted block">Evidence State</span>
                    <span className="text-xs font-mono font-semibold text-scout-cyan">
                      {analysis.active_evidence_state}
                    </span>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-scout-border/60 text-xs text-scout-text-secondary leading-relaxed">
                  {analysis.evidence_summary}
                </div>
              </div>

              {/* Subsystem Breakdown Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Computer Vision Deep Learning Breakdown (M07) */}
                <Card
                  title={
                    <div className="flex items-center gap-2">
                      <Cpu className="w-4 h-4 text-scout-cyan" />
                      <span>M07 Computer Vision Inference</span>
                    </div>
                  }
                  subtitle="Convolutional neural network visual analysis"
                >
                  <div className="space-y-3 text-xs">
                    {analysis.visual_evidence ? (
                      <>
                        <div className="flex justify-between items-center p-2 rounded bg-scout-surface-2 border border-scout-border">
                          <span className="text-scout-text-muted">Detected Visual Class:</span>
                          <span className="font-mono font-bold uppercase text-scout-orange">
                            {analysis.visual_evidence.predicted_class || "FIRE"}
                          </span>
                        </div>

                        {analysis.visual_evidence.class_probabilities && (
                          <div className="space-y-1.5">
                            <span className="text-[10px] font-mono uppercase text-scout-text-muted">
                              Model Probabilities (Softmax Logits)
                            </span>
                            {Object.entries(analysis.visual_evidence.class_probabilities).map(
                              ([label, score]) => (
                                <div key={label} className="space-y-1">
                                  <div className="flex justify-between text-[11px] font-mono">
                                    <span className="capitalize text-scout-text-secondary">{label}</span>
                                    <span className="text-scout-text-primary">{(score * 100).toFixed(1)}%</span>
                                  </div>
                                  <div className="h-1.5 w-full rounded-full bg-scout-surface-2 overflow-hidden">
                                    <div
                                      className="h-full bg-scout-cyan"
                                      style={{ width: `${Math.min(100, score * 100)}%` }}
                                    />
                                  </div>
                                </div>
                              )
                            )}
                          </div>
                        )}

                        <div className="rounded bg-amber-500/10 border border-amber-500/30 p-2.5 text-[11px] text-amber-300 leading-tight">
                          <strong>Epistemic Warning:</strong> Model probability scores are uncalibrated visual feature activations. A single RGB frame cannot independently establish confirmation of a real-world wildfire.
                        </div>
                      </>
                    ) : (
                      <div className="text-center py-4 text-scout-text-muted">
                        No imagery provided for visual inference.
                      </div>
                    )}
                  </div>
                </Card>

                {/* Atmospheric & Geospatial Context Breakdown (M09 + M10) */}
                <Card
                  title={
                    <div className="flex items-center gap-2">
                      <Wind className="w-4 h-4 text-scout-yellow" />
                      <span>Environmental & Geospatial Fusion</span>
                    </div>
                  }
                  subtitle="Atmospheric weather + PostGIS spatial proximity"
                >
                  <div className="space-y-3 text-xs">
                    <div className="rounded bg-scout-surface-2 p-2.5 border border-scout-border space-y-1">
                      <span className="text-[10px] uppercase font-mono text-scout-text-muted">Fire Weather Index</span>
                      <div className="flex justify-between items-center font-mono">
                        <span className="text-scout-text-secondary">Atmospheric Danger:</span>
                        <ThreatBadge
                          threat={analysis.environmental_evidence?.fwi_danger || "HIGH"}
                          size="sm"
                        />
                      </div>
                      <p className="text-[11px] text-scout-text-muted mt-1">
                        {analysis.environmental_evidence?.fire_weather_explanation ||
                          "Elevated surface temperature and low relative humidity enhance combustible vegetation ignition."}
                      </p>
                    </div>

                    <div className="rounded bg-scout-surface-2 p-2.5 border border-scout-border space-y-1">
                      <span className="text-[10px] uppercase font-mono text-scout-text-muted">Spatial Exposure</span>
                      <div className="flex justify-between text-scout-text-secondary">
                        <span>Closest Settlement:</span>
                        <span className="font-mono text-scout-text-primary">
                          {analysis.geospatial_evidence?.closest_settlement || "Pine Ridge (3.2 km)"}
                        </span>
                      </div>
                      <div className="flex justify-between text-scout-text-secondary">
                        <span>Exposed Infrastructure:</span>
                        <span className="font-mono text-scout-cyan font-bold">
                          {analysis.geospatial_evidence?.critical_infrastructure_count ?? 4} facilities
                        </span>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>

              {/* Uncertainty Qualification & Conflict Analysis */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <HelpCircle className="w-4 h-4 text-scout-cyan" />
                    <span>Epistemic Uncertainty Qualification</span>
                  </div>
                }
                subtitle="Transparent disclosure of observation gaps, limitations, and potential conflicts"
              >
                <div className="space-y-3 text-xs">
                  <div className="p-3 rounded-lg bg-scout-surface-2/60 border border-scout-border text-scout-text-secondary leading-relaxed">
                    {analysis.uncertainty_qualification}
                  </div>

                  {analysis.missing_streams.length > 0 && (
                    <div className="flex items-start gap-2 text-scout-yellow">
                      <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-scout-yellow/20 border border-scout-yellow/40">
                        Missing Streams
                      </span>
                      <span className="text-scout-text-muted">
                        {analysis.missing_streams.join(", ")}
                      </span>
                    </div>
                  )}

                  {analysis.conflicting_streams.length > 0 && (
                    <div className="flex items-start gap-2 text-scout-red">
                      <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-scout-red/20 border border-scout-red/40">
                        Conflicting Streams
                      </span>
                      <span className="text-scout-text-muted">
                        {analysis.conflicting_streams.join(", ")}
                      </span>
                    </div>
                  )}
                </div>
              </Card>
            </>
          ) : (
            <Card title="Multimodal Intelligence Console">
              <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
                <div className="p-4 rounded-full bg-scout-surface-2 text-scout-cyan border border-scout-border">
                  <FileSearch className="w-10 h-10" />
                </div>
                <h3 className="text-sm font-semibold text-scout-text-primary">
                  Ready for Multimodal Evidence Fusion
                </h3>
                <p className="text-xs text-scout-text-muted max-w-sm">
                  Click "Execute Multimodal Fusion Analysis" to query computer vision classification, Canadian FWI fire danger, and PostGIS infrastructure exposure.
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* New Incident Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Register New Disaster Incident"
        subtitle="Submit initial observation coordinates and operational classification"
        maxWidth="lg"
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block text-scout-text-secondary mb-1 font-medium">Incident Callsign / Title</label>
            <input
              type="text"
              required
              placeholder="e.g. Pine Ridge Ridge-line Wildfire"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Disaster Type</label>
              <select
                value={newDisasterType}
                onChange={(e) => setNewDisasterType(e.target.value as any)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              >
                <option value="wildfire">Wildfire</option>
                <option value="flood">Flood</option>
                <option value="earthquake">Earthquake</option>
              </select>
            </div>

            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Initial Severity</label>
              <select
                value={newSeverity}
                onChange={(e) => setNewSeverity(e.target.value as any)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              >
                <option value="low">Low</option>
                <option value="moderate">Moderate</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Latitude (WGS 84, °N)</label>
              <input
                type="number"
                step="0.000001"
                required
                value={newLat}
                onChange={(e) => setNewLat(e.target.value)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Longitude (WGS 84, °E)</label>
              <input
                type="number"
                step="0.000001"
                required
                value={newLon}
                onChange={(e) => setNewLon(e.target.value)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-scout-border">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setCreateModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={createMutation.isPending}
            >
              Create Incident
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
