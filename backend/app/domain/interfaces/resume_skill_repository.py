"""Abstract repository interface for the resume<->skill association."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.resume_skill import ResumeSkillDetail


class ResumeSkillRepository(ABC):
    @abstractmethod
    async def upsert(self, resume_id: UUID, skill_id: UUID, confidence: float | None) -> None:
        """Link a skill to a resume, or update its confidence if the link
        already exists. Idempotent — safe to call if the agent re-runs."""

    @abstractmethod
    async def list_by_resume(self, resume_id: UUID) -> list[ResumeSkillDetail]:
        """Return every skill linked to a resume, with name/category/confidence."""
