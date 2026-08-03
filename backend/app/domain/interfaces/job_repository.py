"""Abstract repository interface for Job persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.job import Job


class JobRepository(ABC):
    @abstractmethod
    async def create(self, job: Job) -> Job:
        """Persist a new job and return the stored representation."""

    @abstractmethod
    async def update(self, job: Job) -> Job:
        """Persist changes to an existing job (e.g. after description
        analysis) and return the updated representation."""

    @abstractmethod
    async def get_by_id(self, job_id: UUID) -> Job | None:
        """Return the job with this id, or None if no such job exists."""

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 50) -> list[Job]:
        """Return jobs ordered by most recently created first, paginated."""
