import { CoordinateLocation } from "./common";

export type DisasterType = "wildfire" | "flood" | "earthquake";

export type IncidentStatus = 
  | "reported"
  | "investigating"
  | "active"
  | "contained"
  | "resolved"
  | "false_alarm";

export type IncidentSeverity = "low" | "moderate" | "high" | "critical";

export interface IncidentSummaryCounts {
  media_count: number;
  observations_count: number;
  predictions_count: number;
}

export interface IncidentItem {
  id: string;
  disaster_type: DisasterType;
  title: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  location: CoordinateLocation;
  observed_perimeter?: Record<string, any> | null;
  perimeter_updated_at?: string | null;
  reported_at: string;
  updated_at: string;
  contained_at?: string | null;
  is_archived: boolean;
  archived_at?: string | null;
  metadata?: Record<string, any>;
  summary_counts?: IncidentSummaryCounts;
}

export interface IncidentCreatePayload {
  title: string;
  disaster_type: DisasterType;
  severity?: IncidentSeverity;
  location: {
    latitude: number;
    longitude: number;
  };
  metadata?: Record<string, any>;
}

export interface IncidentUpdatePayload {
  title?: string;
  status?: IncidentStatus;
  severity?: IncidentSeverity;
  location?: {
    latitude: number;
    longitude: number;
  };
  metadata?: Record<string, any>;
}
