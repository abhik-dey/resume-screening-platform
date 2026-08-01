"""Abstract repository interface for Resume persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.resume import Resume


class ResumeRepository(ABC):
    @abstractmethod
    async def create(self, resume: Resume) -> Resume:
        """Persist a new resume and return the stored representation."""

    @abstractmethod
    async def get_by_id(self, resume_id: UUID) -> Resume | None:
        """Return the resume with this id, or None if no such resume exists."""

    @abstractmethod
    async def list_by_job(self, job_id: UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        """Return resumes for a given job, ordered by most recently created first."""
