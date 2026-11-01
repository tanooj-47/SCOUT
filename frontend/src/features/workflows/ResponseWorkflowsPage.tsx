import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  GitPullRequest,
  Plus,
  Clock,
  ShieldCheck,
  ShieldAlert,
  CheckCircle,
  XCircle,
  RotateCcw,
  FileText,
  User,
  History,
  AlertTriangle,
  Play,
} from "lucide-react";
import { workflowsApi } from "../../services";
import { Card } from "../../components/common/Card";
import { StatusBadge } from "../../components/common/StatusBadge";
import { ThreatBadge } from "../../components/common/ThreatBadge";
import { Button } from "../../components/common/Button";
import { Modal } from "../../components/common/Modal";
import { LoadingSpinner } from "../../components/common/LoadingSpinner";
import { AlertBanner } from "../../components/common/AlertBanner";
import {
  WorkflowCreateRequest,
  WorkflowApprovalRequest,
  HumanApprovalStatus,
  ActionRecommendation,
} from "../../types";

export const ResponseWorkflowsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const initialId = searchParams.get("id");

  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(initialId);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);

  // Filter state
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterApproval, setFilterApproval] = useState<string>("all");

  // Create workflow form state
  const [createLat, setCreateLat] = useState("37.7749");
  const [createLon, setCreateLon] = useState("-122.4194");
  const [createRadius, setCreateRadius] = useState("5000");
  const [createDisaster, setCreateDisaster] = useState("wildfire");
  const [createSource, setCreateSource] = useState("Incident Command Dispatch");

  // Approval action form state
  const [selectedDecision, setSelectedDecision] = useState<HumanApprovalStatus>("approved");
  const [reviewerComments, setReviewerComments] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);

  // Query Workflows List
  const { data: workflowsData, isLoading: listLoading } = useQuery({
    queryKey: ["workflows-list", filterStatus, filterApproval],
    queryFn: () =>
      workflowsApi.listWorkflows({
        workflow_status: filterStatus !== "all" ? filterStatus : undefined,
        approval_status: filterApproval !== "all" ? filterApproval : undefined,
        limit: 50,
      }),
    refetchInterval: 10000,
  });

  const workflows = workflowsData?.items || [];

  // Default selection to first workflow if none selected
  const activeId = selectedWorkflowId || (workflows.length > 0 ? workflows[0].workflow_id : null);

  // Query Selected Workflow Details
  const { data: workflowDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["workflow-detail", activeId],
    queryFn: () => workflowsApi.getWorkflowById(activeId!),
    enabled: !!activeId,
    refetchInterval: 8000,
  });

  // Query Approval History for active workflow
  const { data: approvalHistoryData } = useQuery({
    queryKey: ["workflow-history", activeId],
    queryFn: () => workflowsApi.getApprovalHistory(activeId!),
    enabled: !!activeId && historyModalOpen,
  });

  // Create Workflow Mutation
  const createMutation = useMutation({
    mutationFn: (payload: WorkflowCreateRequest) => workflowsApi.createWorkflow(payload),
    onSuccess: (newWf) => {
      queryClient.invalidateQueries({ queryKey: ["workflows-list"] });
      queryClient.invalidateQueries({ queryKey: ["overview-workflows"] });
      queryClient.invalidateQueries({ queryKey: ["pending-approvals-count"] });
      setSelectedWorkflowId(newWf.workflow_id);
      setCreateModalOpen(false);
    },
  });

  // Submit Approval Decision Mutation
  const approvalMutation = useMutation({
    mutationFn: (payload: WorkflowApprovalRequest) => {
      if (!activeId) throw new Error("No active workflow selected.");
      return workflowsApi.submitApprovalDecision(activeId, payload);
    },
    onSuccess: () => {
      setDecisionError(null);
      setReviewerComments("");
      setRejectionReason("");
      queryClient.invalidateQueries({ queryKey: ["workflow-detail", activeId] });
      queryClient.invalidateQueries({ queryKey: ["workflows-list"] });
      queryClient.invalidateQueries({ queryKey: ["pending-approvals-count"] });
    },
    onError: (err: any) => {
      setDecisionError(err?.message || "Failed to submit approval decision.");
    },
  });

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      latitude: parseFloat(createLat),
      longitude: parseFloat(createLon),
      search_radius_meters: parseFloat(createRadius),
      disaster_type: createDisaster,
      source_description: createSource,
    });
  };

  const handleDecisionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setDecisionError(null);

    // Enforce mandatory reason for rejection or revision request
    if (
      (selectedDecision === "rejected" || selectedDecision === "needs_revision") &&
      !rejectionReason.trim()
    ) {
      setDecisionError(
        `A written explanation is mandatory when submitting a '${selectedDecision.toUpperCase()}' decision.`
      );
      return;
    }

    approvalMutation.mutate({
      decision: selectedDecision,
      reviewer_comments: reviewerComments.trim() || undefined,
      rejection_or_revision_reason: rejectionReason.trim() || undefined,
    });
  };

  const stages = [
    { key: "request_validation", name: "1. Validation" },
    { key: "intelligence_assessment", name: "2. Intelligence" },
    { key: "weather_agent", name: "3. Weather" },
    { key: "geospatial_agent", name: "4. Geospatial" },
    { key: "risk_assessment", name: "5. Risk Assessment" },
    { key: "response_planning", name: "6. Response Plan" },
    { key: "human_review_gate", name: "7. Approval Gate" },
  ];

  const recommendations: ActionRecommendation[] =
    workflowDetail?.response_plan?.recommendations || [];

  return (
    <div className="space-y-6">
      {/* Header Controller Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-xl border border-scout-border bg-scout-surface-1 p-5 shadow-scout-card">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-scout-cyan/15 border border-scout-cyan/30 text-scout-cyan">
            <GitPullRequest className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-scout-text-primary">
              Multi-Agent Disaster Response Workflows
            </h1>
            <p className="text-xs text-scout-text-muted">
              LangGraph multi-agent orchestration, evidence-grounded action plans, and authorized human approval gate
            </p>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          icon={Plus}
          onClick={() => setCreateModalOpen(true)}
        >
          Initiate New Workflow
        </Button>
      </div>

      {/* Main Grid: Workflows Table + Selected Workflow Console */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left Column: Workflows Filter & List (1 col) */}
        <div className="space-y-4">
          <Card
            title="Active & Past Workflows"
            subtitle={`${workflows.length} total workflow runs`}
          >
            {/* Filter Controls */}
            <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="rounded bg-scout-surface-2 border border-scout-border px-2 py-1 text-scout-text-primary text-[11px] focus:border-scout-cyan focus:outline-none"
              >
                <option value="all">All Statuses</option>
                <option value="suspended_for_approval">Suspended (Gate)</option>
                <option value="completed">Completed</option>
                <option value="running">Running</option>
                <option value="failed">Failed</option>
              </select>

              <select
                value={filterApproval}
                onChange={(e) => setFilterApproval(e.target.value)}
                className="rounded bg-scout-surface-2 border border-scout-border px-2 py-1 text-scout-text-primary text-[11px] focus:border-scout-cyan focus:outline-none"
              >
                <option value="all">All Approvals</option>
                <option value="pending">Pending Review</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="needs_revision">Needs Revision</option>
              </select>
            </div>

            {/* Workflows List Table */}
            {listLoading ? (
              <LoadingSpinner size="sm" label="Loading workflows..." />
            ) : workflows.length === 0 ? (
              <div className="py-8 text-center text-xs text-scout-text-muted">
                No workflows match the specified criteria.
              </div>
            ) : (
              <div className="max-h-[600px] overflow-y-auto divide-y divide-scout-border/60">
                {workflows.map((wf) => {
                  const isSelected = wf.workflow_id === activeId;
                  const isPendingGate = wf.approval_status === "pending";

                  return (
                    <div
                      key={wf.workflow_id}
                      onClick={() => setSelectedWorkflowId(wf.workflow_id)}
                      className={`p-3 rounded-lg cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-scout-surface-2 border border-scout-cyan/40"
                          : "hover:bg-scout-surface-2/40"
                      } ${isPendingGate ? "border-l-4 border-l-scout-orange" : ""}`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-xs font-bold text-scout-text-primary">
                          {wf.workflow_id.slice(0, 16)}...
                        </span>
                        <StatusBadge status={wf.approval_status} size="sm" />
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-scout-text-muted font-mono">
                        <span>{wf.latitude.toFixed(2)}°N, {wf.longitude.toFixed(2)}°E</span>
                        <span>{new Date(wf.created_at).toLocaleTimeString()}</span>
                      </div>
                      <div className="mt-1 text-[10px] text-scout-text-secondary capitalize">
                        Stage: <span className="font-mono text-scout-cyan">{wf.workflow_stage}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Workflow Detail & Human Approval Gate (2 cols) */}
        <div className="xl:col-span-2 space-y-6">
          {detailLoading ? (
            <Card title="Loading Workflow Details">
              <LoadingSpinner size="lg" label="Retrieving agent state and execution log..." />
            </Card>
          ) : workflowDetail ? (
            <>
              {/* Workflow Execution Stage Pipeline */}
              <Card
                title={
                  <div className="flex items-center justify-between w-full">
                    <span>Multi-Agent Execution Pipeline</span>
                    <button
                      onClick={() => setHistoryModalOpen(true)}
                      className="flex items-center gap-1.5 text-xs font-normal text-scout-cyan hover:underline"
                    >
                      <History className="w-3.5 h-3.5" />
                      <span>Audit Trail</span>
                    </button>
                  </div>
                }
                subtitle={`Workflow ID: ${workflowDetail.workflow_id} • Status: ${workflowDetail.workflow_status.toUpperCase()}`}
              >
                <div className="space-y-4">
                  {/* Stages Progress Track */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 text-center text-xs">
                    {stages.map((st, idx) => {
                      const execRecord = workflowDetail.execution_records?.find(
                        (r) => r.stage.toLowerCase() === st.key.toLowerCase() || r.agent_name.toLowerCase().includes(st.key.split("_")[0])
                      );
                      const isComplete = !!execRecord && execRecord.status === "success";

                      return (
                        <div
                          key={st.key}
                          className={`p-2.5 rounded-lg border text-[11px] flex flex-col items-center justify-between ${
                            isComplete
                              ? "bg-scout-cyan/10 border-scout-cyan/40 text-scout-cyan"
                              : "bg-scout-surface-2/40 border-scout-border text-scout-text-muted"
                          }`}
                        >
                          <span className="font-semibold block mb-1">{st.name}</span>
                          {isComplete ? (
                            <CheckCircle className="w-4 h-4 text-scout-cyan" />
                          ) : (
                            <Clock className="w-4 h-4 text-scout-text-muted" />
                          )}
                          <span className="text-[9px] font-mono mt-1 text-scout-text-muted">
                            {execRecord?.duration_seconds ? `${execRecord.duration_seconds.toFixed(2)}s` : `Node ${idx + 1}`}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex flex-wrap items-center justify-between p-3 rounded-lg bg-scout-surface-2 border border-scout-border text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-scout-text-muted">Approval State:</span>
                      <StatusBadge status={workflowDetail.approval_status} size="sm" />
                    </div>
                    <div className="font-mono text-scout-text-muted text-[11px]">
                      Coordinates: {workflowDetail.location.latitude.toFixed(4)}°N, {workflowDetail.location.longitude.toFixed(4)}°E (Radius: {workflowDetail.search_radius_meters}m)
                    </div>
                  </div>
                </div>
              </Card>

              {/* HUMAN APPROVAL GATE INTERFACE */}
              <div className="rounded-xl border border-scout-border bg-gradient-to-r from-scout-surface-1 to-scout-surface-2 p-5 shadow-scout-card">
                <div className="flex items-center justify-between border-b border-scout-border/60 pb-3 mb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded bg-scout-orange/20 text-scout-orange">
                      <ShieldAlert className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-scout-text-primary tracking-wide">
                        Human Approval Decision Gate (M12.4 / M12.5)
                      </h3>
                      <p className="text-[11px] text-scout-text-muted">
                        Authorized Incident Commander review gate. Explicit approval required for response recommendations.
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={workflowDetail.approval_status} size="md" />
                </div>

                {decisionError && (
                  <div className="mb-4">
                    <AlertBanner
                      type="error"
                      title="Decision Validation Error"
                      message={decisionError}
                      onDismiss={() => setDecisionError(null)}
                    />
                  </div>
                )}

                {/* Gate Decision Form */}
                <form onSubmit={handleDecisionSubmit} className="space-y-4 text-xs">
                  {/* Decision Options */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <label
                      className={`flex items-center gap-2.5 p-3 rounded-lg border cursor-pointer transition-all ${
                        selectedDecision === "approved"
                          ? "bg-scout-green/15 border-scout-green/50 text-scout-green font-bold shadow-sm"
                          : "bg-scout-surface-2 border-scout-border text-scout-text-secondary hover:bg-scout-surface-3"
                      }`}
                    >
                      <input
                        type="radio"
                        name="approval-decision"
                        value="approved"
                        checked={selectedDecision === "approved"}
                        onChange={() => setSelectedDecision("approved")}
                        className="hidden"
                      />
                      <CheckCircle className="w-4 h-4" />
                      <span>Approve Plan</span>
                    </label>

                    <label
                      className={`flex items-center gap-2.5 p-3 rounded-lg border cursor-pointer transition-all ${
                        selectedDecision === "rejected"
                          ? "bg-scout-red/15 border-scout-red/50 text-scout-red font-bold shadow-sm"
                          : "bg-scout-surface-2 border-scout-border text-scout-text-secondary hover:bg-scout-surface-3"
                      }`}
                    >
                      <input
                        type="radio"
                        name="approval-decision"
                        value="rejected"
                        checked={selectedDecision === "rejected"}
                        onChange={() => setSelectedDecision("rejected")}
                        className="hidden"
                      />
                      <XCircle className="w-4 h-4" />
                      <span>Reject Plan</span>
                    </label>

                    <label
                      className={`flex items-center gap-2.5 p-3 rounded-lg border cursor-pointer transition-all ${
                        selectedDecision === "needs_revision"
                          ? "bg-scout-orange/15 border-scout-orange/50 text-scout-orange font-bold shadow-sm"
                          : "bg-scout-surface-2 border-scout-border text-scout-text-secondary hover:bg-scout-surface-3"
                      }`}
                    >
                      <input
                        type="radio"
                        name="approval-decision"
                        value="needs_revision"
                        checked={selectedDecision === "needs_revision"}
                        onChange={() => setSelectedDecision("needs_revision")}
                        className="hidden"
                      />
                      <RotateCcw className="w-4 h-4" />
                      <span>Request Revision</span>
                    </label>
                  </div>

                  {/* Mandatory Rejection / Revision Reason Box */}
                  {(selectedDecision === "rejected" || selectedDecision === "needs_revision") && (
                    <div className="rounded-lg bg-scout-red/10 border border-scout-red/30 p-3 space-y-1.5 animate-in fade-in duration-150">
                      <label className="block text-scout-red font-semibold">
                        Mandatory Written Justification Reason *
                      </label>
                      <p className="text-[10px] text-scout-text-muted">
                        Explain why this advisory response plan is rejected or which agent recommendations require operational revision.
                      </p>
                      <textarea
                        required
                        rows={3}
                        value={rejectionReason}
                        onChange={(e) => setRejectionReason(e.target.value)}
                        placeholder="Provide formal operational justification..."
                        className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-red focus:outline-none"
                      />
                    </div>
                  )}

                  {/* Optional Reviewer Notes */}
                  <div>
                    <label className="block text-scout-text-secondary mb-1">
                      Commander Operational Notes (Optional)
                    </label>
                    <input
                      type="text"
                      value={reviewerComments}
                      onChange={(e) => setReviewerComments(e.target.value)}
                      placeholder="e.g. Coordinated with county mutual-aid dispatch..."
                      className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
                    />
                  </div>

                  {/* Safety Policy Notice & Submit Button */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
                    <p className="text-[10px] text-scout-text-muted max-w-md">
                      <strong>Policy:</strong> Approving records the commander decision in the immutable audit log. It does <em>not</em> trigger sirens or dispatch live vehicles automatically.
                    </p>
                    <Button
                      type="submit"
                      variant={
                        selectedDecision === "approved"
                          ? "primary"
                          : selectedDecision === "rejected"
                          ? "danger"
                          : "warning"
                      }
                      size="sm"
                      isLoading={approvalMutation.isPending}
                      icon={ShieldCheck}
                      className="whitespace-nowrap font-bold"
                    >
                      Submit Review Decision
                    </Button>
                  </div>
                </form>
              </div>

              {/* Evidence-Grounded Action Recommendations */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-scout-cyan" />
                    <span>Evidence-Grounded Action Recommendations ({recommendations.length})</span>
                  </div>
                }
                subtitle="Synthesized by Agent 5 (Response Planning Agent)"
              >
                {recommendations.length === 0 ? (
                  <div className="py-8 text-center text-xs text-scout-text-muted">
                    No recommendations produced yet for this workflow execution.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {recommendations.map((rec) => (
                      <div
                        key={rec.action_id}
                        className="p-4 rounded-lg bg-scout-surface-2/60 border border-scout-border text-xs space-y-2"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-scout-border/60 pb-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-scout-text-primary text-sm">
                              {rec.title}
                            </span>
                            <ThreatBadge threat={rec.priority} size="sm" />
                          </div>
                          <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded bg-scout-surface-3 text-scout-cyan">
                            {rec.category}
                          </span>
                        </div>

                        <p className="text-scout-text-secondary leading-relaxed">
                          {rec.description}
                        </p>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] pt-1">
                          <div className="rounded bg-scout-surface-1 p-2 border border-scout-border">
                            <span className="text-scout-text-muted block text-[10px] uppercase font-mono">Suggested ICS Role</span>
                            <span className="font-semibold text-scout-text-primary">{rec.suggested_responsible_role}</span>
                          </div>
                          <div className="rounded bg-scout-surface-1 p-2 border border-scout-border">
                            <span className="text-scout-text-muted block text-[10px] uppercase font-mono">Confidence Level</span>
                            <span className="font-mono text-scout-cyan">{rec.confidence_description}</span>
                          </div>
                        </div>

                        {rec.safety_constraints.length > 0 && (
                          <div className="flex items-start gap-1.5 text-scout-orange text-[11px]">
                            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                            <span>Safety: {rec.safety_constraints.join("; ")}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </>
          ) : (
            <div className="rounded-lg border border-scout-border p-12 text-center text-xs text-scout-text-muted">
              Select a workflow from the list to inspect execution state and review recommendations.
            </div>
          )}
        </div>
      </div>

      {/* New Workflow Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Initiate Multi-Agent Disaster Response Workflow"
        subtitle="Submits an observation request to the 7-stage LangGraph pipeline"
        maxWidth="lg"
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Latitude (WGS 84, °N)</label>
              <input
                type="number"
                step="0.000001"
                required
                value={createLat}
                onChange={(e) => setCreateLat(e.target.value)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Longitude (WGS 84, °E)</label>
              <input
                type="number"
                step="0.000001"
                required
                value={createLon}
                onChange={(e) => setCreateLon(e.target.value)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Search Radius (Meters)</label>
              <input
                type="number"
                step="100"
                min="100"
                max="100000"
                required
                value={createRadius}
                onChange={(e) => setCreateRadius(e.target.value)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 font-mono text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-scout-text-secondary mb-1 font-medium">Disaster Hazard Category</label>
              <select
                value={createDisaster}
                onChange={(e) => setCreateDisaster(e.target.value)}
                className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
              >
                <option value="wildfire">Wildfire (Pilot Hazard)</option>
                <option value="flood">Flood</option>
                <option value="earthquake">Earthquake</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-scout-text-secondary mb-1 font-medium">Reporting Platform Description</label>
            <input
              type="text"
              required
              value={createSource}
              onChange={(e) => setCreateSource(e.target.value)}
              className="w-full rounded bg-scout-surface-2 border border-scout-border px-3 py-2 text-scout-text-primary focus:border-scout-cyan focus:outline-none"
            />
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
              icon={Play}
              isLoading={createMutation.isPending}
            >
              Launch Pipeline
            </Button>
          </div>
        </form>
      </Modal>

      {/* Audit History Modal */}
      <Modal
        isOpen={historyModalOpen}
        onClose={() => setHistoryModalOpen(false)}
        title="Approval Decision Audit History"
        subtitle={`Chronological review actions for workflow: ${activeId?.slice(0, 16)}...`}
        maxWidth="xl"
      >
        <div className="space-y-3 text-xs">
          {!approvalHistoryData || approvalHistoryData.history.length === 0 ? (
            <div className="py-8 text-center text-scout-text-muted">
              No historical review actions recorded yet for this workflow.
            </div>
          ) : (
            <div className="divide-y divide-scout-border/60">
              {approvalHistoryData.history.map((item) => (
                <div key={item.id} className="py-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <User className="w-3.5 h-3.5 text-scout-cyan" />
                      <span className="font-bold text-scout-text-primary font-mono">{item.reviewer_id}</span>
                    </div>
                    <span className="text-[10px] font-mono text-scout-text-muted">
                      {new Date(item.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[11px]">
                    <span className="text-scout-text-muted">{item.previous_status}</span>
                    <span className="text-scout-cyan">→</span>
                    <StatusBadge status={item.new_status} size="sm" />
                  </div>
                  {item.rejection_or_revision_reason && (
                    <p className="text-scout-red text-[11px] bg-scout-red/10 p-2 rounded border border-scout-red/20 mt-1">
                      <strong>Reason:</strong> {item.rejection_or_revision_reason}
                    </p>
                  )}
                  {item.reviewer_comments && (
                    <p className="text-scout-text-secondary text-[11px] bg-scout-surface-2 p-2 rounded mt-1">
                      <strong>Comments:</strong> {item.reviewer_comments}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};
