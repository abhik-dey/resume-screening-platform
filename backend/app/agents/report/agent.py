"""
Report Generator Agent.

Pipeline step 8 — the final agent (per the Phase 1 LangGraph flow):
Feedback Agent -> Report Generator.

Structurally different from Phases 6-12 in three ways:

1. It AGGREGATES rather than analyzes. Every score, rank, and recommendation
   in the output was computed by an earlier agent. Nothing here infers
   anything new.

2. The core work has NO LLM. Assembling and rendering a PDF is deterministic.
   The LLM's only contribution is an optional executive-summary paragraph;
   if it fails, the report generates in full without it.

3. It produces a FILE, not just database rows — the first agent to do so.
   It reuses the FileStorage interface from Phase 5, so a future S3 migration
   covers reports automatically.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.llm_json_utils import call_llm_for_json
from app.agents.report.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.report.schemas import ExecutiveSummary
from app.domain.entities.report import Report
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.feedback_repository import FeedbackRepository
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.report_repository import ReportRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.score_repository import ScoreRepository
from app.domain.report.builder import assemble_report_data
from app.infrastructure.report.pdf_renderer import render_report_pdf

MAX_LLM_ATTEMPTS = 2
# How many top candidates to describe in the executive summary prompt —
# enough for useful orientation without bloating the request.
TOP_CANDIDATES_FOR_SUMMARY = 5


class ReportGenerationError(Exception):
    """Raised when report generation cannot proceed at all."""


class ReportGeneratorAgent(BaseAgent):
    agent_name = "report_generator"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        resume_repository: ResumeRepository,
        candidate_repository: CandidateRepository,
        feedback_repository: FeedbackRepository,
        report_repository: ReportRepository,
        file_storage: FileStorage,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._jobs = job_repository
        self._scores = score_repository
        self._resumes = resume_repository
        self._candidates = candidate_repository
        self._feedback = feedback_repository
        self._reports = report_repository
        self._storage = file_storage
        self._llm = llm_provider

    async def generate(
        self,
        job_id: uuid.UUID,
        generated_by: uuid.UUID,
        generated_by_email: str | None = None,
    ):
        """Public entrypoint — wraps `run()` with the job's audit input_ref."""
        return await self.run(
            input_ref=f"job:{job_id}",
            job_id=job_id,
            generated_by=generated_by,
            generated_by_email=generated_by_email,
        )

    async def _execute(
        self, job_id: uuid.UUID, generated_by: uuid.UUID, generated_by_email: str | None
    ) -> tuple[dict[str, Any], str]:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise ReportGenerationError(f"Job {job_id} not found")

        scores = await self._scores.list_by_job(job_id)
        if not scores:
            raise ReportGenerationError(
                f"Job {job_id} has no scored candidates. Run matching on its resumes before "
                "generating a report — an empty report would be misleading."
            )

        resume_filenames: dict[uuid.UUID, str] = {}
        candidate_details: dict[uuid.UUID, dict] = {}
        for score in scores:
            resume = await self._resumes.get_by_id(score.resume_id)
            if resume is None:
                continue
            resume_filenames[score.resume_id] = resume.original_filename
            if resume.candidate_id:
                candidate = await self._candidates.get_by_id(resume.candidate_id)
                if candidate:
                    candidate_details[score.resume_id] = {
                        "full_name": candidate.full_name,
                        "email": candidate.email,
                    }

        feedback_entries = await self._feedback.list_by_job(job_id)
        feedback_by_resume = {f.resume_id: f for f in feedback_entries}

        data = assemble_report_data(
            job=job,
            scores=scores,
            resume_filenames=resume_filenames,
            candidate_details=candidate_details,
            feedback_by_resume=feedback_by_resume,
        )

        # Optional enrichment — a failure here must not lose the report.
        summary = await self._generate_summary(data)
        if summary is not None:
            data.executive_summary = summary.summary
        else:
            data.summary_generation_failed = True

        pdf_bytes = render_report_pdf(data, generated_by_email=generated_by_email)
        storage_path = await self._storage.save(pdf_bytes, f"report-{job_id}.pdf")

        report = await self._reports.create(
            Report(
                id=uuid.uuid4(),
                job_id=job_id,
                generated_by=generated_by,
                file_path=storage_path,
                summary=data.executive_summary,
                created_at=datetime.now(timezone.utc),
            )
        )

        output = {
            "report_id": str(report.id),
            "total_candidates": data.total_candidates,
            "average_score": data.average_score,
            "recommendation_counts": data.recommendation_counts,
            "pdf_size_bytes": len(pdf_bytes),
            "summary_generation_failed": data.summary_generation_failed,
        }
        reasoning = (
            f"Generated report for job '{job.title}' covering {data.total_candidates} candidate(s), "
            f"average match score {data.average_score:.2f}. "
            f"Recommendation breakdown: {data.recommendation_counts or 'none assessed'}."
        )
        if data.summary_generation_failed:
            reasoning += (
                f" The LLM executive summary failed after {MAX_LLM_ATTEMPTS} attempts; the report "
                "was generated without it, since all candidate data is computed independently."
            )
        return output, reasoning

    async def _generate_summary(self, data) -> ExecutiveSummary | None:
        top = [
            {
                "rank": c.rank,
                "score": c.similarity_score,
                "recommendation": c.recommendation_label,
                "matched_skills": c.matched_skills,
                "missing_skills": c.missing_skills,
            }
            for c in data.candidates[:TOP_CANDIDATES_FOR_SUMMARY]
        ]
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                job_title=data.job_title,
                required_skills=data.required_skills,
                total_candidates=data.total_candidates,
                average_score=data.average_score,
                recommendation_counts=data.recommendation_counts,
                top_candidates=top,
            ),
            validate=ExecutiveSummary.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
