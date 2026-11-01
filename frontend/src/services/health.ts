import { request } from "./api-client";
import { HealthCheckResponse } from "../types";

export const healthApi = {
  checkAppHealth: () => request<HealthCheckResponse>("/health"),
  checkGeospatialHealth: () => request<HealthCheckResponse>("/geospatial/health"),
  checkEnvironmentalHealth: () => request<HealthCheckResponse>("/environmental/health"),
  checkIntelligenceHealth: () => request<HealthCheckResponse>("/intelligence/health"),
};
