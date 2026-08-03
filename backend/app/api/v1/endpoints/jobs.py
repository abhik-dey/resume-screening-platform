"""Job endpoints — the minimal Job Management slice this phase needs."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.job_description.agent import JobDescriptionAgent
from app.agents.ranking.agent import RankingAgent
from app.api.deps import (
    get_current_user,
    get_job_description_agent,
    get_job_service,
    get_ranking_agent,
    get_resume_repository,
    get_score_repository,
    require_roles,
)
from app.api.v1.schemas.job import JobAnalysisResult, JobCreateRequest, JobResponse
from app.api.v1.schemas.ranking import RankedCandidateResponse, RankingResult, RankRequest
from app.domain.entities.job import Job
from app.domain.entities.user import User, UserRole
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.score_repository import ScoreRepository
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


async def _build_ranked_response(
    ordering: list[dict],
    score_repo: ScoreRepository,
    resume_repo: ResumeRepository,
) -> list[RankedCandidateResponse]:
    """Join the ranker's ordering with each score's stored detail."""
    from uuid import UUID as _UUID

    candidates: list[RankedCandidateResponse] = []
    for item in ordering:
        resume_id = _UUID(item["resume_id"])
        score = await score_repo.get_by_resume_id(resume_id)
        if score is None:
            continue
        resume = await resume_repo.get_by_id(resume_id)
        candidates.append(
            RankedCandidateResponse(
                rank=item["rank"],
                resume_id=resume_id,
                candidate_id=resume.candidate_id if resume else None,
                similarity_score=score.similarity_score,
                skill_overlap=score.skill_overlap,
                missing_skills=score.missing_skills,
                strengths=score.strengths,
                weaknesses=score.weaknesses,
                explanation=score.explanation,
                tie_break_reason=item.get("tie_break_reason"),
            )
        )
    return candidates


@router.post("/{job_id}/rank", response_model=RankingResult)
async def rank_candidates(
    job_id: UUID,
    payload: RankRequest | None = None,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    job_service: JobService = Depends(get_job_service),
    ranking_agent: RankingAgent = Depends(get_ranking_agent),
    score_repo: ScoreRepository = Depends(get_score_repository),
    resume_repo: ResumeRepository = Depends(get_resume_repository),
) -> RankingResult:
    """Rank every scored candidate for this job, best first.

    Ranking is deterministic: identical data always produces an identical
    ordering, with ties broken by an explicit documented chain. Optionally
    supply custom `weights` to re-score candidates before ranking — useful
    when a particular role should weight skills or education differently
    from the 60/25/15 default.
    """
    job = await job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    weights = payload.weights.to_domain() if payload and payload.weights else None
    result = await ranking_agent.rank(job_id, weights=weights)
    output = result.output or {}

    ranking = await _build_ranked_response(output.get("ordering", []), score_repo, resume_repo)
    return RankingResult(
        success=result.success,
        reasoning=result.reasoning,
        total_candidates=output.get("total_candidates", 0),
        weights_applied=output.get("weights_applied"),
        ranking=ranking,
    )


@router.get("/{job_id}/ranking", response_model=list[RankedCandidateResponse])
async def get_ranking(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
    score_repo: ScoreRepository = Depends(get_score_repository),
    resume_repo: ResumeRepository = Depends(get_resume_repository),
) -> list[RankedCandidateResponse]:
    """Return the previously computed ranking for this job."""
    job = await job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")

    scores = await score_repo.list_by_job(job_id)
    ranked_scores = [s for s in scores if s.rank is not None]
    ranked_scores.sort(key=lambda s: (s.rank, str(s.resume_id)))

    candidates: list[RankedCandidateResponse] = []
    for score in ranked_scores:
        resume = await resume_repo.get_by_id(score.resume_id)
        candidates.append(
            RankedCandidateResponse(
                rank=score.rank,
                resume_id=score.resume_id,
                candidate_id=resume.candidate_id if resume else None,
                similarity_score=score.similarity_score,
                skill_overlap=score.skill_overlap,
                missing_skills=score.missing_skills,
                strengths=score.strengths,
                weaknesses=score.weaknesses,
                explanation=score.explanation,
            )
        )
    return candidates
