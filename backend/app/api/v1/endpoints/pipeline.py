"""Pipeline orchestration endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_pipeline_service, require_roles
from app.api.v1.schemas.pipeline import (
    JobPipelineResponse,
    PipelineDescription,
    ResumePipelineResponse,
)
from app.domain.entities.user import User, UserRole
from app.graph.pipeline import describe_pipeline
from app.services.pipeline_service import PipelineError, PipelineService

router = APIRouter(tags=["pipeline"])


def _to_response(result) -> ResumePipelineResponse:
    return ResumePipelineResponse(
        resume_id=result.resume_id,
        success=result.success,
        completed_steps=result.completed_steps,
        failed_steps=result.failed_steps,
        step_details=result.step_details,
        halted=result.halted,
        halt_reason=result.halt_reason,
    )


@router.get("/api/v1/pipeline/describe", response_model=PipelineDescription)
async def describe(current_user: User = Depends(get_current_user)) -> PipelineDescription:
    """Describe the pipeline's steps and which failures halt it."""
    return PipelineDescription(**describe_pipeline())


@router.post("/api/v1/resumes/{resume_id}/pipeline", response_model=ResumePipelineResponse)
async def run_resume_pipeline_endpoint(
    resume_id: UUID,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> ResumePipelineResponse:
    """Run the full agent pipeline for one resume.

    Replaces calling parse -> extract-skills -> match -> interview-questions
    -> feedback -> index by hand. Failure of a prerequisite step halts the
    run; failures of enrichment steps are recorded and the run continues.
    """
    try:
        result = await pipeline_service.run_for_resume(resume_id)
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(result)


@router.post("/api/v1/jobs/{job_id}/pipeline", response_model=JobPipelineResponse)
async def run_job_pipeline_endpoint(
    job_id: UUID,
    generate_report: bool = True,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> JobPipelineResponse:
    """Run the full pipeline for every resume on a job, then rank and report.

    Resumes are processed sequentially — each makes several LLM calls, and
    parallel execution reliably trips free-tier rate limits.

    Note this is synchronous: a job with many resumes will hold the request
    open for a long time. Background execution is a known gap.
    """
    try:
        result = await pipeline_service.run_for_job(
            job_id,
            generated_by=current_user.id,
            generated_by_email=current_user.email,
            generate_report=generate_report,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return JobPipelineResponse(
        job_id=result.job_id,
        total_resumes=result.total_resumes,
        successful_resumes=result.successful_resumes,
        resume_results=[_to_response(r) for r in result.resume_results],
        ranking_success=result.ranking_success,
        ranking_reasoning=result.ranking_reasoning,
        report_success=result.report_success,
        report_reasoning=result.report_reasoning,
        report_id=result.report_id,
    )
