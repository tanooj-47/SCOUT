export type FeatureCategory = 
  | "settlement"
  | "road"
  | "vegetation"
  | "water_body"
  | "infrastructure"
  | "administrative"
  | "other";

export type SpatialRelationship = 
  | "intersects"
  | "within_radius"
  | "adjacent"
  | "disjoint";

export interface GeoJSONGeometry {
  type: string;
  coordinates: any;
}

export interface GeographicFeatureItem {
  id: string;
  name: string;
  category: FeatureCategory;
  distance_meters: number;
  relationship: SpatialRelationship;
  source_dataset: string;
  geometry?: GeoJSONGeometry | null;
  metadata?: Record<string, any>;
  latitude?: number;
  longitude?: number;
}

export interface CoordinateValidationRequest {
  latitude: number;
  longitude: number;
}

export interface CoordinateValidationResponse {
  is_valid: boolean;
  latitude?: number | null;
  longitude?: number | null;
  srid: number;
  utm_epsg?: number | null;
  error_message?: string | null;
}

export interface GeospatialLayerItem {
  id: string;
  name: string;
  category: FeatureCategory;
  feature_count: number;
  description?: string;
  color?: string;
  visible?: boolean;
}

export interface ExternalDataSource {
  id: string;
  name: string;
  provider: string;
  category: string;
  update_frequency: string;
  spatial_resolution?: string;
  coverage: string;
  license: string;
  status: "ONLINE" | "DEGRADED" | "OFFLINE";
  description: string;
  limitations: string[];
}
