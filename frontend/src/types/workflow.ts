export type WorkflowStatus = 
  | "initialized"
  | "running"
  | "completed"
  | "failed"
  | "suspended_for_approval";

export type HumanApprovalStatus = 
  | "pending"
  | "approved"
  | "rejected"
  | "needs_revision";

export type WorkflowStage = 
  | "initialized"
  | "request_validation"
  | "request_validated"
  | "intelligence_assessment"
  | "context_interpretation"
  | "risk_assessment"
  | "response_planning"
  | "human_review_gate"
  | "coordinator_report"
  | "completed"
  | "terminated_with_error";

export type RecommendationPriority = "critical" | "high" | "medium" | "low";

export interface ActionRecommendation {
  action_id: string;
  category: string;
  title: string;
  description: string;
  priority: RecommendationPriority | string;
  intended_objective: string;
  suggested_responsible_role: string;
  suggested_resource_categories: string[];
  preconditions: string[];
  safety_constraints: string[];
  evidence_references: string[];
  confidence_description: string;
  target_infrastructure?: string | null;
  rationale: string;
  is_conditional: boolean;
  condition_description?: string | null;
  requires_human_authorization: boolean;
}

export interface AgentExecutionRecord {
  agent_name: string;
  stage: string;
  status: "success" | "failed" | "skipped" | string;
  start_time: string;
  end_time?: string | null;
  duration_seconds?: number | null;
  details?: string | null;
}

export interface WorkflowError {
  code: string;
  message: string;
  stage: string;
  agent?: string | null;
  timestamp: string;
  recoverable: boolean;
}

export interface PendingApprovalItem {
  workflow_id: string;
  plan_id: string;
  disaster_type: string;
  location: { latitude: number; longitude: number };
  threat_level: string;
  incident_status: string;
  approval_status: HumanApprovalStatus | string;
  recommendations_count: number;
  requires_approval: boolean;
  created_at: string;
}

export interface WorkflowSummaryItem {
  workflow_id: string;
  request_id: string;
  disaster_type: string;
  workflow_status: WorkflowStatus | string;
  workflow_stage: WorkflowStage | string;
  approval_status: HumanApprovalStatus | string;
  latitude: number;
  longitude: number;
  search_radius_meters: number;
  version: number;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface WorkflowListResponse {
  total: number;
  skip: number;
  limit: number;
  items: WorkflowSummaryItem[];
}

export interface WorkflowDetailResponse {
  workflow_id: string;
  request_id: string;
  disaster_type: string;
  workflow_status: WorkflowStatus | string;
  workflow_stage: WorkflowStage | string;
  location: { latitude: number; longitude: number };
  search_radius_meters: number;
  source_description?: string | null;
  approval_status: HumanApprovalStatus | string;
  version: number;
  intelligence_assessment?: Record<string, any> | null;
  weather_interpretation?: Record<string, any> | null;
  geospatial_context?: Record<string, any> | null;
  risk_assessment?: {
    assessment_status?: string;
    incident_status?: string;
    incident_severity?: string;
    fire_weather_danger?: string;
    geographic_exposure_status?: string;
    potential_consequences_status?: string;
    overall_threat_level?: string;
    heuristic_risk_index?: number;
    hazard_summary?: string;
    exposure_summary?: string;
    consequence_summary?: string;
    fire_weather_summary?: string;
    supporting_evidence?: string[];
    missing_evidence?: string[];
    conflicting_evidence?: string[];
    uncertainty_qualification?: string;
    assessment_rationale?: string;
    key_risk_drivers?: string[];
    mitigating_factors?: string[];
    source_agent_provenance?: Record<string, any>;
    generated_at?: string;
  } | null;
  response_plan?: {
    plan_id?: string;
    disaster_type?: string;
    incident_status?: string;
    assessed_threat_level?: string;
    overall_plan_status?: string;
    recommendations?: ActionRecommendation[];
    suggested_resource_categories?: string[];
    safety_precautions?: string[];
    missing_information?: string[];
    operational_limitations?: string[];
    life_safety_notes?: string[];
    responder_information_gaps?: string[];
    evacuation_alert_guidance?: string | null;
    human_approval_status?: string;
  } | null;
  coordinator_report?: {
    report_id?: string;
    executive_summary?: string;
    incident_status?: string;
    incident_severity?: string;
    composite_threat_level?: string;
    weather_summary?: string;
    exposure_summary?: string;
    recommendations_summary?: string[];
    human_decisions_required?: string[];
    unresolved_uncertainties?: string[];
    audit_trail?: Record<string, any>;
    generated_at?: string;
  } | null;
  execution_records: AgentExecutionRecord[];
  errors: WorkflowError[];
  warnings: string[];
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface WorkflowCreateRequest {
  request_id?: string;
  disaster_type?: string;
  latitude: number;
  longitude: number;
  search_radius_meters?: number;
  image_path?: string | null;
  source_description?: string;
  metadata?: Record<string, any>;
}

export interface WorkflowCreateResponse {
  workflow_id: string;
  request_id: string;
  disaster_type: string;
  status: WorkflowStatus | string;
  stage: WorkflowStage | string;
  location: { latitude: number; longitude: number };
  search_radius_meters: number;
  approval_status: string;
  execution_records_count: number;
  has_coordinator_report: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowApprovalRequest {
  decision: HumanApprovalStatus;
  reviewer_comments?: string | null;
  rejection_or_revision_reason?: string | null;
}

export interface WorkflowApprovalResponse {
  workflow_id: string;
  plan_id: string;
  previous_status: string;
  new_status: string;
  workflow_status: string;
  reviewer_id: string;
  reviewer_comments?: string | null;
  rejection_or_revision_reason?: string | null;
  decided_at: string;
}

export interface ApprovalHistoryItem {
  id: string;
  workflow_id: string;
  plan_id: string;
  previous_status: string;
  new_status: string;
  reviewer_id: string;
  reviewer_comments?: string | null;
  rejection_or_revision_reason?: string | null;
  decision_type?: string | null;
  created_at: string;
}

export interface ApprovalHistoryResponse {
  workflow_id: string;
  total_decisions: number;
  history: ApprovalHistoryItem[];
}
