"""Abstract repository interface for Report persistence."""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.report import Report


class ReportRepository(ABC):
    @abstractmethod
    async def create(self, report: Report) -> Report:
        """Persist a new report record.

        Create, not upsert: unlike scores or feedback, reports are point-in-time
        artifacts. A report generated last week described the candidate pool as
        it was then, and shouldn't be overwritten when a new one is generated."""

    @abstractmethod
    async def get_by_id(self, report_id: UUID) -> Report | None:
        """Return the report with this id, or None."""

    @abstractmethod
    async def list_by_job(self, job_id: UUID) -> list[Report]:
        """Return all reports for a job, most recent first."""
