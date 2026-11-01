import { request } from "./api-client";
import {
  CoordinateValidationRequest,
  CoordinateValidationResponse,
  GeographicFeatureItem,
  GeospatialLayerItem,
  ExternalDataSource,
} from "../types";

export interface NearbyQueryParams {
  latitude: number;
  longitude: number;
  radius_meters?: number;
  limit?: number;
  category?: string;
}

export const geospatialApi = {
  validateCoordinate: (payload: CoordinateValidationRequest) => {
    return request<CoordinateValidationResponse>("/geospatial/validate-coordinate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getNearbyFeatures: (params: NearbyQueryParams) => {
    const query = new URLSearchParams();
    query.set("latitude", String(params.latitude));
    query.set("longitude", String(params.longitude));
    if (params.radius_meters) query.set("radius_meters", String(params.radius_meters));
    if (params.limit) query.set("limit", String(params.limit));
    if (params.category) query.set("category", params.category);

    return request<GeographicFeatureItem[]>(`/geospatial/nearby?${query.toString()}`);
  },

  getLayers: () => {
    return request<GeospatialLayerItem[]>("/geospatial/layers");
  },

  getDataSources: () => {
    return request<ExternalDataSource[]>("/geospatial/sources");
  },

  analyzeExposure: (payload: {
    latitude: number;
    longitude: number;
    radius_meters?: number;
    disaster_type?: string;
  }) => {
    return request<Record<string, any>>("/geospatial/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getIncidentExposure: (incidentId: string, radiusMeters: number = 5000) => {
    return request<Record<string, any>>(
      `/geospatial/incidents/${incidentId}/exposure?radius_meters=${radiusMeters}`
    );
  },
};
