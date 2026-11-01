import { request } from "./api-client";
import {
  IncidentItem,
  IncidentCreatePayload,
  IncidentUpdatePayload,
  PaginatedResponse,
} from "../types";

export interface IncidentFilterParams {
  skip?: number;
  limit?: number;
  disaster_type?: string;
  status?: string;
  severity?: string;
  include_archived?: boolean;
}

export const incidentsApi = {
  listIncidents: (params: IncidentFilterParams = {}) => {
    const query = new URLSearchParams();
    if (params.skip !== undefined) query.set("skip", String(params.skip));
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.disaster_type) query.set("disaster_type", params.disaster_type);
    if (params.status) query.set("status", params.status);
    if (params.severity) query.set("severity", params.severity);
    if (params.include_archived !== undefined)
      query.set("include_archived", String(params.include_archived));

    const qs = query.toString();
    return request<PaginatedResponse<IncidentItem>>(`/incidents${qs ? `?${qs}` : ""}`);
  },

  getIncidentById: (id: string) => {
    return request<IncidentItem>(`/incidents/${id}`);
  },

  createIncident: (payload: IncidentCreatePayload) => {
    return request<IncidentItem>("/incidents", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateIncident: (id: string, payload: IncidentUpdatePayload) => {
    return request<IncidentItem>(`/incidents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  archiveIncident: (id: string) => {
    return request<IncidentItem>(`/incidents/${id}/archive`, {
      method: "POST",
    });
  },
};
