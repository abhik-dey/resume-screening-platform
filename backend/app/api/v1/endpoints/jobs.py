"""Job endpoints — the minimal Job Management slice this phase needs."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.job_description.agent import JobDescriptionAgent
from app.api.deps import get_current_user, get_job_description_agent, get_job_service, require_roles
from app.api.v1.schemas.job import JobAnalysisResult, JobCreateRequest, JobResponse
from app.domain.entities.job import Job
from app.domain.entities.user import User, UserRole
from app.services.job_service import JobService

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreateRequest,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    job_service: JobService = Depends(get_job_service),
) -> Job:
    return await job_service.create_job(
        created_by=current_user.id,
        title=payload.title,
        description=payload.description,
        required_skills=payload.required_skills,
        preferred_skills=payload.preferred_skills,
        min_experience_years=payload.min_experience_years,
        education_requirement=payload.education_requirement,
        responsibilities=payload.responsibilities,
        keywords=payload.keywords,
        status=payload.status,
    )


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
) -> list[Job]:
    return await job_service.list_jobs(skip=skip, limit=limit)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
) -> Job:
    job = await job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return job


@router.post("/{job_id}/analyze", response_model=JobAnalysisResult)
async def analyze_job(
    job_id: UUID,
    overwrite: bool = False,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    job_service: JobService = Depends(get_job_service),
    analysis_agent: JobDescriptionAgent = Depends(get_job_description_agent),
) -> JobAnalysisResult:
    """Extract structured requirements from the job's free-text description.

    By default this only fills fields the recruiter left empty — pass
    `overwrite=true` to replace recruiter-provided values with the agent's
    extraction. Either way, everything extracted is returned so the
    recruiter can see what the agent would have suggested.
    """
    job = await job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    result = await analysis_agent.analyze(job_id, overwrite=overwrite)
    updated_job = await job_service.get_job(job_id)
    output = result.output or {}
    return JobAnalysisResult(
        job=JobResponse.model_validate(updated_job),
        success=result.success,
        reasoning=result.reasoning,
        extracted=output.get("extracted", {}),
        applied_fields=output.get("applied_fields", []),
        skipped_fields=output.get("skipped_fields", []),
    )
