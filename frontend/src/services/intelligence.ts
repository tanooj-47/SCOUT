import { request } from "./api-client";
import { MultimodalAnalysisResult } from "../types";

export interface IntelligenceAnalyzePayload {
  incident_id?: string;
  disaster_type?: string;
  latitude: number;
  longitude: number;
  media_id?: string;
  image_path?: string;
  weather_override?: Record<string, any>;
  geospatial_override?: Record<string, any>;
}

export const intelligenceApi = {
  analyzeObservation: (payload: IntelligenceAnalyzePayload) => {
    return request<MultimodalAnalysisResult>("/intelligence/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  analyzeWithImage: (formData: FormData) => {
    return request<MultimodalAnalysisResult>("/intelligence/analyze-with-image", {
      method: "POST",
      body: formData,
    });
  },

  getCapabilities: () => {
    return request<Record<string, any>>("/intelligence/capabilities");
  },
};
