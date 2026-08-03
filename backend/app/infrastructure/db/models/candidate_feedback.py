"""SQLAlchemy ORM model mapping the `candidate_feedback` table."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.feedback.recommendation import RecommendationCategory
from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID, PORTABLE_JSON

if TYPE_CHECKING:
    from app.infrastructure.db.models.job import JobModel
    from app.infrastructure.db.models.resume import ResumeModel


class CandidateFeedbackModel(Base):
    __tablename__ = "candidate_feedback"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Unique: one current feedback record per resume. Regenerating replaces
    # it rather than accumulating a history of contradictory recommendations
    # — the audit_logs table already preserves every run for traceability.
    resume_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation: Mapped[RecommendationCategory] = mapped_column(
        SAEnum(
            RecommendationCategory,
            values_callable=lambda enum: [e.value for e in enum],
            native_enum=False,
            length=30,
        ),
        nullable=False,
    )
    threshold_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    weaknesses: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    risk_factors: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    improvement_suggestions: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    narrative_generation_failed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resume: Mapped["ResumeModel"] = relationship(back_populates="feedback")
    job: Mapped["JobModel"] = relationship(back_populates="feedback_entries")
