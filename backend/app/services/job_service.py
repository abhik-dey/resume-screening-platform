"""Job use-case orchestration. Depends only on the abstract JobRepository."""
import uuid
from datetime import datetime, timezone

from app.domain.entities.job import Job, JobStatus
from app.domain.interfaces.job_repository import JobRepository


class JobService:
    def __init__(self, job_repository: JobRepository) -> None:
        self._jobs = job_repository

    async def create_job(
        self,
        created_by: uuid.UUID,
        title: str,
        description: str,
        required_skills: list[str] | None = None,
        preferred_skills: list[str] | None = None,
        min_experience_years: int | None = None,
        education_requirement: str | None = None,
        responsibilities: list[str] | None = None,
        keywords: list[str] | None = None,
        status: JobStatus = JobStatus.OPEN,
    ) -> Job:
        job = Job(
            id=uuid.uuid4(),
            created_by=created_by,
            title=title,
            description=description,
            required_skills=required_skills or [],
            preferred_skills=preferred_skills or [],
            min_experience_years=min_experience_years,
            education_requirement=education_requirement,
            responsibilities=responsibilities or [],
            keywords=keywords or [],
            status=status,
            created_at=datetime.now(timezone.utc),
        )
        return await self._jobs.create(job)

    async def get_job(self, job_id: uuid.UUID) -> Job | None:
        return await self._jobs.get_by_id(job_id)

    async def list_jobs(self, skip: int = 0, limit: int = 50) -> list[Job]:
        return await self._jobs.list_all(skip=skip, limit=limit)
