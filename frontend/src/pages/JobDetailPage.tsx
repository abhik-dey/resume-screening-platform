import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  downloadReport, getJob, getRanking, listReports, listResumes,
  runJobPipeline, uploadResume,
} from "../api/endpoints";
import type { Job, JobPipelineResult, RankedCandidate, ReportSummary, Resume } from "../api/types";
import { useCanEdit } from "../auth/AuthContext";
import { ScoreBar } from "../components/ScoreBreakdown";
import { SkillChip, StatusPill } from "../components/Recommendation";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Spinner } from "../components/ui";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const canEdit = useCanEdit();
  const fileInput = useRef<HTMLInputElement>(null);

  const [job, setJob] = useState<Job | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [ranking, setRanking] = useState<RankedCandidate[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<JobPipelineResult | null>(null);

  const load = () => {
    Promise.all([getJob(jobId), listResumes(jobId), getRanking(jobId), listReports(jobId)])
      .then(([j, r, rank, rep]) => { setJob(j); setResumes(r); setRanking(rank); setReports(rep); })
      .catch((cause) => setError(cause.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [jobId]);

  const upload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      await uploadResume(jobId, file);
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const runPipeline = async () => {
    setPipelineRunning(true);
    setError(null);
    setPipelineResult(null);
    try {
      setPipelineResult(await runJobPipeline(jobId));
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The pipeline couldn't run");
    } finally {
      setPipelineRunning(false);
    }
  };

  if (loading) return <Card className="p-8 flex justify-center"><Spinner label="Loading job" /></Card>;
  if (!job) return <ErrorBanner message="This job couldn't be loaded." />;

  const rankByResume = new Map(ranking.map((r) => [r.resume_id, r]));

  return (
    <div className="space-y-6">
      <div>
        <Link to="/jobs" className="text-sm text-ink-soft hover:text-ink">← Jobs</Link>
        <div className="flex items-start justify-between gap-4 mt-2">
          <div>
            <h1 className="text-xl font-semibold text-ink">{job.title}</h1>
            <p className="text-sm text-ink-soft mt-1 max-w-2xl leading-relaxed">{job.description}</p>
          </div>
          <StatusPill status={job.status} />
        </div>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader
              title={`Candidates · ${resumes.length}`}
              action={
                canEdit && (
                  <div className="flex items-center gap-2">
                    <input ref={fileInput} type="file" accept=".pdf,.docx" className="hidden"
                      onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
                    <Button onClick={() => fileInput.current?.click()} disabled={uploading}>
                      {uploading ? <Spinner /> : "Upload resume"}
                    </Button>
                    <Button variant="primary" onClick={runPipeline}
                      disabled={pipelineRunning || resumes.length === 0}>
                      {pipelineRunning ? <Spinner label="Running" /> : "Screen all"}
                    </Button>
                  </div>
                )
              }
            />

            {resumes.length === 0 ? (
              <EmptyState
                title="No candidates yet"
                hint="Upload a PDF or DOCX resume to add a candidate to this job."
              />
            ) : (
              <ul className="divide-y divide-line">
                {resumes.map((resume) => {
                  const ranked = rankByResume.get(resume.id);
                  return (
                    <li key={resume.id}>
                      <Link to={`/resumes/${resume.id}`}
                        className="flex items-center gap-4 px-5 py-3 hover:bg-surface-sunk transition-colors">
                        <span className="numeric text-sm text-ink-faint w-8 shrink-0">
                          {ranked?.rank != null ? `#${ranked.rank}` : "—"}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-ink truncate">{resume.original_filename}</p>
                          {ranked && (
                            <div className="mt-1.5 max-w-[220px]">
                              <ScoreBar score={ranked.similarity_score} compact />
                            </div>
                          )}
                        </div>
                        {ranked && (
                          <span className="numeric text-sm text-ink">
                            {ranked.similarity_score.toFixed(2)}
                          </span>
                        )}
                        <StatusPill status={resume.status} />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {pipelineResult && <PipelineReport result={pipelineResult} />}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Requirements" />
            <dl className="px-5 py-4 space-y-4 text-sm">
              <div>
                <dt className="eyebrow mb-1.5">Required skills</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {job.required_skills.length
                    ? job.required_skills.map((s) => <SkillChip key={s} name={s} />)
                    : <span className="text-ink-faint text-xs">None specified</span>}
                </dd>
              </div>
              {job.preferred_skills.length > 0 && (
                <div>
                  <dt className="eyebrow mb-1.5">Preferred</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {job.preferred_skills.map((s) => <SkillChip key={s} name={s} />)}
                  </dd>
                </div>
              )}
              <div>
                <dt className="eyebrow mb-1">Minimum experience</dt>
                <dd className="text-ink">
                  {job.min_experience_years != null
                    ? `${job.min_experience_years} years`
                    : <span className="text-ink-faint text-xs">Not specified</span>}
                </dd>
              </div>
              <div>
                <dt className="eyebrow mb-1">Education</dt>
                <dd className="text-ink">
                  {job.education_requirement ?? (
                    <span className="text-ink-faint text-xs">Not specified</span>
                  )}
                </dd>
              </div>
            </dl>
          </Card>

          <Card>
            <CardHeader title={`Reports · ${reports.length}`} />
            {reports.length === 0 ? (
              <p className="px-5 py-4 text-xs text-ink-faint leading-relaxed">
                Screening all candidates generates a PDF report covering the pool.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {reports.map((report) => (
                  <li key={report.id} className="px-5 py-3 flex items-center justify-between gap-3">
                    <span className="text-xs text-ink-soft">
                      {new Date(report.created_at).toLocaleString()}
                    </span>
                    <Button onClick={() => downloadReport(report.id)}>Download</Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Shows exactly which pipeline steps ran and which halted.
 *  The backend distinguishes fatal from non-fatal failures, so surfacing
 *  the per-step outcome is more useful than a single success/fail. */
function PipelineReport({ result }: { result: JobPipelineResult }) {
  return (
    <Card>
      <CardHeader title="Screening run" />
      <div className="px-5 py-4">
        <p className="text-sm text-ink">
          {result.successful_resumes} of {result.total_resumes} candidates screened successfully.
        </p>
        {result.successful_resumes < result.total_resumes && (
          <p className="text-xs text-ink-soft mt-1 leading-relaxed">
            Candidates that halted are listed below with the step that failed. Ranking and
            reporting still ran on the ones that succeeded.
          </p>
        )}

        <ul className="mt-4 space-y-2">
          {result.resume_results.map((item) => (
            <li key={item.resume_id}
              className="flex items-start gap-3 text-xs border-t border-line pt-2">
              <span className={item.success ? "text-positive" : "text-negative"}>
                {item.success ? "✓" : "✕"}
              </span>
              <div className="min-w-0">
                <p className="numeric text-ink-faint">{item.resume_id.slice(0, 8)}</p>
                {item.halted ? (
                  <p className="text-negative mt-0.5 leading-relaxed">{item.halt_reason}</p>
                ) : (
                  <p className="text-ink-soft mt-0.5">
                    {item.completed_steps.join(" → ")}
                    {item.failed_steps.length > 0 && (
                      <span className="text-caution"> · skipped {item.failed_steps.join(", ")}</span>
                    )}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
