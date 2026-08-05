import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { createJob, listJobs } from "../api/endpoints";
import type { Job } from "../api/types";
import { useCanEdit } from "../auth/AuthContext";
import { StatusPill } from "../components/Recommendation";
import { Button, Card, EmptyState, ErrorBanner, Field, inputClass, Spinner } from "../components/ui";

export function JobsPage() {
  const canEdit = useCanEdit();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    listJobs()
      .then(setJobs)
      .catch((cause) => setError(cause.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Jobs</h1>
          <p className="text-sm text-ink-soft mt-0.5">
            Each job holds its own candidates, scores, and reports.
          </p>
        </div>
        {canEdit && (
          <Button variant="primary" onClick={() => setCreating(!creating)}>
            {creating ? "Cancel" : "New job"}
          </Button>
        )}
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {creating && (
        <NewJobForm
          onCreated={() => { setCreating(false); load(); }}
          onError={setError}
        />
      )}

      {loading ? (
        <Card className="p-8 flex justify-center"><Spinner label="Loading jobs" /></Card>
      ) : jobs.length === 0 ? (
        <Card>
          <EmptyState
            title="No jobs yet"
            hint="Create a job to start collecting and screening candidates against it."
            action={canEdit ? <Button variant="primary" onClick={() => setCreating(true)}>New job</Button> : undefined}
          />
        </Card>
      ) : (
        <div className="grid gap-3">
          {jobs.map((job) => (
            <Link key={job.id} to={`/jobs/${job.id}`}
              className="block bg-surface border border-line rounded-card p-4 hover:border-accent transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-medium text-ink">{job.title}</h3>
                  <p className="text-sm text-ink-soft mt-0.5 line-clamp-1">{job.description}</p>
                  {job.required_skills.length > 0 && (
                    <p className="text-xs text-ink-faint mt-2">
                      Requires {job.required_skills.join(", ")}
                    </p>
                  )}
                </div>
                <StatusPill status={job.status} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function NewJobForm({ onCreated, onError }: { onCreated: () => void; onError: (m: string) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [requiredSkills, setRequiredSkills] = useState("");
  const [minExperience, setMinExperience] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await createJob({
        title,
        description,
        required_skills: requiredSkills.split(",").map((s) => s.trim()).filter(Boolean),
        min_experience_years: minExperience ? Number(minExperience) : null,
        status: "open",
      });
      onCreated();
    } catch (cause) {
      onError(cause instanceof Error ? cause.message : "Couldn't create the job");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Title">
          <input className={inputClass} value={title} required
            onChange={(e) => setTitle(e.target.value)} placeholder="Senior Backend Engineer" />
        </Field>

        <Field label="Description"
          hint="Requirements can be extracted from this text later, or set them directly below.">
          <textarea className={`${inputClass} min-h-[80px]`} value={description} required
            onChange={(e) => setDescription(e.target.value)} />
        </Field>

        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Required skills" hint="Comma separated.">
            <input className={inputClass} value={requiredSkills}
              onChange={(e) => setRequiredSkills(e.target.value)} placeholder="Python, PostgreSQL" />
          </Field>
          <Field label="Minimum experience" hint="Years. Leave blank if not required.">
            <input className={inputClass} type="number" min="0" max="60" value={minExperience}
              onChange={(e) => setMinExperience(e.target.value)} />
          </Field>
        </div>

        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? <Spinner /> : "Create job"}
        </Button>
      </form>
    </Card>
  );
}
