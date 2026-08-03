"""Concrete InterviewQuestionRepository backed by SQLAlchemy's async ORM."""
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.interview_question import InterviewQuestion
from app.domain.interfaces.interview_question_repository import InterviewQuestionRepository
from app.infrastructure.db.models.interview_question import InterviewQuestionModel


def _to_entity(model: InterviewQuestionModel) -> InterviewQuestion:
    return InterviewQuestion(
        id=model.id,
        resume_id=model.resume_id,
        job_id=model.job_id,
        question=model.question,
        category=model.category,
        difficulty=model.difficulty,
        rationale=model.rationale,
        created_at=model.created_at,
    )


class SQLAlchemyInterviewQuestionRepository(InterviewQuestionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_resume(
        self, resume_id: UUID, questions: list[InterviewQuestion]
    ) -> list[InterviewQuestion]:
        # Delete then insert, committed together, so a regenerate either
        # fully replaces the old set or leaves it untouched — never a
        # half-deleted mix of old and new questions.
        await self._session.execute(
            delete(InterviewQuestionModel).where(InterviewQuestionModel.resume_id == resume_id)
        )
        models = [
            InterviewQuestionModel(
                id=q.id,
                resume_id=q.resume_id,
                job_id=q.job_id,
                question=q.question,
                category=q.category,
                difficulty=q.difficulty,
                rationale=q.rationale,
            )
            for q in questions
        ]
        self._session.add_all(models)
        await self._session.commit()
        for model in models:
            await self._session.refresh(model)
        return [_to_entity(m) for m in models]

    async def list_by_resume(self, resume_id: UUID) -> list[InterviewQuestion]:
        result = await self._session.execute(
            select(InterviewQuestionModel)
            .where(InterviewQuestionModel.resume_id == resume_id)
            .order_by(InterviewQuestionModel.created_at, InterviewQuestionModel.id)
        )
        return [_to_entity(m) for m in result.scalars().all()]
