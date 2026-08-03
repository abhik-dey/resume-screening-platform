"""Concrete ResumeSkillRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.infrastructure.db.models.resume_skill import ResumeSkillModel
from app.infrastructure.db.models.skill import SkillModel


class SQLAlchemyResumeSkillRepository(ResumeSkillRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, resume_id: UUID, skill_id: UUID, confidence: float | None) -> None:
        existing = await self._session.get(ResumeSkillModel, (resume_id, skill_id))
        if existing is not None:
            existing.confidence = confidence
        else:
            self._session.add(
                ResumeSkillModel(resume_id=resume_id, skill_id=skill_id, confidence=confidence)
            )
        await self._session.commit()

    async def list_by_resume(self, resume_id: UUID) -> list[ResumeSkillDetail]:
        result = await self._session.execute(
            select(SkillModel.id, SkillModel.name, SkillModel.category, ResumeSkillModel.confidence)
            .join(ResumeSkillModel, ResumeSkillModel.skill_id == SkillModel.id)
            .where(ResumeSkillModel.resume_id == resume_id)
        )
        return [
            ResumeSkillDetail(
                skill_id=row.id,
                name=row.name,
                category=row.category,
                confidence=row.confidence,
            )
            for row in result.all()
        ]
