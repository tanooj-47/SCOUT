export interface CanonicalWeatherVariables {
  temperature_celsius?: number | null;
  relative_humidity?: number | null;
  wind_speed_mps?: number | null;
  wind_direction_degrees?: number | null;
  precipitation_mm?: number | null;
  surface_pressure_hpa?: number | null;
}

export interface ModelRunProvenance {
  provider: string;
  dataset_or_model: string;
  init_time_utc?: string | null;
  lead_time_hours?: number | null;
  retrieved_at_utc: string;
  algorithm_name?: string | null;
  algorithm_version?: string | null;
  source_fingerprint?: string | null;
}

export interface FWICalculationResult {
  ffmc: number;
  dmc: number;
  dc: number;
  isi: number;
  bui: number;
  fwi: number;
  danger_rating: "LOW" | "MODERATE" | "HIGH" | "VERY_HIGH" | "EXTREME";
  explanation?: string;
  is_experimental: boolean;
}

export interface EnvironmentalObservationItem {
  id?: string;
  location_type?: string;
  latitude: number;
  longitude: number;
  variables: CanonicalWeatherVariables;
  provenance: ModelRunProvenance;
  observed_at: string;
  fwi_indices?: FWICalculationResult | null;
}
