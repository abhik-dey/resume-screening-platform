"""Abstract repository interface for CandidateFeedback persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.candidate_feedback import CandidateFeedback


class FeedbackRepository(ABC):
    @abstractmethod
    async def upsert(self, feedback: CandidateFeedback) -> CandidateFeedback:
        """Create or replace the feedback for a resume.

        Upsert, not append: a candidate should have one current
        recommendation, not a stack of contradictory ones. The audit_logs
        table already preserves every run for traceability."""

    @abstractmethod
    async def get_by_resume_id(self, resume_id: UUID) -> CandidateFeedback | None:
        """Return the feedback for this resume, or None if not yet generated."""

    @abstractmethod
    async def list_by_job(self, job_id: UUID) -> list[CandidateFeedback]:
        """Return all feedback records for a job (used by reporting in Phase 13)."""
