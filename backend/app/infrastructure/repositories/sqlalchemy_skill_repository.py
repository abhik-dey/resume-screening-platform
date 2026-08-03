"""Concrete SkillRepository backed by SQLAlchemy's async ORM."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.skill import Skill, SkillCategory
from app.domain.interfaces.skill_repository import SkillRepository
from app.infrastructure.db.models.skill import SkillModel


def _to_entity(model: SkillModel) -> Skill:
    return Skill(id=model.id, name=model.name, category=model.category, created_at=model.created_at)


class SQLAlchemySkillRepository(SkillRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name(self, name: str) -> Skill | None:
        result = await self._session.execute(
            select(SkillModel).where(func.lower(SkillModel.name) == name.lower())
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def get_or_create(self, name: str, category: SkillCategory) -> Skill:
        existing = await self.get_by_name(name)
        if existing is not None:
            return existing

        model = SkillModel(id=uuid.uuid4(), name=name, category=category)
        self._session.add(model)
        try:
            await self._session.commit()
        except Exception:
            # Two concurrent calls could both miss the get_by_name check
            # and race to insert the same skill name; the unique constraint
            # on SkillModel.name catches that, and we fall back to fetching
            # whichever row won.
            await self._session.rollback()
            existing = await self.get_by_name(name)
            if existing is not None:
                return existing
            raise
        await self._session.refresh(model)
        return _to_entity(model)
