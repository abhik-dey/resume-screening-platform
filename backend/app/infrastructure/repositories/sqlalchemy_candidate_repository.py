"""Concrete CandidateRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.candidate import Candidate
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.infrastructure.db.models.candidate import CandidateModel


def _to_entity(model: CandidateModel) -> Candidate:
    return Candidate(
        id=model.id,
        full_name=model.full_name,
        email=model.email,
        phone=model.phone,
        links=dict(model.links or {}),
        created_at=model.created_at,
    )


class SQLAlchemyCandidateRepository(CandidateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> Candidate | None:
        # Case-insensitive lookup — "Jane@Co.com" and "jane@co.com" are the
        # same candidate, and different resumes may capitalize differently.
        result = await self._session.execute(
            select(CandidateModel).where(func.lower(CandidateModel.email) == email.lower())
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def get_by_id(self, candidate_id: UUID) -> Candidate | None:
        model = await self._session.get(CandidateModel, candidate_id)
        return _to_entity(model) if model else None

    async def create(self, candidate: Candidate) -> Candidate:
        model = CandidateModel(
            id=candidate.id,
            full_name=candidate.full_name,
            email=candidate.email,
            phone=candidate.phone,
            links=candidate.links,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)
