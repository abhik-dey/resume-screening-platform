import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "./api/health";

function StatusPill({ label, status }: { label: string; status: "ok" | "error" }) {
  const color = status === "ok" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800";
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${color}`}>
      {label}: {status}
    </span>
  );
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-bold text-slate-900">AI Resume Screening Platform</h1>
      <p className="text-slate-500">Phase 2 — Environment smoke test</p>

      {error && <p className="text-red-600">Could not reach backend: {error}</p>}

      {health && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-slate-700">
            Overall status:{" "}
            <span className="font-semibold">{health.status}</span>
          </p>
          <div className="flex gap-3">
            <StatusPill label="PostgreSQL" status={health.postgres.status} />
            <StatusPill label="Redis" status={health.redis.status} />
          </div>
        </div>
      )}
    </div>
  );
}
