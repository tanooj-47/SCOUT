import { request } from "./api-client";
import {
  PendingApprovalItem,
  WorkflowApprovalRequest,
  WorkflowApprovalResponse,
  WorkflowCreateRequest,
  WorkflowCreateResponse,
  WorkflowDetailResponse,
  WorkflowListResponse,
  ApprovalHistoryResponse,
} from "../types";

export interface WorkflowListFilterParams {
  skip?: number;
  limit?: number;
  disaster_type?: string;
  workflow_status?: string;
  approval_status?: string;
  start_date?: string;
  end_date?: string;
}

export const workflowsApi = {
  createWorkflow: (payload: WorkflowCreateRequest) => {
    return request<WorkflowCreateResponse>("/workflows", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listWorkflows: (params: WorkflowListFilterParams = {}) => {
    const query = new URLSearchParams();
    if (params.skip !== undefined) query.set("skip", String(params.skip));
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.disaster_type) query.set("disaster_type", params.disaster_type);
    if (params.workflow_status) query.set("workflow_status", params.workflow_status);
    if (params.approval_status) query.set("approval_status", params.approval_status);
    if (params.start_date) query.set("start_date", params.start_date);
    if (params.end_date) query.set("end_date", params.end_date);

    const qs = query.toString();
    return request<WorkflowListResponse>(`/workflows${qs ? `?${qs}` : ""}`);
  },

  getWorkflowById: (workflowId: string) => {
    return request<WorkflowDetailResponse>(`/workflows/${workflowId}`);
  },

  listPendingApprovals: () => {
    return request<PendingApprovalItem[]>("/workflows/pending-approvals");
  },

  submitApprovalDecision: (workflowId: string, payload: WorkflowApprovalRequest) => {
    return request<WorkflowApprovalResponse>(`/workflows/${workflowId}/approval`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getApprovalHistory: (workflowId: string) => {
    return request<ApprovalHistoryResponse>(`/workflows/${workflowId}/approval-history`);
  },
};
