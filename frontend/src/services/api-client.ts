/**
 * SCOUT Centralized API Client
 * Manages HTTP communication with FastAPI backend.
 * Uses VITE_API_BASE_URL if set, or defaults to relative '/api/v1' (proxied by Vite)
 * or direct 'http://127.0.0.1:8000/api/v1'.
 */

const getApiBase = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    return envUrl.endsWith("/api/v1") ? envUrl : `${envUrl.replace(/\/+$/, "")}/api/v1`;
  }
  // In development Vite proxies /api to http://127.0.0.1:8000
  return "/api/v1";
};

export const API_BASE = getApiBase();

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

/**
 * Storage key for the authenticated emergency reviewer identity.
 */
const REVIEWER_TOKEN_KEY = "scout_reviewer_token";

export const getStoredReviewerToken = (): string => {
  return localStorage.getItem(REVIEWER_TOKEN_KEY) || "reviewer:commander-01";
};

export const setStoredReviewerToken = (token: string): void => {
  localStorage.setItem(REVIEWER_TOKEN_KEY, token);
};

export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  // Inject Reviewer credentials for authorization
  const reviewerToken = getStoredReviewerToken();
  if (reviewerToken && !headers["Authorization"] && !headers["X-Reviewer-Token"]) {
    headers["Authorization"] = `Bearer ${reviewerToken}`;
    headers["X-Reviewer-Token"] = reviewerToken;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorData: any = null;
      try {
        errorData = await response.json();
      } catch {
        errorData = { detail: await response.text() };
      }

      const message =
        errorData?.detail?.message ||
        errorData?.detail ||
        errorData?.message ||
        `HTTP ${response.status}: ${response.statusText}`;

      throw new ApiError(message, response.status, errorData);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(
      err?.message || "Network communication failure with SCOUT backend",
      0,
      err
    );
  }
}
