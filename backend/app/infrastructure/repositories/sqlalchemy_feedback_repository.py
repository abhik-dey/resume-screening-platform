"""Concrete FeedbackRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.candidate_feedback import CandidateFeedback
from app.domain.interfaces.feedback_repository import FeedbackRepository
from app.infrastructure.db.models.candidate_feedback import CandidateFeedbackModel


def _to_entity(model: CandidateFeedbackModel) -> CandidateFeedback:
    return CandidateFeedback(
        id=model.id,
        resume_id=model.resume_id,
        job_id=model.job_id,
        recommendation=model.recommendation,
        threshold_rationale=model.threshold_rationale,
        summary=model.summary,
        strengths=list(model.strengths or []),
        weaknesses=list(model.weaknesses or []),
        risk_factors=list(model.risk_factors or []),
        improvement_suggestions=list(model.improvement_suggestions or []),
        narrative_generation_failed=model.narrative_generation_failed,
        created_at=model.created_at,
    )


class SQLAlchemyFeedbackRepository(FeedbackRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, feedback: CandidateFeedback) -> CandidateFeedback:
        result = await self._session.execute(
            select(CandidateFeedbackModel).where(
                CandidateFeedbackModel.resume_id == feedback.resume_id
            )
        )
        model = result.scalar_one_or_none()

        if model is None:
            model = CandidateFeedbackModel(
                id=feedback.id,
                resume_id=feedback.resume_id,
                job_id=feedback.job_id,
                recommendation=feedback.recommendation,
                threshold_rationale=feedback.threshold_rationale,
                summary=feedback.summary,
                strengths=feedback.strengths,
                weaknesses=feedback.weaknesses,
                risk_factors=feedback.risk_factors,
                improvement_suggestions=feedback.improvement_suggestions,
                narrative_generation_failed=feedback.narrative_generation_failed,
            )
            self._session.add(model)
        else:
            model.job_id = feedback.job_id
            model.recommendation = feedback.recommendation
            model.threshold_rationale = feedback.threshold_rationale
            model.summary = feedback.summary
            model.strengths = feedback.strengths
            model.weaknesses = feedback.weaknesses
            model.risk_factors = feedback.risk_factors
            model.improvement_suggestions = feedback.improvement_suggestions
            model.narrative_generation_failed = feedback.narrative_generation_failed

        await self._session.commit()
        await self._session.refresh(model)
        return _to_entity(model)

    async def get_by_resume_id(self, resume_id: UUID) -> CandidateFeedback | None:
        result = await self._session.execute(
            select(CandidateFeedbackModel).where(CandidateFeedbackModel.resume_id == resume_id)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def list_by_job(self, job_id: UUID) -> list[CandidateFeedback]:
        result = await self._session.execute(
            select(CandidateFeedbackModel).where(CandidateFeedbackModel.job_id == job_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]
