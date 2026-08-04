"""
Pipeline orchestration service.

Two levels, because the agents operate at two different scopes:

RESUME-SCOPED (the LangGraph pipeline): parse, skills, match, questions,
feedback, index. Each runs against one resume independently.

JOB-SCOPED (run once, after all resumes): ranking and reporting. Ranking is
inherently comparative — running it per-candidate would be meaningless — and
a report describes the whole pool.

So a job-level run is: graph per resume, then rank once, then report once.
"""
import uuid
from dataclasses import dataclass, field

from app.agents.ranking.agent import RankingAgent
from app.agents.report.agent import ReportGeneratorAgent
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.graph.pipeline import run_resume_pipeline
from app.graph.state import PipelineState


class PipelineError(Exception):
    """Raised when a pipeline run cannot start at all."""


@dataclass
class ResumePipelineResult:
    resume_id: uuid.UUID
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    step_details: dict = field(default_factory=dict)
    halted: bool = False
    halt_reason: str | None = None

    @property
    def success(self) -> bool:
        """A run counts as successful if it wasn't halted by a fatal step.

        Deliberately not "zero failures": a resume that parsed, scored, and
        produced feedback but failed to index is a useful result, and
        reporting it as a failure would obscure the distinction between a
        degraded run and a broken one.
        """
        return not self.halted


@dataclass
class JobPipelineResult:
    job_id: uuid.UUID
    resume_results: list[ResumePipelineResult] = field(default_factory=list)
    ranking_success: bool = False
    ranking_reasoning: str = ""
    report_success: bool = False
    report_reasoning: str = ""
    report_id: str | None = None

    @property
    def total_resumes(self) -> int:
        return len(self.resume_results)

    @property
    def successful_resumes(self) -> int:
        return sum(1 for r in self.resume_results if r.success)


def _to_result(state: PipelineState, resume_id: uuid.UUID) -> ResumePipelineResult:
    return ResumePipelineResult(
        resume_id=resume_id,
        completed_steps=list(state.get("completed_steps") or []),
        failed_steps=list(state.get("failed_steps") or []),
        step_details=dict(state.get("step_details") or {}),
        halted=bool(state.get("halted")),
        halt_reason=state.get("halt_reason"),
    )


class PipelineService:
    def __init__(
        self,
        pipeline,
        resume_repository: ResumeRepository,
        job_repository: JobRepository,
        ranking_agent: RankingAgent,
        report_agent: ReportGeneratorAgent,
    ) -> None:
        self._pipeline = pipeline
        self._resumes = resume_repository
        self._jobs = job_repository
        self._ranking = ranking_agent
        self._report = report_agent

    async def run_for_resume(self, resume_id: uuid.UUID) -> ResumePipelineResult:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise PipelineError(f"Resume {resume_id} not found")

        state = await run_resume_pipeline(self._pipeline, resume_id, resume.job_id)
        return _to_result(state, resume_id)

    async def run_for_job(
        self,
        job_id: uuid.UUID,
        generated_by: uuid.UUID,
        generated_by_email: str | None = None,
        generate_report: bool = True,
    ) -> JobPipelineResult:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise PipelineError(f"Job {job_id} not found")

        resumes = await self._resumes.list_by_job(job_id, skip=0, limit=1000)
        if not resumes:
            raise PipelineError(
                f"Job {job_id} has no resumes. Upload at least one before running the pipeline."
            )

        result = JobPipelineResult(job_id=job_id)

        # Resumes run sequentially rather than concurrently: each makes
        # several LLM calls, and free-tier rate limits make parallel runs a
        # reliable way to get throttled. Concurrency with rate limiting is a
        # worthwhile improvement, not a default.
        for resume in resumes:
            state = await run_resume_pipeline(self._pipeline, resume.id, job_id)
            result.resume_results.append(_to_result(state, resume.id))

        # Ranking needs every candidate scored, so it runs once at the end.
        ranking = await self._ranking.rank(job_id)
        result.ranking_success = ranking.success
        result.ranking_reasoning = ranking.reasoning

        if generate_report:
            report = await self._report.generate(
                job_id, generated_by=generated_by, generated_by_email=generated_by_email
            )
            result.report_success = report.success
            result.report_reasoning = report.reasoning
            if report.output:
                result.report_id = report.output.get("report_id")

        return result
