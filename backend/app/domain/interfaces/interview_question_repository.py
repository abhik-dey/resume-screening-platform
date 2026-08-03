"""Abstract repository interface for InterviewQuestion persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.interview_question import InterviewQuestion


class InterviewQuestionRepository(ABC):
    @abstractmethod
    async def replace_for_resume(
        self, resume_id: UUID, questions: list[InterviewQuestion]
    ) -> list[InterviewQuestion]:
        """Replace all questions for a resume with a new set.

        Replace rather than append: regenerating questions should produce a
        fresh set, not accumulate stale ones from earlier runs alongside
        the current ones."""

    @abstractmethod
    async def list_by_resume(self, resume_id: UUID) -> list[InterviewQuestion]:
        """Return every question generated for this resume."""
