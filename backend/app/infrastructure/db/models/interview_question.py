"""SQLAlchemy ORM model mapping the `interview_questions` table.

Added in Phase 11 rather than Phase 4: the Interview Question Agent is the
first consumer of this data, and designing the table seven phases before
anything used it would have risked guessing its shape wrong.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.entities.interview_question import QuestionCategory, QuestionDifficulty
from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID

if TYPE_CHECKING:
    from app.infrastructure.db.models.job import JobModel
    from app.infrastructure.db.models.resume import ResumeModel


class InterviewQuestionModel(Base):
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized from resume.job_id, same rationale as scores.job_id in
    # Phase 4: lets "all questions for job X" be answered without a join.
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[QuestionCategory] = mapped_column(
        SAEnum(
            QuestionCategory,
            values_callable=lambda enum: [e.value for e in enum],
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
    difficulty: Mapped[QuestionDifficulty] = mapped_column(
        SAEnum(
            QuestionDifficulty,
            values_callable=lambda enum: [e.value for e in enum],
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resume: Mapped["ResumeModel"] = relationship(back_populates="interview_questions")
    job: Mapped["JobModel"] = relationship(back_populates="interview_questions")
