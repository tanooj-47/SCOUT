import { CoordinateLocation } from "./common";

export type MediaFormat = "jpeg" | "png" | "webp";

export type MediaSourceType = 
  | "drone"
  | "satellite"
  | "field_camera"
  | "ground_team"
  | "citizen_report"
  | "sensor"
  | "other";

export interface MediaItem {
  id: string;
  incident_id?: string | null;
  storage_path: string;
  media_format: string;
  source_type: string;
  file_size_bytes: number;
  capture_location?: CoordinateLocation | null;
  captured_at?: string | null;
  created_at: string;
}
