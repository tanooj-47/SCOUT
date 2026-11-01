export interface PaginatedResponse<T> {
  total: number;
  skip: number;
  limit: number;
  items: T[];
}

export interface CoordinateLocation {
  latitude: number;
  longitude: number;
  srid?: number;
}

export interface HealthCheckResponse {
  status: string;
  subsystem?: string;
  timestamp?: string;
  details?: Record<string, any>;
  version?: string;
  environment?: string;
}
