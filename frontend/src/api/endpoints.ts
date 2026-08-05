import { api, setToken, API_BASE_URL, getToken } from "./client";
import type {
  Feedback, FeedbackResult, InterviewQuestion, Job, JobPipelineResult,
  MatchResult, RagAnswer, RankedCandidate, ReportSummary, Resume,
  ResumePipelineResult, ResumeSkill, Score, SearchResponse, User,
} from "./types";

export async function login(email: string, password: string): Promise<User> {
  // The backend uses OAuth2 password flow, which is form-encoded rather
  // than JSON — the one endpoint that differs.
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail ?? "Sign in failed");
  }
  const { access_token } = await response.json();
  setToken(access_token);
  return api.get<User>("/api/v1/auth/me");
}

export const getCurrentUser = () => api.get<User>("/api/v1/auth/me");

export const register = (email: string, password: string, fullName: string) =>
  api.post<User>("/api/v1/auth/register", {
    email, password, full_name: fullName,
  });

export const listJobs = () => api.get<Job[]>("/api/v1/jobs");
export const getJob = (id: string) => api.get<Job>(`/api/v1/jobs/${id}`);

export const createJob = (job: Partial<Job>) => api.post<Job>("/api/v1/jobs", job);

export const listResumes = (jobId: string) =>
  api.get<Resume[]>(`/api/v1/jobs/${jobId}/resumes`);

export const uploadResume = (jobId: string, file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.postForm<Resume>(`/api/v1/jobs/${jobId}/resumes`, formData);
};

export const runResumePipeline = (resumeId: string) =>
  api.post<ResumePipelineResult>(`/api/v1/resumes/${resumeId}/pipeline`);

export const runJobPipeline = (jobId: string) =>
  api.post<JobPipelineResult>(`/api/v1/jobs/${jobId}/pipeline`);

export const getRanking = (jobId: string) =>
  api.get<RankedCandidate[]>(`/api/v1/jobs/${jobId}/ranking`);

export const rankJob = (jobId: string) =>
  api.post<{ ranking: RankedCandidate[]; total_candidates: number }>(
    `/api/v1/jobs/${jobId}/rank`,
  );

export const getResume = (id: string) => api.get<Resume>(`/api/v1/resumes/${id}`);
export const getScore = (id: string) => api.get<Score>(`/api/v1/resumes/${id}/score`);
export const matchResume = (id: string) =>
  api.post<MatchResult>(`/api/v1/resumes/${id}/match`);

export const getSkills = (id: string) =>
  api.get<ResumeSkill[]>(`/api/v1/resumes/${id}/skills`);

export const getFeedback = (id: string) =>
  api.get<FeedbackResult>(`/api/v1/resumes/${id}/feedback`);

export const generateFeedback = (id: string) =>
  api.post<FeedbackResult>(`/api/v1/resumes/${id}/feedback`);

export const getQuestions = (id: string) =>
  api.get<InterviewQuestion[]>(`/api/v1/resumes/${id}/interview-questions`);

export const searchResumes = (query: string, limit = 10) =>
  api.post<SearchResponse>("/api/v1/search/resumes", { query, limit });

export const askRag = (question: string, jobId?: string) =>
  api.post<RagAnswer>("/api/v1/rag/ask", {
    question, top_k: 5, ...(jobId ? { job_id: jobId } : {}),
  });

export const listReports = (jobId: string) =>
  api.get<ReportSummary[]>(`/api/v1/jobs/${jobId}/reports`);

export function reportDownloadUrl(reportId: string): string {
  return `${API_BASE_URL}/api/v1/reports/${reportId}/download`;
}

/** Downloads via fetch rather than a bare link, since the endpoint needs
 *  an Authorization header that an <a href> can't carry. */
export async function downloadReport(reportId: string): Promise<void> {
  const response = await fetch(reportDownloadUrl(reportId), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) throw new Error("Couldn't download the report");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `candidate-report-${reportId}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

export type { Feedback };
