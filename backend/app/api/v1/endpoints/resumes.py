"""Resume endpoints: upload, list, get metadata, download original file."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.agents.interview_question.agent import InterviewQuestionAgent
from app.agents.matching.agent import MatchingAgent
from app.agents.resume_parser.agent import ResumeParsingAgent
from app.agents.skill_extractor.agent import SkillExtractionAgent
from app.api.deps import (
    get_current_user,
    get_interview_question_agent,
    get_interview_question_repository,
    get_matching_agent,
    get_resume_parsing_agent,
    get_resume_service,
    get_resume_skill_repository,
    get_score_repository,
    get_skill_extraction_agent,
    require_roles,
)
from app.api.v1.schemas.interview_question import (
    InterviewQuestionGenerationResult,
    InterviewQuestionRequest,
    InterviewQuestionResponse,
)
from app.api.v1.schemas.resume import ResumeParseResult, ResumeResponse
from app.api.v1.schemas.score import MatchResultResponse, ScoreResponse
from app.api.v1.schemas.skill import ResumeSkillResponse, SkillExtractionResult
from app.domain.entities.resume import Resume
from app.domain.entities.user import User, UserRole
from app.domain.interfaces.interview_question_repository import InterviewQuestionRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository
from app.domain.validation.resume_file import ResumeValidationError
from app.services.resume_service import (
    JobNotFoundError,
    JobNotOpenError,
    ResumeNotFoundError,
    ResumeService,
)

router = APIRouter(tags=["resumes"])

# A conservative content-type map for the download endpoint — derived from
# the file extension we ourselves validated at upload time, not from any
# client-supplied header.
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post(
    "/api/v1/jobs/{job_id}/resumes",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    job_id: UUID,
    file: UploadFile,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Resume:
    content = await file.read()
    try:
        return await resume_service.upload(
            job_id=job_id,
            uploaded_by=current_user.id,
            filename=file.filename or "unnamed",
            content=content,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobNotOpenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ResumeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/api/v1/jobs/{job_id}/resumes", response_model=list[ResumeResponse])
async def list_resumes_for_job(
    job_id: UUID,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> list[Resume]:
    return await resume_service.list_resumes_for_job(job_id, skip=skip, limit=limit)


@router.get("/api/v1/resumes/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Resume:
    try:
        return await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/api/v1/resumes/{resume_id}/download")
async def download_resume(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    try:
        resume, content = await resume_service.download(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    extension = "." + resume.original_filename.rsplit(".", 1)[-1].lower()
    content_type = _CONTENT_TYPES.get(extension, "application/octet-stream")
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{resume.original_filename}"'},
    )


@router.post("/api/v1/resumes/{resume_id}/parse", response_model=ResumeParseResult)
async def parse_resume(
    resume_id: UUID,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    resume_service: ResumeService = Depends(get_resume_service),
    parsing_agent: ResumeParsingAgent = Depends(get_resume_parsing_agent),
) -> ResumeParseResult:
    # Confirm the resume exists before invoking the agent — a 404 here is a
    # routing error, not a parsing failure, so it shouldn't be swallowed
    # into the agent's success/failure result.
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await parsing_agent.parse(resume_id)
    updated_resume = await resume_service.get_resume(resume_id)
    return ResumeParseResult(
        resume=ResumeResponse.model_validate(updated_resume),
        success=result.success,
        reasoning=result.reasoning,
    )


@router.post("/api/v1/resumes/{resume_id}/extract-skills", response_model=SkillExtractionResult)
async def extract_skills(
    resume_id: UUID,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    resume_service: ResumeService = Depends(get_resume_service),
    extraction_agent: SkillExtractionAgent = Depends(get_skill_extraction_agent),
) -> SkillExtractionResult:
    # A missing resume is a routing error (404). A resume that exists but
    # isn't parsed yet is a valid, inspectable outcome — the agent reports
    # that as a handled failure (success: false), not an HTTP error, same
    # philosophy as the parse endpoint above.
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await extraction_agent.extract(resume_id)
    output = result.output or {}
    return SkillExtractionResult(
        success=result.success,
        reasoning=result.reasoning,
        resolved_skills=output.get("resolved_skills", []),
        unresolved_raw_skills=output.get("unresolved_raw_skills", []),
    )


@router.get("/api/v1/resumes/{resume_id}/skills", response_model=list[ResumeSkillResponse])
async def list_resume_skills(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
    resume_skill_repo: ResumeSkillRepository = Depends(get_resume_skill_repository),
) -> list:
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return await resume_skill_repo.list_by_resume(resume_id)


@router.post("/api/v1/resumes/{resume_id}/match", response_model=MatchResultResponse)
async def match_resume(
    resume_id: UUID,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    resume_service: ResumeService = Depends(get_resume_service),
    matching_agent: MatchingAgent = Depends(get_matching_agent),
    score_repo: ScoreRepository = Depends(get_score_repository),
) -> MatchResultResponse:
    """Score this resume against the job it was uploaded for.

    The numeric score is computed deterministically — running this twice on
    unchanged data produces an identical score. `breakdown` shows exactly
    how it was derived. Strengths/weaknesses come from an LLM and may be
    empty if that call failed; the score is unaffected either way.
    """
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    result = await matching_agent.match(resume_id)
    output = result.output or {}
    score = await score_repo.get_by_resume_id(resume_id)

    return MatchResultResponse(
        success=result.success,
        reasoning=result.reasoning,
        score=ScoreResponse.model_validate(score) if score else None,
        breakdown=output.get("breakdown", {}),
        explanation=output.get("explanation", ""),
        qualitative_analysis_failed=output.get("qualitative_analysis_failed", False),
    )


@router.get("/api/v1/resumes/{resume_id}/score", response_model=ScoreResponse)
async def get_resume_score(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
    score_repo: ScoreRepository = Depends(get_score_repository),
) -> ScoreResponse:
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    score = await score_repo.get_by_resume_id(resume_id)
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume {resume_id} has not been matched yet — run POST /resumes/{resume_id}/match first",
        )
    return ScoreResponse.model_validate(score)


@router.post(
    "/api/v1/resumes/{resume_id}/interview-questions",
    response_model=InterviewQuestionGenerationResult,
)
async def generate_interview_questions(
    resume_id: UUID,
    payload: InterviewQuestionRequest | None = None,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    resume_service: ResumeService = Depends(get_resume_service),
    question_agent: InterviewQuestionAgent = Depends(get_interview_question_agent),
    question_repo: InterviewQuestionRepository = Depends(get_interview_question_repository),
) -> InterviewQuestionGenerationResult:
    """Generate interview questions tailored to this candidate and job.

    Regenerating REPLACES any previous set rather than appending to it.
    Unlike scoring, this has no deterministic fallback — if generation
    fails, nothing is saved and `success` is false, rather than returning
    fabricated placeholder questions.
    """
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    count = payload.question_count if payload else 9
    result = await question_agent.generate(resume_id, question_count=count)
    output = result.output or {}
    saved = await question_repo.list_by_resume(resume_id) if result.success else []

    return InterviewQuestionGenerationResult(
        success=result.success,
        reasoning=result.reasoning,
        questions=[InterviewQuestionResponse.model_validate(q) for q in saved],
        by_category=output.get("by_category", {}),
        by_difficulty=output.get("by_difficulty", {}),
    )


@router.get(
    "/api/v1/resumes/{resume_id}/interview-questions",
    response_model=list[InterviewQuestionResponse],
)
async def list_interview_questions(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    resume_service: ResumeService = Depends(get_resume_service),
    question_repo: InterviewQuestionRepository = Depends(get_interview_question_repository),
) -> list[InterviewQuestionResponse]:
    try:
        await resume_service.get_resume(resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    questions = await question_repo.list_by_resume(resume_id)
    return [InterviewQuestionResponse.model_validate(q) for q in questions]
