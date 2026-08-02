"""Abstract repository interface for Candidate persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.candidate import Candidate


class CandidateRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> Candidate | None:
        """Return the candidate with this email (case-insensitive), or None."""

    @abstractmethod
    async def get_by_id(self, candidate_id: UUID) -> Candidate | None:
        """Return the candidate with this id, or None if no such candidate exists."""

    @abstractmethod
    async def create(self, candidate: Candidate) -> Candidate:
        """Persist a new candidate and return the stored representation."""
