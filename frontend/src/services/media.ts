import { request } from "./api-client";
import { MediaItem, PaginatedResponse } from "../types";

export const mediaApi = {
  uploadMedia: (formData: FormData) => {
    return request<MediaItem>("/media", {
      method: "POST",
      body: formData,
    });
  },

  listMedia: (incidentId?: string, limit: number = 20) => {
    const query = new URLSearchParams();
    if (incidentId) query.set("incident_id", incidentId);
    query.set("limit", String(limit));
    return request<PaginatedResponse<MediaItem>>(`/media?${query.toString()}`);
  },

  getMediaById: (mediaId: string) => {
    return request<MediaItem>(`/media/${mediaId}`);
  },
};
