"""Concrete ReportRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.report import Report
from app.domain.interfaces.report_repository import ReportRepository
from app.infrastructure.db.models.report import ReportModel


def _to_entity(model: ReportModel) -> Report:
    return Report(
        id=model.id,
        job_id=model.job_id,
        generated_by=model.generated_by,
        file_path=model.file_path,
        summary=model.summary,
        created_at=model.created_at,
    )


class SQLAlchemyReportRepository(ReportRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, report: Report) -> Report:
        model = ReportModel(
            id=report.id,
            job_id=report.job_id,
            generated_by=report.generated_by,
            file_path=report.file_path,
            summary=report.summary,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, report_id: UUID) -> Report | None:
        model = await self._session.get(ReportModel, report_id)
        return _to_entity(model) if model else None

    async def list_by_job(self, job_id: UUID) -> list[Report]:
        result = await self._session.execute(
            select(ReportModel)
            .where(ReportModel.job_id == job_id)
            .order_by(ReportModel.created_at.desc())
        )
        return [_to_entity(m) for m in result.scalars().all()]
