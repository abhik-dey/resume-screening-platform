"""Concrete ScoreRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.score import Score
from app.domain.interfaces.score_repository import ScoreRepository
from app.infrastructure.db.models.score import ScoreModel


def _to_entity(model: ScoreModel) -> Score:
    return Score(
        id=model.id,
        resume_id=model.resume_id,
        job_id=model.job_id,
        similarity_score=model.similarity_score,
        skill_overlap=list(model.skill_overlap or []),
        missing_skills=list(model.missing_skills or []),
        strengths=list(model.strengths or []),
        weaknesses=list(model.weaknesses or []),
        rank=model.rank,
        explanation=model.explanation,
        created_at=model.created_at,
    )


class SQLAlchemyScoreRepository(ScoreRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, score: Score) -> Score:
        result = await self._session.execute(
            select(ScoreModel).where(ScoreModel.resume_id == score.resume_id)
        )
        model = result.scalar_one_or_none()

        if model is None:
            model = ScoreModel(
                id=score.id,
                resume_id=score.resume_id,
                job_id=score.job_id,
                similarity_score=score.similarity_score,
                skill_overlap=score.skill_overlap,
                missing_skills=score.missing_skills,
                strengths=score.strengths,
                weaknesses=score.weaknesses,
                rank=score.rank,
                explanation=score.explanation,
            )
            self._session.add(model)
        else:
            model.job_id = score.job_id
            model.similarity_score = score.similarity_score
            model.skill_overlap = score.skill_overlap
            model.missing_skills = score.missing_skills
            model.strengths = score.strengths
            model.weaknesses = score.weaknesses
            model.explanation = score.explanation
            # Deliberately NOT updating `rank` here: rank is owned by the
            # Ranking Agent (Phase 10), which considers all candidates for
            # a job together. Re-running a single match must not clobber it.

        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def get_by_resume_id(self, resume_id: UUID) -> Score | None:
        result = await self._session.execute(
            select(ScoreModel).where(ScoreModel.resume_id == resume_id)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def list_by_job(self, job_id: UUID) -> list[Score]:
        result = await self._session.execute(
            select(ScoreModel)
            .where(ScoreModel.job_id == job_id)
            .order_by(ScoreModel.similarity_score.desc())
        )
        return [_to_entity(m) for m in result.scalars().all()]
