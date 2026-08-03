"""Abstract repository interface for Score persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.score import Score


class ScoreRepository(ABC):
    @abstractmethod
    async def upsert(self, score: Score) -> Score:
        """Create or replace the score for a resume. Upsert (not create)
        because scores.resume_id is unique 1:1 — re-running the Matching
        Agent must update the existing row, not violate the constraint."""

    @abstractmethod
    async def get_by_resume_id(self, resume_id: UUID) -> Score | None:
        """Return the score for this resume, or None if not yet scored."""

    @abstractmethod
    async def list_by_job(self, job_id: UUID) -> list[Score]:
        """Return all scores for a job, highest similarity first.
        (Used by the Ranking Agent in Phase 10.)"""

    @abstractmethod
    async def update_rank(self, score_id: UUID, rank: int) -> None:
        """Set the rank on an existing score row.

        Separate from `upsert` deliberately: `upsert` is owned by the
        Matching Agent and must never touch rank, while rank is owned by
        the Ranking Agent, which considers all candidates for a job
        together. Keeping them apart makes it structurally impossible for
        one agent to clobber the other's field."""
