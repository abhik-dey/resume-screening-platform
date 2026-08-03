"""
Dependency-injection wiring for the API layer.

This module is the only place that knows how to assemble concrete
implementations (SQLAlchemyUserRepository, AuthService) from the abstract
interfaces the rest of the codebase depends on. Swapping an implementation
later means editing this file, not the routes or services.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.feedback.agent import FeedbackAgent
from app.agents.interview_question.agent import InterviewQuestionAgent
from app.agents.job_description.agent import JobDescriptionAgent
from app.agents.matching.agent import MatchingAgent
from app.agents.ranking.agent import RankingAgent
from app.agents.report.agent import ReportGeneratorAgent
from app.agents.resume_parser.agent import ResumeParsingAgent
from app.agents.skill_extractor.agent import SkillExtractionAgent
from app.core.config import get_settings
from app.core.security import TokenError, decode_access_token
from app.domain.entities.user import User, UserRole
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.llm_provider import LLMProvider
from app.infrastructure.db.session import get_db
from app.infrastructure.llm.factory import get_llm_provider
from app.infrastructure.repositories.sqlalchemy_audit_log_repository import SQLAlchemyAuditLogRepository
from app.infrastructure.repositories.sqlalchemy_candidate_repository import SQLAlchemyCandidateRepository
from app.infrastructure.repositories.sqlalchemy_feedback_repository import SQLAlchemyFeedbackRepository
from app.infrastructure.repositories.sqlalchemy_interview_question_repository import (
    SQLAlchemyInterviewQuestionRepository,
)
from app.infrastructure.repositories.sqlalchemy_job_repository import SQLAlchemyJobRepository
from app.infrastructure.repositories.sqlalchemy_report_repository import SQLAlchemyReportRepository
from app.infrastructure.repositories.sqlalchemy_resume_repository import SQLAlchemyResumeRepository
from app.infrastructure.repositories.sqlalchemy_resume_skill_repository import (
    SQLAlchemyResumeSkillRepository,
)
from app.infrastructure.repositories.sqlalchemy_score_repository import SQLAlchemyScoreRepository
from app.infrastructure.repositories.sqlalchemy_skill_repository import SQLAlchemySkillRepository
from app.infrastructure.repositories.sqlalchemy_user_repository import SQLAlchemyUserRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.services.auth_service import AuthService
from app.services.job_service import JobService
from app.services.resume_service import ResumeService

settings = get_settings()

# tokenUrl points Swagger UI's "Authorize" button at our login route.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# A single shared FileStorage instance — local disk today, swappable for an
# S3 adapter later without changing any service or route code.
_file_storage = LocalFileStorage(base_dir=settings.resume_storage_dir)


async def get_user_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db)


async def get_auth_service(
    repo: SQLAlchemyUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repo)


async def get_job_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyJobRepository:
    return SQLAlchemyJobRepository(db)


async def get_job_service(
    repo: SQLAlchemyJobRepository = Depends(get_job_repository),
) -> JobService:
    return JobService(repo)


async def get_resume_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyResumeRepository:
    return SQLAlchemyResumeRepository(db)


def get_file_storage() -> FileStorage:
    return _file_storage


async def get_resume_service(
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    storage: FileStorage = Depends(get_file_storage),
) -> ResumeService:
    return ResumeService(
        resume_repository=resume_repo,
        job_repository=job_repo,
        file_storage=storage,
        max_upload_size_bytes=settings.max_resume_upload_size_bytes,
    )


async def get_candidate_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyCandidateRepository:
    return SQLAlchemyCandidateRepository(db)


async def get_audit_log_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyAuditLogRepository:
    return SQLAlchemyAuditLogRepository(db)


def get_llm_provider_dependency() -> LLMProvider:
    return get_llm_provider(settings)


async def get_resume_parsing_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    candidate_repo: SQLAlchemyCandidateRepository = Depends(get_candidate_repository),
    storage: FileStorage = Depends(get_file_storage),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> ResumeParsingAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return ResumeParsingAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        candidate_repository=candidate_repo,
        file_storage=storage,
        llm_provider=llm,
        model_name=model_name,
    )


async def get_skill_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemySkillRepository:
    return SQLAlchemySkillRepository(db)


async def get_resume_skill_repository(
    db: AsyncSession = Depends(get_db),
) -> SQLAlchemyResumeSkillRepository:
    return SQLAlchemyResumeSkillRepository(db)


async def get_skill_extraction_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    skill_repo: SQLAlchemySkillRepository = Depends(get_skill_repository),
    resume_skill_repo: SQLAlchemyResumeSkillRepository = Depends(get_resume_skill_repository),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> SkillExtractionAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return SkillExtractionAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        skill_repository=skill_repo,
        resume_skill_repository=resume_skill_repo,
        llm_provider=llm,
        model_name=model_name,
    )


async def get_job_description_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> JobDescriptionAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return JobDescriptionAgent(
        audit_log_repository=audit_repo,
        job_repository=job_repo,
        llm_provider=llm,
        model_name=model_name,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    repo: SQLAlchemyUserRepository = Depends(get_user_repository),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise credentials_error from exc

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise credentials_error

    user = await repo.get_by_id(UUID(raw_user_id))
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_roles(*allowed_roles: UserRole):
    """Dependency factory enforcing RBAC on a route.

    Usage: `current_user: User = Depends(require_roles(UserRole.ADMIN))`
    """

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return _check


async def get_score_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyScoreRepository:
    return SQLAlchemyScoreRepository(db)


async def get_matching_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    resume_skill_repo: SQLAlchemyResumeSkillRepository = Depends(get_resume_skill_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    score_repo: SQLAlchemyScoreRepository = Depends(get_score_repository),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> MatchingAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return MatchingAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        resume_skill_repository=resume_skill_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        llm_provider=llm,
        model_name=model_name,
    )


async def get_ranking_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    score_repo: SQLAlchemyScoreRepository = Depends(get_score_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    resume_skill_repo: SQLAlchemyResumeSkillRepository = Depends(get_resume_skill_repository),
) -> RankingAgent:
    # No LLM provider: ranking is deterministic arithmetic (see the agent's
    # module docstring for why).
    return RankingAgent(
        audit_log_repository=audit_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        resume_repository=resume_repo,
        resume_skill_repository=resume_skill_repo,
    )


async def get_interview_question_repository(
    db: AsyncSession = Depends(get_db),
) -> SQLAlchemyInterviewQuestionRepository:
    return SQLAlchemyInterviewQuestionRepository(db)


async def get_interview_question_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    resume_skill_repo: SQLAlchemyResumeSkillRepository = Depends(get_resume_skill_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    score_repo: SQLAlchemyScoreRepository = Depends(get_score_repository),
    question_repo: SQLAlchemyInterviewQuestionRepository = Depends(get_interview_question_repository),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> InterviewQuestionAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return InterviewQuestionAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        resume_skill_repository=resume_skill_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        interview_question_repository=question_repo,
        llm_provider=llm,
        model_name=model_name,
    )


async def get_feedback_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyFeedbackRepository:
    return SQLAlchemyFeedbackRepository(db)


async def get_feedback_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    resume_skill_repo: SQLAlchemyResumeSkillRepository = Depends(get_resume_skill_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    score_repo: SQLAlchemyScoreRepository = Depends(get_score_repository),
    feedback_repo: SQLAlchemyFeedbackRepository = Depends(get_feedback_repository),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> FeedbackAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return FeedbackAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        resume_skill_repository=resume_skill_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        feedback_repository=feedback_repo,
        llm_provider=llm,
        model_name=model_name,
    )


async def get_report_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyReportRepository:
    return SQLAlchemyReportRepository(db)


async def get_report_generator_agent(
    audit_repo: SQLAlchemyAuditLogRepository = Depends(get_audit_log_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    score_repo: SQLAlchemyScoreRepository = Depends(get_score_repository),
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    candidate_repo: SQLAlchemyCandidateRepository = Depends(get_candidate_repository),
    feedback_repo: SQLAlchemyFeedbackRepository = Depends(get_feedback_repository),
    report_repo: SQLAlchemyReportRepository = Depends(get_report_repository),
    storage: FileStorage = Depends(get_file_storage),
    llm: LLMProvider = Depends(get_llm_provider_dependency),
) -> ReportGeneratorAgent:
    model_name = (
        settings.openai_model if settings.llm_provider == "openai" else settings.anthropic_model
    )
    return ReportGeneratorAgent(
        audit_log_repository=audit_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        resume_repository=resume_repo,
        candidate_repository=candidate_repo,
        feedback_repository=feedback_repo,
        report_repository=report_repo,
        file_storage=storage,
        llm_provider=llm,
        model_name=model_name,
    )
