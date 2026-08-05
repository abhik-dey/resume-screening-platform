// TypeScript mirrors of the backend API schemas.

export type UserRole = "admin" | "recruiter" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface Job {
  id: string;
  created_by: string;
  title: string;
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  min_experience_years: number | null;
  education_requirement: string | null;
  responsibilities: string[];
  keywords: string[];
  status: "draft" | "open" | "closed";
  created_at: string;
}

export interface Resume {
  id: string;
  job_id: string;
  candidate_id: string | null;
  original_filename: string;
  status: "uploaded" | "parsing" | "parsed" | "failed";
  parsed_data: Record<string, unknown> | null;
  created_at: string;
}

export interface ScoreComponent {
  name: string;
  raw_score: number;
  weight: number;
  weighted_score: number;
  detail: string;
}

export interface Score {
  id: string;
  resume_id: string;
  job_id: string;
  similarity_score: number;
  skill_overlap: string[];
  missing_skills: string[];
  strengths: string[];
  weaknesses: string[];
  rank: number | null;
  explanation: string | null;
  created_at: string;
}

export interface MatchResult {
  success: boolean;
  reasoning: string;
  score: Score | null;
  breakdown: { overall_score?: number; components?: ScoreComponent[] };
  explanation: string;
  qualitative_analysis_failed: boolean;
}

export interface RankedCandidate {
  rank: number;
  resume_id: string;
  candidate_id: string | null;
  similarity_score: number;
  skill_overlap: string[];
  missing_skills: string[];
  strengths: string[];
  weaknesses: string[];
  explanation: string | null;
  tie_break_reason?: string | null;
}

export type Recommendation =
  | "strong_recommend"
  | "recommend"
  | "consider"
  | "not_recommended";

export interface Feedback {
  id: string;
  resume_id: string;
  job_id: string;
  recommendation: Recommendation;
  threshold_rationale: string;
  summary: string | null;
  strengths: string[];
  weaknesses: string[];
  risk_factors: string[];
  improvement_suggestions: string[];
  narrative_generation_failed: boolean;
  created_at: string;
}

export interface FeedbackResult {
  success: boolean;
  reasoning: string;
  feedback: Feedback | null;
  advisory_notice: string;
}

export interface InterviewQuestion {
  id: string;
  resume_id: string;
  job_id: string;
  question: string;
  category: "technical" | "behavioral" | "project";
  difficulty: "easy" | "medium" | "hard";
  rationale: string | null;
  created_at: string;
}

export interface ResumeSkill {
  skill_id: string;
  name: string;
  category: string;
  confidence: number | null;
}

export interface PipelineStepDetail {
  success: boolean;
  reasoning: string;
  [key: string]: unknown;
}

export interface ResumePipelineResult {
  resume_id: string;
  success: boolean;
  completed_steps: string[];
  failed_steps: string[];
  step_details: Record<string, PipelineStepDetail>;
  halted: boolean;
  halt_reason: string | null;
}

export interface JobPipelineResult {
  job_id: string;
  total_resumes: number;
  successful_resumes: number;
  resume_results: ResumePipelineResult[];
  ranking_success: boolean;
  ranking_reasoning: string;
  report_success: boolean;
  report_reasoning: string;
  report_id: string | null;
}

export interface SearchHit {
  resume_id: string;
  job_id: string | null;
  similarity: number;
  candidate_name: string | null;
  candidate_email: string | null;
  original_filename: string | null;
}

export interface SearchResponse {
  query: string;
  embedding_model: string;
  total_hits: number;
  results: SearchHit[];
}

export interface RagClaim {
  text: string;
  source_ids: number[];
  warning: string | null;
}

export interface RagSource {
  source_id: number;
  resume_id: string;
  candidate_name: string;
  similarity: number;
  text: string;
}

export interface RagAnswer {
  question: string;
  answer: string;
  claims: RagClaim[];
  sources: RagSource[];
  insufficient_evidence: boolean;
  citation_warnings: string[];
  answer_rejected: boolean;
}

export interface ReportSummary {
  id: string;
  job_id: string;
  generated_by: string;
  summary: string | null;
  created_at: string;
}
