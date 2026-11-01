import { DisasterType } from "./incident";

export type ThreatLevel = 
  | "LOW"
  | "MODERATE"
  | "HIGH"
  | "CRITICAL"
  | "INSUFFICIENT_DATA";

export type EpistemicIncidentStatus = 
  | "CONFIRMED"
  | "SUSPECTED"
  | "UNCONFIRMED"
  | "INSUFFICIENT_EVIDENCE";

export interface EvidenceQuality {
  is_stale: boolean;
  age_seconds?: number | null;
  has_confidence_measure: boolean;
  confidence_scale?: string | null;
  provider_type: string;
}

export interface EvidenceItem {
  id: string;
  category: string;
  source_name: string;
  status: string;
  observation_timestamp?: string | null;
  data_payload: Record<string, any>;
  quality: EvidenceQuality;
  limitations: string[];
}

export interface MultimodalAnalysisResult {
  assessment_id: string;
  disaster_type: DisasterType;
  incident_status: EpistemicIncidentStatus;
  threat_level: ThreatLevel;
  confidence_score?: number | null;
  active_evidence_state: string;
  evidence_summary: string;
  visual_evidence?: {
    model_name?: string;
    class_probabilities?: Record<string, number>;
    predicted_class?: string;
    uncalibrated_score?: number;
    uncertainty_notes?: string;
  } | null;
  environmental_evidence?: {
    temperature_c?: number;
    relative_humidity?: number;
    wind_speed_mps?: number;
    fwi_danger?: string;
    fire_weather_explanation?: string;
  } | null;
  geospatial_evidence?: {
    features_found?: number;
    closest_settlement?: string;
    closest_distance_m?: number;
    critical_infrastructure_count?: number;
    exposure_level?: string;
  } | null;
  conflicting_streams: string[];
  missing_streams: string[];
  uncertainty_qualification: string;
  potential_consequences: string;
  created_at: string;
}
