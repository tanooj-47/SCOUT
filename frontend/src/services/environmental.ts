import { request } from "./api-client";
import {
  EnvironmentalObservationItem,
  FWICalculationResult,
} from "../types";

export interface WeatherQueryParams {
  latitude: number;
  longitude: number;
  provider?: string;
}

export const environmentalApi = {
  getCurrentWeather: (params: WeatherQueryParams) => {
    const query = new URLSearchParams();
    query.set("latitude", String(params.latitude));
    query.set("longitude", String(params.longitude));
    if (params.provider) query.set("provider", params.provider);

    return request<EnvironmentalObservationItem>(`/environmental/current?${query.toString()}`);
  },

  calculateFWI: (payload: {
    temperature_c: number;
    relative_humidity_pct: number;
    wind_speed_kmh: number;
    precipitation_mm: number;
    month?: number;
    prev_ffmc?: number;
    prev_dmc?: number;
    prev_dc?: number;
  }) => {
    return request<FWICalculationResult>("/environmental/fwi/calculate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getForecast: (params: WeatherQueryParams & { days?: number }) => {
    const query = new URLSearchParams();
    query.set("latitude", String(params.latitude));
    query.set("longitude", String(params.longitude));
    if (params.provider) query.set("provider", params.provider);
    if (params.days) query.set("days", String(params.days));

    return request<Record<string, any>>(`/environmental/forecast?${query.toString()}`);
  },
};
