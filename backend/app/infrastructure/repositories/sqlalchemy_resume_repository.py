"""Concrete ResumeRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.resume import Resume
from app.domain.interfaces.resume_repository import ResumeRepository
from app.infrastructure.db.models.resume import ResumeModel


def _to_entity(model: ResumeModel) -> Resume:
    return Resume(
        id=model.id,
        job_id=model.job_id,
        uploaded_by=model.uploaded_by,
        storage_path=model.storage_path,
        original_filename=model.original_filename,
        candidate_id=model.candidate_id,
        raw_text=model.raw_text,
        parsed_data=model.parsed_data,
        status=model.status,
        created_at=model.created_at,
    )


class SQLAlchemyResumeRepository(ResumeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, resume: Resume) -> Resume:
        model = ResumeModel(
            id=resume.id,
            job_id=resume.job_id,
            uploaded_by=resume.uploaded_by,
            storage_path=resume.storage_path,
            original_filename=resume.original_filename,
            candidate_id=resume.candidate_id,
            raw_text=resume.raw_text,
            parsed_data=resume.parsed_data,
            status=resume.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, resume_id: UUID) -> Resume | None:
        model = await self._session.get(ResumeModel, resume_id)
        return _to_entity(model) if model else None

    async def update(self, resume: Resume) -> Resume:
        model = await self._session.get(ResumeModel, resume.id)
        if model is None:
            raise ValueError(f"Cannot update resume {resume.id}: not found")
        model.candidate_id = resume.candidate_id
        model.raw_text = resume.raw_text
        model.parsed_data = resume.parsed_data
        model.status = resume.status
        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def list_by_job(self, job_id: UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        result = await self._session.execute(
            select(ResumeModel)
            .where(ResumeModel.job_id == job_id)
            .order_by(ResumeModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [_to_entity(m) for m in result.scalars().all()]
