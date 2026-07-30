const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface DependencyStatus {
  status: "ok" | "error";
  detail?: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  postgres: DependencyStatus;
  redis: DependencyStatus;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }
  return response.json();
}
