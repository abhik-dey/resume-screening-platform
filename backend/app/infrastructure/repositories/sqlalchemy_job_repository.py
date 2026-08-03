"""Concrete JobRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.job import Job
from app.domain.interfaces.job_repository import JobRepository
from app.infrastructure.db.models.job import JobModel


def _to_entity(model: JobModel) -> Job:
    return Job(
        id=model.id,
        created_by=model.created_by,
        title=model.title,
        description=model.description,
        required_skills=list(model.required_skills),
        preferred_skills=list(model.preferred_skills),
        min_experience_years=model.min_experience_years,
        education_requirement=model.education_requirement,
        responsibilities=list(model.responsibilities),
        keywords=list(model.keywords),
        status=model.status,
        created_at=model.created_at,
    )


class SQLAlchemyJobRepository(JobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job: Job) -> Job:
        model = JobModel(
            id=job.id,
            created_by=job.created_by,
            title=job.title,
            description=job.description,
            required_skills=job.required_skills,
            preferred_skills=job.preferred_skills,
            min_experience_years=job.min_experience_years,
            education_requirement=job.education_requirement,
            responsibilities=job.responsibilities,
            keywords=job.keywords,
            status=job.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, job_id: UUID) -> Job | None:
        model = await self._session.get(JobModel, job_id)
        return _to_entity(model) if model else None

    async def update(self, job: Job) -> Job:
        model = await self._session.get(JobModel, job.id)
        if model is None:
            raise ValueError(f"Cannot update job {job.id}: not found")
        model.title = job.title
        model.description = job.description
        model.required_skills = job.required_skills
        model.preferred_skills = job.preferred_skills
        model.min_experience_years = job.min_experience_years
        model.education_requirement = job.education_requirement
        model.responsibilities = job.responsibilities
        model.keywords = job.keywords
        model.status = job.status
        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def list_all(self, skip: int = 0, limit: int = 50) -> list[Job]:
        result = await self._session.execute(
            select(JobModel).order_by(JobModel.created_at.desc()).offset(skip).limit(limit)
        )
        return [_to_entity(m) for m in result.scalars().all()]
